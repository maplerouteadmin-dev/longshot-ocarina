"""Runs the whole live pipeline on a background thread:
mic readings -> NoteMatcher -> gate (game flag / hotkey / always) -> virtual pad.

Button timing is scheduled rather than slept: a release that comes before the
note's minimum hold time is queued for later, so the audio keeps being
processed instead of backing up (the old time.sleep() in release_held added
lag to the next note).
"""
import queue
import threading
import time

import audio
import config
import echo
import gamepad
import gamewin
from keys import VK_SCROLL, is_toggled
from matcher import NoteMatcher
from ocarina_flag import GameFlag


class OutputScheduler:
    """Owns the virtual pad. Guarantees each press lasts min_hold and leaves a
    short gap between releasing one note and pressing the next."""

    def __init__(self, min_hold, gap, on_press=None):
        self.min_hold, self.gap = min_hold, gap
        self.held = None        # button physically down right now
        self.open_key = None    # last scheduled press with no release queued yet
        self.free_at = 0.0      # earliest time the next action may happen
        self.actions = []       # FIFO of (time, "press"/"release", key)
        self.on_press = on_press

    def _queue_release(self, now):
        at = max(now, self.free_at)
        self.actions.append((at, "release", self.open_key))
        self.open_key = None
        self.free_at = at + self.gap

    def press(self, key, now):
        if self.open_key is not None:
            self._queue_release(now)
        start = max(now, self.free_at)
        self.actions.append((start, "press", key))
        self.open_key = key
        self.free_at = start + self.min_hold

    def release(self, key, now):
        if self.open_key == key:
            self._queue_release(now)

    def release_all(self, now):
        if self.open_key is not None:
            self._queue_release(now)

    def tick(self, now):
        while self.actions and self.actions[0][0] <= now:
            _, kind, key = self.actions.pop(0)
            if kind == "press":
                if self.held is not None:
                    gamepad.release(self.held)
                gamepad.press(key)
                self.held = key
                if self.on_press:
                    self.on_press(key)
            elif self.held == key:
                gamepad.release(key)
                self.held = None

    def shutdown(self):
        if self.held is not None:
            gamepad.release(self.held)
            self.held = None
        self.open_key = None
        self.actions.clear()


class CustomOutput:
    """Custom note mappings: any controller input, held with the note or for a set time.

    mapping: {"input", "x", "y", "amount", "mode": "hold"|"timed", "seconds", "delay"}
    """

    def __init__(self, mappings, min_hold):
        self.maps = mappings            # key -> mapping
        self.min_hold = min_hold
        self.pending = []               # (time, key, on)
        self.active = {}                # key -> earliest release time

    def _send(self, key, on):
        m = self.maps[key]
        gamepad.set_input(m["input"], on, float(m.get("x", 0)), float(m.get("y", 0)), float(m.get("amount", 1)))

    def press(self, key, now):
        m = self.maps[key]
        start = now + max(0.0, float(m.get("delay", 0) or 0))
        self.pending = [p for p in self.pending if p[1] != key]   # re-trigger restarts the timer
        self.pending.append((start, key, True))
        if m.get("mode") == "timed":
            self.pending.append((start + max(0.05, float(m.get("seconds", 1) or 1)), key, False))

    def release(self, key, now):
        if self.maps[key].get("mode") == "timed":
            return                                   # timed mappings run their full time
        if key not in self.active:                   # note ended during the delay: never press
            self.pending = [p for p in self.pending if p[1] != key]
            return
        self.pending.append((max(now, self.active[key]), key, False))

    def tick(self, now):
        due = [p for p in self.pending if p[0] <= now]
        if not due:
            return
        self.pending = [p for p in self.pending if p[0] > now]
        for _, key, on in sorted(due):
            self._send(key, on)
            if on:
                self.active[key] = now + self.min_hold
            else:
                self.active.pop(key, None)

    def shutdown(self):
        for key in list(self.active):
            self._send(key, False)
        self.active.clear()
        self.pending.clear()


class Engine:
    def __init__(self, cfg, inject=True):
        self.cfg = cfg
        self.inject = inject
        self.status = queue.Queue(maxsize=500)   # Decisions + gate info for the UI
        self._stop = threading.Event()
        self._thread = None
        self.gate_state = "off"
        self.gate_note = ""

    def start(self):
        idx, name, sr = audio.find_device(self.cfg["mic_name"])
        self.mic_label = name
        self.analyzer = audio.Analyzer(idx, sr)
        customs = {f"custom:{i}": m for i, m in enumerate(self.cfg.get("custom", []))
                   if m.get("hz") and m.get("input")}
        self.free_keys = set(customs)       # custom mappings work with the ocarina up or put away
        notes = dict(config.note_freqs(self.cfg))
        # extra notes (D-pad left) work whether the ocarina is up or put away
        self.free_keys |= {d["button"] for d in config.EXTRA_DEFS if d["button"] in notes}
        if not self.cfg.get("extras_when_away", True):
            self.free_keys = set()          # user wants nothing heard while the ocarina is put away
        notes.update({k: float(m["hz"]) for k, m in customs.items()})
        self.matcher = NoteMatcher(notes, config.match_params(self.cfg))
        self.flag = GameFlag(**self.cfg["flag"])
        focus = gamewin.focus_game if self.cfg.get("focus_game_on_note", True) else None
        self._focus = (lambda: threading.Thread(target=focus, daemon=True).start()) if focus else (lambda: None)
        self.out = OutputScheduler(self.cfg["min_hold_seconds"], self.cfg["switch_gap_seconds"],
                                   on_press=lambda _k: self._focus())
        self.custom = CustomOutput(customs, self.cfg["min_hold_seconds"])
        self.game_audio = None
        gsf = self.cfg["game_sound_filter"]
        if gsf["enabled"]:
            self.game_audio = echo.GameAudio(gsf["device"])
            self.game_audio.start()
        if self.inject:
            gamepad.connect()
        self.analyzer.start()
        self._stop.clear()
        self._thread = threading.Thread(target=self._run, daemon=True)
        self._thread.start()

    def stop(self):
        self._stop.set()
        if self._thread:
            self._thread.join(timeout=2)
        self.analyzer.stop()
        if self.game_audio:
            self.game_audio.stop()
        if self.inject:
            self.out.shutdown()
            self.custom.shutdown()
            gamepad.disconnect()

    def _gate(self, now, state):
        """Returns (listening, allow_new). state carries the flag debounce."""
        mode = self.cfg["gate_mode"]
        if mode == "always":
            self.gate_note = "always listening"
            return True, True
        if mode == "game":
            up = self.flag.read()
            if up is not None:
                self.gate_note = "game flag (auto)" if self.flag.via_chains else "game flag"
                # the chain-found flag is steady, so it barely needs any grace
                grace = (min(self.cfg["flag_grace_seconds"], 0.15) if self.flag.via_chains
                         else self.cfg["flag_grace_seconds"])
                if up:
                    state["down_since"] = None
                    state["listening"] = True
                    return True, True
                if state["down_since"] is None:
                    state["down_since"] = now
                if state["listening"] and now - state["down_since"] < grace:
                    # the flag pulses during play -- keep a held note going, but
                    # don't start a new one from silence until it reads "up" again
                    return True, False
                state["listening"] = False
                return False, False
            self.gate_note = "game flag unavailable -> using Scroll Lock"
        else:
            self.gate_note = "Scroll Lock"
        on = is_toggled(VK_SCROLL)
        return on, on

    def _emit(self, item):
        try:
            self.status.put_nowait(item)
        except queue.Full:
            pass

    def _run(self):
        gate_state = {"listening": False, "down_since": None}
        last_gate = 0.0
        listening, allow_new = False, False
        while not self._stop.is_set():
            now = time.monotonic()
            if now - last_gate >= 0.02:
                last_gate = now
                was = listening
                listening, allow_new = self._gate(now, gate_state)
                self.gate_state = "on" if listening else "off"
                if was and not listening:
                    for _, key in self.matcher.reset():
                        if self.inject and not key.startswith("custom:"):
                            self.out.release(key, now)
                        elif self.inject and key not in self.free_keys:
                            self.custom.release(key, now)
                    self.analyzer.drain()
                    self._emit(("gate", False, self.gate_note))
                elif listening and not was:
                    self.analyzer.drain()
                    self._emit(("gate", True, self.gate_note))

            # custom mappings and extra notes keep listening with the ocarina put away
            active = listening or bool(self.free_keys)
            readings = self.analyzer.drain()
            if not active:
                readings = []
            if readings and self.game_audio:
                self.game_audio.annotate(readings, self.matcher.gate_level())
            for r in readings:
                d = self.matcher.update(r, allow_new=allow_new if listening else True)
                for kind, key in d.events:
                    if not self.inject:
                        continue
                    if key.startswith("custom:"):
                        if listening or key in self.free_keys:
                            if kind == "press":
                                self.custom.press(key, now)
                                self._focus()
                            else:
                                self.custom.release(key, now)
                    elif listening or key in self.free_keys:
                        (self.out.press if kind == "press" else self.out.release)(key, now)
                self._emit(("reading", d))
            if self.inject:
                t = time.monotonic()
                self.out.tick(t)
                self.custom.tick(t)
            time.sleep(0.003)

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
        self.matcher = NoteMatcher(config.note_freqs(self.cfg), config.match_params(self.cfg))
        self.flag = GameFlag(**self.cfg["flag"])
        self.out = OutputScheduler(self.cfg["min_hold_seconds"], self.cfg["switch_gap_seconds"])
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
                        if self.inject:
                            self.out.release(key, now)
                    self.analyzer.drain()
                    self._emit(("gate", False, self.gate_note))
                elif listening and not was:
                    self.analyzer.drain()
                    self._emit(("gate", True, self.gate_note))

            readings = self.analyzer.drain() if listening else []
            if not listening:
                self.analyzer.drain()
            if readings and self.game_audio:
                self.game_audio.annotate(readings, self.matcher.gate_level())
            for r in readings:
                d = self.matcher.update(r, allow_new=allow_new)
                for kind, key in d.events:
                    if self.inject:
                        (self.out.press if kind == "press" else self.out.release)(key, now)
                self._emit(("reading", d))
            if self.inject:
                self.out.tick(time.monotonic())
            time.sleep(0.003)

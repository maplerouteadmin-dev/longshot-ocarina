"""Ocarina Translator -- play the Longshot ocarina with a real ocarina.

Tabs:
  Setup      pick the mic (live level + pitch), measure background noise,
             check the virtual-controller driver and Longshot's note bindings
  Calibrate  record each note (3 takes) with the fingering picture shown
  Test       live note detection + song practice, without touching the game
  Play       run it against the game
  Game Flag  re-find the "ocarina is up" flag after Longshot is relaunched
  Advanced   timing/sensitivity settings
"""
import os
import queue
import threading
import time
import tkinter as tk
import traceback
import webbrowser
from dataclasses import asdict
from tkinter import filedialog, messagebox, ttk

from PIL import Image, ImageTk

import audio
import calibration
import config
import diagram
import echo
import fingering
import pitch
import setup_helpers
from engine import Engine
from flag_scan import FlagScanner
from matcher import MatchParams, NoteMatcher
from ocarina_flag import GameFlag, game_running

BIG = ("Segoe UI", 28, "bold")
MID = ("Segoe UI", 14)
TAKES_PER_NOTE = 3


class App(tk.Tk):
    def __init__(self):
        super().__init__()
        self.title("Ocarina Translator")
        self.geometry("900x640")
        self.minsize(820, 580)
        self.cfg = config.load()
        self.ui_queue = queue.Queue()
        self.monitor = None
        self.monitor_paused = False
        self.game_audio = None
        self.engine = None
        self._busy = False

        nb = ttk.Notebook(self)
        nb.pack(fill="both", expand=True)
        self.nb = nb
        self.tabs = {}
        for name, cls in [("Setup", SetupTab), ("Calibrate", CalibrateTab), ("Test", TestTab),
                          ("Play", PlayTab), ("Game Flag", FlagTab), ("Advanced", AdvancedTab)]:
            tab = cls(nb, self)
            nb.add(tab, text=name)
            self.tabs[name] = tab
        nb.bind("<<NotebookTabChanged>>", lambda e: self.current_tab().on_show())

        self.status = ttk.Label(self, anchor="w", padding=(8, 2))
        self.status.pack(fill="x")
        self.start_monitor()
        self.after(40, self._loop)
        self.protocol("WM_DELETE_WINDOW", self.on_close)

    # ---- shared plumbing -------------------------------------------------
    def current_tab(self):
        return self.tabs[self.nb.tab(self.nb.select(), "text")]

    def save(self):
        config.save(self.cfg)

    def set_status(self, text):
        self.status.config(text=text)

    def run_bg(self, work, done=None, error=None):
        """Run work() off the UI thread; done(result)/error(msg) back on it."""
        def target():
            try:
                result = work()
                self.ui_queue.put(lambda: done(result) if done else None)
            except Exception as e:
                msg = str(e) or e.__class__.__name__
                traceback.print_exc()
                self.ui_queue.put(lambda: (error or self._show_error)(msg))
        threading.Thread(target=target, daemon=True).start()

    def _show_error(self, msg):
        messagebox.showerror("Ocarina Translator", msg)

    def start_monitor(self):
        self.stop_monitor()
        idx, name, sr = audio.find_device(self.cfg["mic_name"])
        if idx is None:
            self.set_status("No microphone found.")
            return
        try:
            self.monitor = audio.Analyzer(idx, sr)
            self.monitor.start()
            self.set_status(f"Mic: {name} ({sr} Hz)")
        except Exception as e:
            self.monitor = None
            self.set_status(f"Couldn't open mic '{name}': {e}")
        self.start_game_audio()

    def start_game_audio(self):
        if self.game_audio:
            self.game_audio.stop()
            self.game_audio = None
        gsf = self.cfg["game_sound_filter"]
        if gsf["enabled"] and not self.engine:
            self.game_audio = echo.GameAudio(gsf["device"])
            self.game_audio.start()

    def stop_monitor(self):
        if self.monitor:
            self.monitor.stop()
            self.monitor = None
        if self.game_audio:
            self.game_audio.stop()
            self.game_audio = None

    def _loop(self):
        while True:
            try:
                self.ui_queue.get_nowait()()
            except queue.Empty:
                break
        tab = self.current_tab()
        if self.monitor and not self.monitor_paused:
            readings = self.monitor.drain()
            if readings:
                tab.on_readings(readings)
        tab.tick()
        self.after(40, self._loop)

    def on_close(self):
        if self.engine:
            self.engine.stop()
        self.stop_monitor()
        self.destroy()


class Tab(ttk.Frame):
    def __init__(self, parent, app):
        super().__init__(parent, padding=12)
        self.app = app

    def on_show(self):
        pass

    def on_readings(self, readings):
        pass

    def tick(self):
        pass


class LevelMeter(tk.Canvas):
    """Horizontal level bar with a marker at the note-detection threshold."""

    def __init__(self, parent, width=420, height=22):
        super().__init__(parent, width=width, height=height, bg="#222", highlightthickness=0)
        self.w, self.h = width, height
        self.bar = self.create_rectangle(0, 0, 0, height, fill="#3c3", width=0)
        self.gate = self.create_line(0, 0, 0, height, fill="#fc3", width=2)

    @staticmethod
    def _x(level, w):
        import math
        db = 20 * math.log10(max(level, 1e-5))      # -100..0 dBFS
        return max(0, min(w, (db + 70) / 70 * w))  # show -70..0 dB

    def show(self, level, gate):
        self.coords(self.bar, 0, 0, self._x(level, self.w), self.h)
        self.itemconfig(self.bar, fill="#3c3" if level >= gate else "#777")
        gx = self._x(gate, self.w)
        self.coords(self.gate, gx, 0, gx, self.h)


# ---- Setup ---------------------------------------------------------------
class SetupTab(Tab):
    def __init__(self, parent, app):
        super().__init__(parent, app)
        box = ttk.LabelFrame(self, text="Microphone", padding=10)
        box.pack(fill="x")
        self.devices = audio.input_devices()
        names = [n for _, n, _ in self.devices]
        self.mic = ttk.Combobox(box, values=names, state="readonly", width=50)
        cur = audio.find_device(app.cfg["mic_name"])[1]
        if cur in names:
            self.mic.set(cur)
        self.mic.bind("<<ComboboxSelected>>", self._mic_changed)
        self.mic.grid(row=0, column=0, columnspan=2, sticky="w")
        ttk.Label(box, text="Level:").grid(row=1, column=0, sticky="w", pady=(8, 0))
        self.meter = LevelMeter(box)
        self.meter.grid(row=1, column=1, sticky="w", pady=(8, 0))
        self.pitch_lbl = ttk.Label(box, text="--", font=MID)
        self.pitch_lbl.grid(row=2, column=1, sticky="w")
        ttk.Label(box, text="Green = loud enough to count as a note; the yellow line is that threshold.",
                  foreground="#666").grid(row=3, column=0, columnspan=2, sticky="w")
        row = ttk.Frame(box)
        row.grid(row=4, column=0, columnspan=2, sticky="w", pady=(8, 0))
        self.noise_btn = ttk.Button(row, text="Measure background noise (stay quiet 2s)", command=self._measure)
        self.noise_btn.pack(side="left")
        self.noise_lbl = ttk.Label(row, text="")
        self.noise_lbl.pack(side="left", padx=8)

        gs = ttk.LabelFrame(self, text="Game sounds", padding=10)
        gs.pack(fill="x", pady=(12, 0))
        gsf = app.cfg["game_sound_filter"]
        self.gs_on = tk.BooleanVar(value=gsf["enabled"])
        ttk.Checkbutton(gs, text="Ignore notes the game itself is playing (music, Link playing your note back) "
                                 "-- needed when the mic can hear the TV/speakers",
                        variable=self.gs_on, command=self._gs_changed).grid(row=0, column=0, columnspan=2, sticky="w")
        ttk.Label(gs, text="Game audio comes out of:").grid(row=1, column=0, sticky="w", pady=(6, 0))
        self.default_out = "Windows default output"
        self.gs_dev = ttk.Combobox(gs, values=[self.default_out] + echo.output_devices(), state="readonly", width=46)
        self.gs_dev.set(gsf["device"] or self.default_out)
        self.gs_dev.bind("<<ComboboxSelected>>", lambda e: self._gs_changed())
        self.gs_dev.grid(row=1, column=1, sticky="w", padx=6, pady=(6, 0))
        self.gs_lbl = ttk.Label(gs, foreground="#666")
        self.gs_lbl.grid(row=2, column=0, columnspan=2, sticky="w", pady=(6, 0))

        chk = ttk.LabelFrame(self, text="Checks", padding=10)
        chk.pack(fill="x", pady=(12, 0))
        self.vigem_lbl = ttk.Label(chk)
        self.vigem_lbl.grid(row=0, column=0, sticky="w")
        self.vigem_btn = ttk.Button(chk, text="Get ViGEmBus driver",
                                    command=lambda: webbrowser.open(setup_helpers.VIGEM_URL))
        self.vigem_btn.grid(row=0, column=1, sticky="w", padx=8)
        self.ini_lbl = ttk.Label(chk, wraplength=560)
        self.ini_lbl.grid(row=1, column=0, sticky="w", pady=(8, 0))
        btns = ttk.Frame(chk)
        btns.grid(row=1, column=1, sticky="w", padx=8, pady=(8, 0))
        ttk.Button(btns, text="Find…", command=self._browse_ini).pack(side="left")
        self.apply_btn = ttk.Button(btns, text="Apply note bindings", command=self._apply)
        self.apply_btn.pack(side="left", padx=4)
        self.game_lbl = ttk.Label(chk)
        self.game_lbl.grid(row=2, column=0, sticky="w", pady=(8, 0))
        ttk.Button(chk, text="Re-check", command=self.refresh).grid(row=2, column=1, sticky="w", padx=8, pady=(8, 0))
        self.refresh()

    def on_show(self):
        self.refresh()

    def refresh(self):
        ok = setup_helpers.vigem_installed()
        self.vigem_lbl.config(text=("✔ Virtual controller driver (ViGEmBus) is installed" if ok else
                                    "✘ ViGEmBus is not installed -- needed to send notes to the game"))
        self.vigem_btn.grid() if not ok else self.vigem_btn.grid_remove()
        path = setup_helpers.find_ini(self.app.cfg.get("longshot_ini", ""))
        if path:
            self.app.cfg["longshot_ini"] = path
            ok_b = setup_helpers.bindings_ok(path)
            self.ini_lbl.config(text=f"{'✔' if ok_b else '✘'} Longshot settings: {path}\n" +
                                ("Ocarina notes are bound to the controller." if ok_b else
                                 "Ocarina notes aren't bound yet -- close Longshot, then Apply note bindings."))
            self.apply_btn.state(["!disabled"] if not ok_b else ["disabled"])
        else:
            self.ini_lbl.config(text="✘ Couldn't find longshot_options.ini -- start Longshot once, or use Find…")
            self.apply_btn.state(["disabled"])
        running = game_running()
        self.game_lbl.config(text="Longshot is running" if running else "Longshot is not running")
        nf = self.app.cfg["match"]["noise_floor"]
        self.noise_lbl.config(text=f"background level: {nf:.4f}")

    def _gs_changed(self):
        dev = self.gs_dev.get()
        self.app.cfg["game_sound_filter"] = {"enabled": self.gs_on.get(),
                                             "device": "" if dev == self.default_out else dev}
        self.app.save()
        self.app.start_game_audio()

    def tick(self):
        ga = self.app.game_audio
        if not self.gs_on.get():
            self.gs_lbl.config(text="Off -- fine with headphones.")
        elif ga is None or ga.error:
            self.gs_lbl.config(text=(ga.error if ga else "not running"), foreground="#b00")
        else:
            dom = ga.dominant()
            self.gs_lbl.config(foreground="#666", text=f"Listening to {ga.device_name}: "
                               + (f"game is playing ~{dom:.0f} Hz" if dom else "game is quiet"))

    def _mic_changed(self, _e=None):
        self.app.cfg["mic_name"] = self.mic.get()
        self.app.save()
        self.app.start_monitor()

    def _measure(self):
        if not self.app.monitor:
            return
        self.app.monitor_paused = True
        self.noise_btn.state(["disabled"])
        self.noise_lbl.config(text="listening… stay quiet")

        def done(floor):
            self.app.monitor_paused = False
            self.noise_btn.state(["!disabled"])
            self.app.cfg["match"]["noise_floor"] = floor
            self.app.save()
            self.refresh()

        self.app.run_bg(lambda: audio.measure_noise_floor(self.app.monitor), done)

    def _browse_ini(self):
        p = filedialog.askopenfilename(title="Find longshot_options.ini",
                                       filetypes=[("Longshot settings", "longshot_options.ini"), ("INI", "*.ini")])
        if p:
            self.app.cfg["longshot_ini"] = p
            self.app.save()
            self.refresh()

    def _apply(self):
        try:
            backup = setup_helpers.apply_bindings(self.app.cfg["longshot_ini"])
            messagebox.showinfo("Ocarina Translator", f"Bindings applied. Backup saved:\n{backup}")
        except Exception as e:
            messagebox.showerror("Ocarina Translator", str(e))
        self.app.save()
        self.refresh()

    def on_readings(self, readings):
        r = readings[-1]
        p = config.match_params(self.app.cfg)
        gate = max(p.min_level, p.noise_floor * p.level_margin)
        self.meter.show(max(x.level for x in readings), gate)
        voiced = [x for x in readings if x.freq and x.conf >= p.min_conf and x.level >= gate]
        self.pitch_lbl.config(text=f"{voiced[-1].freq:.1f} Hz" if voiced else "--")


# ---- Calibrate -----------------------------------------------------------
class CalibrateTab(Tab):
    def __init__(self, parent, app):
        super().__init__(parent, app)
        top = ttk.Frame(self)
        top.pack(fill="x")
        ttk.Label(top, text="Ocarina:").pack(side="left")
        self.profile = ttk.Combobox(top, values=list(fingering.PROFILES), state="readonly", width=20)
        self.profile.set(app.cfg["ocarina"])
        self.profile.pack(side="left", padx=6)

        body = ttk.Frame(self)
        body.pack(fill="both", expand=True, pady=8)
        self.tree = ttk.Treeview(body, columns=("note", "pitch", "hz", "spread", "takes"), show="headings",
                                 height=6, selectmode="browse")
        for col, text, w in [("note", "Button / note", 150), ("pitch", "Pitch", 60), ("hz", "Calibrated", 90),
                             ("spread", "Wander", 70), ("takes", "Takes", 50)]:
            self.tree.heading(col, text=text)
            self.tree.column(col, width=w, anchor="w")
        self.tree.pack(side="left", fill="y")
        self.tree.bind("<<TreeviewSelect>>", lambda e: self._select())

        right = ttk.Frame(body, padding=(12, 0))
        right.pack(side="left", fill="both", expand=True)
        self.img_lbl = ttk.Label(right)
        self.img_lbl.pack()
        self.finger_note = ttk.Label(right, foreground="#a60", wraplength=420, justify="center")
        self.finger_note.pack()
        row = ttk.Frame(right)
        row.pack(pady=6)
        self.rec_btn = ttk.Button(row, text="Record take", command=self._record)
        self.rec_btn.pack(side="left")
        ttk.Button(row, text="Clear takes", command=self._clear).pack(side="left", padx=4)
        ttk.Button(row, text="Save note", command=self._save_note).pack(side="left")
        self.rec_lbl = ttk.Label(right, font=MID)
        self.rec_lbl.pack()
        self.takes_lbl = ttk.Label(right)
        self.takes_lbl.pack()
        self.warn_lbl = ttk.Label(self, foreground="#b00", wraplength=820, justify="left")
        self.warn_lbl.pack(fill="x")
        ttk.Label(self, text="Tip: blow the way you will while playing -- calibration should match your real "
                             "breath, not your most careful one. Calibrate again whenever you change mic or room.",
                  foreground="#666", wraplength=820).pack(fill="x")
        self.takes = {}
        self.photo = None
        self._fill()
        self.tree.selection_set(self.tree.get_children()[0])

    def _defs(self):
        return {d["button"]: d for d in config.NOTE_DEFS}

    def _fill(self):
        sel = self.tree.selection()
        self.tree.delete(*self.tree.get_children())
        for d in config.NOTE_DEFS:
            n = self.app.cfg["notes"].get(d["button"], {})
            self.tree.insert("", "end", iid=d["button"], values=(
                f"{d['button']}  {d['label']}", d["pitch"],
                f"{n['hz']:.1f} Hz" if n.get("hz") else "--",
                f"{n.get('spread_cents', 0):.0f}¢" if n.get("hz") else "",
                len(n.get("takes", [])) if n.get("hz") else ""))
        if sel:
            self.tree.selection_set(sel)
        warns = calibration.check_notes(self.app.cfg["notes"])
        self.warn_lbl.config(text="\n".join("⚠ " + w for w in warns))

    def _current(self):
        sel = self.tree.selection()
        return self._defs()[sel[0]] if sel else None

    def _select(self):
        d = self._current()
        if not d:
            return
        path = os.path.join(diagram.OUT_DIR, f"{d['pitch']}.png")
        if not os.path.exists(path):
            path = diagram.render(d["pitch"])
        img = Image.open(path)
        img.thumbnail((440, 340))
        self.photo = ImageTk.PhotoImage(img)
        self.img_lbl.config(image=self.photo)
        ok = fingering.confirmed(self.profile.get(), d["pitch"])
        self.finger_note.config(text="" if ok else "This fingering isn't confirmed for your model yet -- "
                                                   "check your ocarina's own chart.")
        self._show_takes()

    def _show_takes(self):
        d = self._current()
        ts = self.takes.get(d["button"], [])
        self.takes_lbl.config(text="  ".join(f"{t['hz']:.1f}Hz (±{t['spread_cents']/2:.0f}¢)" for t in ts)
                              or f"Record {TAKES_PER_NOTE} takes, then Save note.")

    def _record(self):
        d = self._current()
        if not d or not self.app.monitor or self.app._busy:
            return
        self.app._busy = True
        self.app.monitor_paused = True
        self.rec_btn.state(["disabled"])
        params = config.match_params(self.app.cfg)
        self.rec_lbl.config(text="Get ready…")
        self.app.after(700, lambda: self.rec_lbl.config(text="▶ PLAY and hold the note…"))

        def work():
            time.sleep(0.7)
            return calibration.record_take(self.app.monitor, params, seconds=2.0)

        def done(take):
            self.app._busy = False
            self.app.monitor_paused = False
            self.rec_btn.state(["!disabled"])
            if take is None:
                self.rec_lbl.config(text="Didn't hear a steady note -- try again (check the level on Setup).")
                return
            self.takes.setdefault(d["button"], []).append(take)
            n = len(self.takes[d["button"]])
            self.rec_lbl.config(text=f"Got {take['hz']:.1f} Hz" +
                                (" -- one more!" if n < TAKES_PER_NOTE else " -- Save note when ready."))
            self._show_takes()
            if n >= TAKES_PER_NOTE:
                self._save_note()

        self.app.run_bg(work, done)

    def _clear(self):
        d = self._current()
        self.takes.pop(d["button"], None)
        self._show_takes()

    def _save_note(self):
        d = self._current()
        ts = self.takes.get(d["button"], [])
        if not ts:
            return
        self.app.cfg["notes"][d["button"]] = calibration.combine(ts)
        self.app.cfg["ocarina"] = self.profile.get()
        self.app.save()
        self.takes.pop(d["button"], None)
        self.rec_lbl.config(text=f"Saved {d['button']} = {self.app.cfg['notes'][d['button']]['hz']:.1f} Hz")
        self._fill()
        self._show_takes()


# ---- Test ----------------------------------------------------------------
class TestTab(Tab):
    def __init__(self, parent, app):
        super().__init__(parent, app)
        ttk.Label(self, text="Live detection -- nothing is sent to the game here.", foreground="#666").pack(anchor="w")
        self.hz = ttk.Label(self, text="--", font=BIG)
        self.hz.pack(pady=(10, 0))
        self.near = ttk.Label(self, text="", font=MID)
        self.near.pack()
        self.cents = tk.Canvas(self, width=400, height=24, bg="#eee", highlightthickness=0)
        self.cents.pack(pady=4)
        self.press = ttk.Label(self, text="", font=BIG, foreground="#16a")
        self.press.pack(pady=6)
        song = ttk.LabelFrame(self, text="Song practice", padding=8)
        song.pack(fill="x", pady=8)
        self.song = ttk.Combobox(song, values=list(config.SONGS), state="readonly", width=24)
        self.song.set("Zelda's Lullaby")
        self.song.pack(side="left")
        self.song.bind("<<ComboboxSelected>>", lambda e: self._reset_song())
        self.seq_lbl = ttk.Label(song, font=MID)
        self.seq_lbl.pack(side="left", padx=12)
        self.log = tk.Text(self, height=6, state="disabled")
        self.log.pack(fill="both", expand=True)
        self.matcher = None
        self.progress = 0

    def on_show(self):
        self.matcher = NoteMatcher(config.note_freqs(self.app.cfg), config.match_params(self.app.cfg))
        self._reset_song()

    def _reset_song(self):
        self.progress = 0
        self._draw_song()

    def _draw_song(self, done=False):
        seq = config.SONGS[self.song.get()]
        parts = [f"[{b}]" if i < self.progress else b for i, b in enumerate(seq)]
        self.seq_lbl.config(text="  ".join(parts) + ("   ✔ played!" if done else ""))

    def _log(self, text):
        self.log.config(state="normal")
        self.log.insert("end", text + "\n")
        self.log.see("end")
        self.log.config(state="disabled")

    def on_readings(self, readings):
        if not self.matcher:
            self.on_show()
        if self.app.game_audio:
            self.app.game_audio.annotate(readings, self.matcher.gate_level())
        last = None
        for r in readings:
            d = self.matcher.update(r)
            last = d
            for kind, key in d.events:
                if kind == "press":
                    self._log(f"press {key}   ({d.freq:.1f} Hz)")
                    seq = config.SONGS[self.song.get()]
                    if key == seq[self.progress]:
                        self.progress += 1
                    else:
                        self.progress = 1 if key == seq[0] else 0
                    if self.progress == len(seq):
                        self._draw_song(done=True)
                        self.progress = 0
                    else:
                        self._draw_song()
        if last:
            self.hz.config(text=f"{last.freq:.1f} Hz" if last.voiced else "--")
            if last.voiced and last.nearest:
                self.near.config(text=f"nearest {last.nearest}  {last.offset_cents:+.0f}¢" +
                                      ("   (game sound -- ignored)" if last.echo else ""))
                x = 200 + max(-190, min(190, last.offset_cents * 2))
                self.cents.delete("all")
                self.cents.create_line(200, 0, 200, 24, fill="#999")
                self.cents.create_oval(x - 7, 5, x + 7, 19, fill="#16a", outline="")
            else:
                self.near.config(text="")
                self.cents.delete("all")
            self.press.config(text=f"pressing {last.held}" if last.held else "")


# ---- Play ----------------------------------------------------------------
class PlayTab(Tab):
    def __init__(self, parent, app):
        super().__init__(parent, app)
        mode = ttk.LabelFrame(self, text="When to listen", padding=8)
        mode.pack(fill="x")
        self.mode = tk.StringVar(value=app.cfg["gate_mode"])
        for value, text in [("game", "Only while the ocarina is up in-game (game flag)"),
                            ("hotkey", "While Scroll Lock is on"),
                            ("always", "Always (testing only -- sounds can move your character)")]:
            ttk.Radiobutton(mode, text=text, value=value, variable=self.mode,
                            command=self._mode_changed).pack(anchor="w")
        self.btn = ttk.Button(self, text="Start", command=self._toggle)
        self.btn.pack(pady=10)
        self.gate = ttk.Label(self, text="stopped", font=MID)
        self.gate.pack()
        self.held = ttk.Label(self, text="", font=BIG, foreground="#16a")
        self.held.pack(pady=6)
        self.log = tk.Text(self, height=10, state="disabled")
        self.log.pack(fill="both", expand=True)

    def _mode_changed(self):
        self.app.cfg["gate_mode"] = self.mode.get()
        self.app.save()

    def _toggle(self):
        if self.app.engine:
            self.app.engine.stop()
            self.app.engine = None
            self.btn.config(text="Start")
            self.gate.config(text="stopped")
            self.held.config(text="")
            self.app.start_monitor()
            return
        if not config.note_freqs(self.app.cfg):
            messagebox.showwarning("Ocarina Translator", "Calibrate your notes first (Calibrate tab).")
            return
        if not setup_helpers.vigem_installed():
            messagebox.showwarning("Ocarina Translator", "Install the ViGEmBus driver first (Setup tab).")
            return
        self.app.stop_monitor()
        try:
            self.app.engine = Engine(self.app.cfg)
            self.app.engine.start()
        except Exception as e:
            self.app.engine = None
            self.app.start_monitor()
            messagebox.showerror("Ocarina Translator", f"Couldn't start: {e}")
            return
        self.btn.config(text="Stop")
        self._log(f"Started -- mic: {self.app.engine.mic_label}")

    def _log(self, text):
        self.log.config(state="normal")
        self.log.insert("end", time.strftime("%H:%M:%S  ") + text + "\n")
        self.log.see("end")
        self.log.config(state="disabled")

    def tick(self):
        eng = self.app.engine
        if not eng:
            return
        last = None
        while True:
            try:
                item = eng.status.get_nowait()
            except queue.Empty:
                break
            if item[0] == "gate":
                self._log(("listening" if item[1] else "not listening") + f"  ({item[2]})")
            else:
                last = item[1]
                for kind, key in last.events:
                    if kind == "press":
                        self._log(f"press {key}")
        self.gate.config(text=("● listening" if eng.gate_state == "on" else "○ not listening") +
                              f"   [{eng.gate_note}]")
        if last is not None:
            self.held.config(text=last.held or "")


# ---- Game flag -----------------------------------------------------------
class FlagTab(Tab):
    STEPS = [
        ("down", "Put the ocarina AWAY, then click Capture."),
        ("up", "Bring the ocarina UP (don't play anything), then click Capture."),
    ]

    def __init__(self, parent, app):
        super().__init__(parent, app)
        ttk.Label(self, wraplength=820, justify="left", text=(
            "The translator reads a value in Longshot's memory to know when the ocarina is up. It moves every "
            "time Longshot is relaunched -- if 'Value now' doesn't change when you take the ocarina out, run "
            "the scan below (Longshot must be running; the first capture briefly uses a few GB of RAM).")
        ).pack(anchor="w")
        cur = ttk.LabelFrame(self, text="Current flag", padding=8)
        cur.pack(fill="x", pady=8)
        self.cur_lbl = ttk.Label(cur, font=MID)
        self.cur_lbl.pack(anchor="w")

        scan = ttk.LabelFrame(self, text="Find it again", padding=8)
        scan.pack(fill="both", expand=True)
        self.instr = ttk.Label(scan, font=MID, wraplength=800)
        self.instr.pack(anchor="w")
        row = ttk.Frame(scan)
        row.pack(anchor="w", pady=6)
        self.start_btn = ttk.Button(row, text="Start scan", command=self._start)
        self.start_btn.pack(side="left")
        self.cap_btn = ttk.Button(row, text="Capture", command=self._capture)
        self.cap_btn.pack(side="left", padx=4)
        self.play_btn = ttk.Button(row, text="Verify while playing (6s)", command=self._verify_play)
        self.play_btn.pack(side="left", padx=4)
        self.use_btn = ttk.Button(row, text="Use this flag", command=self._use)
        self.use_btn.pack(side="left", padx=4)
        self.result = ttk.Label(scan, wraplength=800, justify="left")
        self.result.pack(anchor="w")
        self.scanner = None
        self.step = 0
        self.flag = None
        self.best = None
        self._last_poll = 0
        self.instr.config(text="With Longshot running and your save loaded, click Start scan. It takes 2-4 "
                               "rounds of putting the ocarina away and taking it out.")
        self._set_buttons(idle=True)

    def _set_buttons(self, idle=False, capture=False, verify=False, use=False):
        self.start_btn.state(["!disabled"] if idle else ["disabled"])
        self.cap_btn.state(["!disabled"] if capture else ["disabled"])
        self.play_btn.state(["!disabled"] if verify else ["disabled"])
        self.use_btn.state(["!disabled"] if use else ["disabled"])

    def on_show(self):
        f = self.app.cfg["flag"]
        self.flag = GameFlag(f["address"], f["up_value"], f["down_value"])

    def tick(self):
        if not self.flag or self.scanner or time.monotonic() - self._last_poll < 0.2:
            return
        self._last_poll = time.monotonic()
        up = self.flag.read()
        addr = self.app.cfg["flag"]["address"]
        state = {True: "ocarina UP", False: "put away", None: "can't read (stale address or game closed)"}[up]
        self.cur_lbl.config(text=f"Address {hex(addr) if addr else '(none)'}   Value now: "
                                 f"{self.flag.last_raw if self.flag.last_raw is not None else '--'}  → {state}")

    def _progress(self, msg):
        self.app.ui_queue.put(lambda: self.result.config(text=msg))

    def _start(self):
        if not game_running():
            messagebox.showwarning("Ocarina Translator", "Start Longshot and load your save first.")
            return
        if self.app.engine:
            messagebox.showwarning("Ocarina Translator", "Stop the Play tab first.")
            return
        self.scanner = FlagScanner(progress=self._progress)
        self.step = 0
        self._set_buttons(capture=True)
        self.instr.config(text=self.STEPS[0][1])

    def _capture(self):
        state, _ = self.STEPS[self.step % 2]
        self._set_buttons()
        self.instr.config(text="Capturing… keep the ocarina where it is.")

        def done(_):
            self.step += 1
            n = self.scanner.count()
            if state == "up" and n is not None and n <= 40:
                self.instr.config(text="Down to a few candidates. Hold the ocarina UP and PLAY a few notes, "
                                       "then click Verify while playing.")
                self._set_buttons(capture=True, verify=True)
            elif state == "up" and n == 0:
                self.instr.config(text="Nothing matched -- the ocarina may have been in the wrong state. Start again.")
                self.scanner = None
                self._set_buttons(idle=True)
            else:
                self.instr.config(text=self.STEPS[self.step % 2][1])
                self._set_buttons(capture=True)

        def err(msg):
            self.scanner = None
            self._set_buttons(idle=True)
            messagebox.showerror("Ocarina Translator", f"Scan failed: {msg}")

        self.app.run_bg(lambda: self.scanner.capture(state), done, err)

    def _verify_play(self):
        self._set_buttons()
        self.instr.config(text="Keep playing notes with the ocarina up…")

        def work():
            self.scanner.verify_while_playing(seconds=6.0)
            self.app.ui_queue.put(lambda: self.instr.config(
                text="Now put the ocarina AWAY and leave it there for a few seconds…"))
            time.sleep(2.5)
            self.scanner.verify_down(seconds=2.0)
            return self.scanner.best()

        def done(best):
            if not best:
                self.instr.config(text="No candidate survived -- start the scan again.")
                self.scanner = None
                self._set_buttons(idle=True)
                return
            steady = [a for a, s in self.scanner.steady.items() if s >= 0.98 and
                      any(a == x[0] for x in self.scanner.addresses())]
            self.best = best
            more = len(steady) > 1
            self.instr.config(text=(f"Found {hex(best['address'])} (steady while playing: "
                                    f"{best['steadiness'] * 100:.0f}%)." +
                                    ("  Several still match -- do another Capture round to be sure, or use it."
                                     if more else "")))
            self.step = 0
            self._set_buttons(capture=more, use=True)

        self.app.run_bg(work, done)

    def _use(self):
        b = self.best
        self.app.cfg["flag"] = {"address": b["address"], "up_value": b["up_value"], "down_value": b["down_value"]}
        if b["steadiness"] >= 0.98:
            self.app.cfg["flag_grace_seconds"] = 0.15   # steady flag -- barely any grace needed
        self.app.save()
        self.scanner = None
        self._set_buttons(idle=True)
        self.instr.config(text="Saved. The Play tab will use it next time you press Start.")
        self.on_show()


# ---- Advanced ------------------------------------------------------------
class AdvancedTab(Tab):
    FIELDS = [
        ("match", "stable_seconds", "Note must hold steady for (ms)", 1000, 10, 150),
        ("match", "stable_spread_cents", "…within (cents)", 1, 10, 80),
        ("match", "release_seconds", "Release after silence of (ms)", 1000, 20, 300),
        ("", "min_hold_seconds", "Minimum button press (ms)", 1000, 30, 300),
        ("", "flag_grace_seconds", "Game-flag grace when it flickers (ms)", 1000, 0, 1000),
        ("match", "max_window_cents", "Widest note window (cents)", 1, 30, 200),
        ("match", "sticky_cents", "Held-note stickiness (cents)", 1, 0, 60),
        ("match", "level_margin", "Loudness needed (× background)", 1, 1.5, 10),
        ("match", "min_conf", "Tone clarity needed (0-1)", 1, 0.5, 0.99),
        ("match", "release_level_ratio", "Release when breath drops below (× its peak)", 1, 0.05, 0.9),
        ("match", "echo_override", "Game-sound pitch still counts if louder than (× threshold)", 1, 1, 20),
        ("match", "max_hold_seconds", "Longest a note can be held (s)", 1, 1, 15),
    ]

    def __init__(self, parent, app):
        super().__init__(parent, app)
        ttk.Label(self, wraplength=820, justify="left", foreground="#666", text=(
            "Faster = lower 'hold steady'. Fewer stray presses while a note starts = higher 'hold steady' or "
            "lower 'within'. Changes apply next time you press Start / open the Test tab.")).pack(anchor="w")
        grid = ttk.Frame(self)
        grid.pack(anchor="w", pady=8)
        self.vars = {}
        for i, (sec, key, label, scale, lo, hi) in enumerate(self.FIELDS):
            ttk.Label(grid, text=label).grid(row=i, column=0, sticky="w", pady=3)
            v = tk.DoubleVar()
            self.vars[(sec, key)] = (v, scale)
            ttk.Spinbox(grid, textvariable=v, from_=lo, to=hi, increment=(1 if scale > 1 or hi > 5 else 0.01),
                        width=8).grid(row=i, column=1, sticky="w", padx=8)
        row = ttk.Frame(self)
        row.pack(anchor="w")
        ttk.Button(row, text="Save", command=self._save).pack(side="left")
        ttk.Button(row, text="Reset to defaults", command=self._reset).pack(side="left", padx=6)
        self._load()

    def _get(self, sec, key):
        return self.app.cfg[sec][key] if sec else self.app.cfg[key]

    def _load(self):
        for (sec, key), (v, scale) in self.vars.items():
            v.set(round(self._get(sec, key) * scale, 3))

    def on_show(self):
        self._load()

    def _save(self):
        for (sec, key), (v, scale) in self.vars.items():
            try:
                val = float(v.get()) / scale
            except (tk.TclError, ValueError):
                continue
            if sec:
                self.app.cfg[sec][key] = val
            else:
                self.app.cfg[key] = val
        self.app.save()
        self.app.set_status("Settings saved.")

    def _reset(self):
        noise = self.app.cfg["match"]["noise_floor"]
        self.app.cfg["match"] = asdict(MatchParams(noise_floor=noise))
        self.app.cfg["min_hold_seconds"] = config.DEFAULTS["min_hold_seconds"]
        self.app.cfg["flag_grace_seconds"] = config.DEFAULTS["flag_grace_seconds"]
        self.app.save()
        self._load()


if __name__ == "__main__":
    App().mainloop()

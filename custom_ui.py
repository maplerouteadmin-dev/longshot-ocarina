"""Custom mappings editor (hidden section on the Play tab).

Map any pitch you can play to any controller input -- d-pad, sticks, triggers,
Start, anything -- either held for as long as you hold the note, or for a set
time (e.g. a note pushes the left stick forward for 10 s). Stored in
config "custom": [{name, hz, input, x, y, amount, mode, seconds, delay,
when_away, enabled}]. The engine picks them up when Play is (re)started.
"""
import statistics
import time
import tkinter as tk
from tkinter import messagebox, ttk

import config
import gamepad
import pitch

NAMES = ["C", "C#", "D", "D#", "E", "F", "F#", "G", "G#", "A", "A#", "B"]
NOTE_HZ = {f"{n}{o}": 440.0 * 2 ** (((o + 1) * 12 + i - 69) / 12)
           for o in range(3, 8) for i, n in enumerate(NAMES)}
LISTEN_SECONDS = 1.5


def note_name(hz):
    midi = round(69 + pitch.cents(hz) / 100)
    return f"{NAMES[midi % 12]}{midi // 12 - 1}"


def _blank():
    return {"name": "New mapping", "hz": 0.0, "input": "D-pad left", "x": 0.0, "y": 1.0, "amount": 1.0,
            "mode": "hold", "seconds": 1.0, "delay": 0.0, "when_away": True, "enabled": True}


class CustomMappings:
    def __init__(self, parent, app):
        self.app = app
        self.frame = ttk.Frame(parent)
        self.listening_until = 0.0
        self.heard = []
        self.sel = None

        ttk.Label(self.frame, wraplength=820, justify="left", foreground="#666", text=(
            "Map any pitch to any controller input. 'Hold' presses it while you hold the note; 'Timed' "
            "presses it for a set time (e.g. push the left stick forward for 10 s). Changes apply the next "
            "time you press Start. Names are the Xbox inputs -- with a Switch-style layout Longshot treats "
            "A/B and X/Y as swapped.")).pack(anchor="w")

        body = ttk.Frame(self.frame)
        body.pack(fill="x", pady=(6, 0))
        self.tree = ttk.Treeview(body, columns=("pitch", "input", "mode"), height=5, selectmode="browse")
        self.tree.heading("#0", text="Name")
        self.tree.heading("pitch", text="Pitch")
        self.tree.heading("input", text="Input")
        self.tree.heading("mode", text="Mode")
        self.tree.column("#0", width=150)
        for c, w in (("pitch", 110), ("input", 140), ("mode", 150)):
            self.tree.column(c, width=w)
        self.tree.pack(side="left", fill="y")
        self.tree.bind("<<TreeviewSelect>>", lambda e: self._load_selected())
        btns = ttk.Frame(body)
        btns.pack(side="left", padx=8, anchor="n")
        ttk.Button(btns, text="New", command=self._new).pack(fill="x")
        ttk.Button(btns, text="Delete", command=self._delete).pack(fill="x", pady=4)

        ed = ttk.Frame(self.frame)
        ed.pack(fill="x", pady=(8, 0))
        self.v = {k: tk.StringVar() for k in ("name", "hz", "note", "input", "seconds", "delay")}
        self.v_mode = tk.StringVar(value="hold")
        self.v_x, self.v_y, self.v_amt = tk.DoubleVar(), tk.DoubleVar(value=1.0), tk.DoubleVar(value=1.0)
        self.v_away, self.v_on = tk.BooleanVar(value=True), tk.BooleanVar(value=True)

        r = 0
        ttk.Label(ed, text="Name").grid(row=r, column=0, sticky="w")
        ttk.Entry(ed, textvariable=self.v["name"], width=24).grid(row=r, column=1, columnspan=3, sticky="w")
        r += 1
        ttk.Label(ed, text="Pitch (Hz)").grid(row=r, column=0, sticky="w", pady=2)
        ttk.Entry(ed, textvariable=self.v["hz"], width=10).grid(row=r, column=1, sticky="w")
        note = ttk.Combobox(ed, textvariable=self.v["note"], values=list(NOTE_HZ), width=6, state="readonly")
        note.grid(row=r, column=2, sticky="w", padx=4)
        note.bind("<<ComboboxSelected>>", lambda e: self.v["hz"].set(f"{NOTE_HZ[self.v['note'].get()]:.1f}"))
        self.listen_btn = ttk.Button(ed, text=f"Listen ({LISTEN_SECONDS:g}s)", command=self._listen)
        self.listen_btn.grid(row=r, column=3, sticky="w")
        self.listen_lbl = ttk.Label(ed, foreground="#666")
        self.listen_lbl.grid(row=r, column=4, sticky="w", padx=6)
        r += 1
        ttk.Label(ed, text="Input").grid(row=r, column=0, sticky="w", pady=2)
        ttk.Combobox(ed, textvariable=self.v["input"], values=gamepad.ALL_INPUTS, width=18,
                     state="readonly").grid(row=r, column=1, columnspan=2, sticky="w")
        r += 1
        ttk.Label(ed, text="Stick direction").grid(row=r, column=0, sticky="w")
        sf = ttk.Frame(ed)
        sf.grid(row=r, column=1, columnspan=4, sticky="w")
        for lbl, var in (("left/right", self.v_x), ("down/up", self.v_y)):
            ttk.Label(sf, text=lbl).pack(side="left")
            ttk.Scale(sf, from_=-1, to=1, variable=var, length=110).pack(side="left", padx=(2, 10))
        ttk.Label(sf, text="trigger amount").pack(side="left")
        ttk.Scale(sf, from_=0, to=1, variable=self.v_amt, length=90).pack(side="left", padx=2)
        r += 1
        ttk.Label(ed, text="Timing").grid(row=r, column=0, sticky="w", pady=2)
        tf = ttk.Frame(ed)
        tf.grid(row=r, column=1, columnspan=4, sticky="w")
        ttk.Radiobutton(tf, text="Hold while the note is held", value="hold", variable=self.v_mode).pack(side="left")
        ttk.Radiobutton(tf, text="Timed for", value="timed", variable=self.v_mode).pack(side="left", padx=(10, 2))
        ttk.Entry(tf, textvariable=self.v["seconds"], width=5).pack(side="left")
        ttk.Label(tf, text="s     delay before").pack(side="left", padx=2)
        ttk.Entry(tf, textvariable=self.v["delay"], width=5).pack(side="left")
        ttk.Label(tf, text="s").pack(side="left")
        r += 1
        of = ttk.Frame(ed)
        of.grid(row=r, column=0, columnspan=5, sticky="w", pady=(2, 0))
        ttk.Button(of, text="Save mapping", command=self._save).pack(side="left")
        ttk.Label(of, text="Mappings also work with the ocarina put away (switch on the Play tab).",
                  foreground="#666").pack(side="left", padx=10)
        self._refresh_list()

    # -- list ------------------------------------------------------------------
    @property
    def maps(self):
        return self.app.cfg.setdefault("custom", [])

    def _refresh_list(self, select=None):
        self.tree.delete(*self.tree.get_children())
        for i, m in enumerate(self.maps):
            hz = float(m.get("hz") or 0)
            mode = "hold" if m.get("mode") != "timed" else f"timed {m.get('seconds', 1)}s"
            if float(m.get("delay") or 0):
                mode += f", +{m['delay']}s delay"
            name = m.get("name", "") + ("" if m.get("enabled", True) else "  (off)")
            self.tree.insert("", "end", iid=str(i), text=name,
                             values=(f"{hz:.1f} Hz ({note_name(hz)})" if hz else "--", m.get("input"), mode))
        if select is not None and str(select) in self.tree.get_children():
            self.tree.selection_set(str(select))

    def _load_selected(self):
        sel = self.tree.selection()
        if not sel:
            return
        self.sel = int(sel[0])
        m = {**_blank(), **self.maps[self.sel]}
        for k in ("name", "input"):
            self.v[k].set(m[k])
        self.v["hz"].set(f"{float(m['hz']):.1f}" if m["hz"] else "")
        self.v["note"].set("")
        self.v["seconds"].set(str(m["seconds"]))
        self.v["delay"].set(str(m["delay"]))
        self.v_mode.set(m["mode"])
        self.v_x.set(m["x"]), self.v_y.set(m["y"]), self.v_amt.set(m["amount"])
        self.v_away.set(m["when_away"]), self.v_on.set(m["enabled"])

    def _new(self):
        self.maps.append(_blank())
        self.app.save()
        self._refresh_list(select=len(self.maps) - 1)
        self._load_selected()

    def _delete(self):
        if self.sel is None or self.sel >= len(self.maps):
            return
        del self.maps[self.sel]
        self.sel = None
        self.app.save()
        self._refresh_list()

    def _save(self):
        if self.sel is None:
            self._new()
        try:
            hz = float(self.v["hz"].get() or 0)
            seconds = float(self.v["seconds"].get() or 1)
            delay = float(self.v["delay"].get() or 0)
        except ValueError:
            messagebox.showwarning("Ocarina Translator", "Pitch, time and delay must be numbers.")
            return
        if hz <= 0:
            messagebox.showwarning("Ocarina Translator", "Set a pitch: type it, pick a note, or click Listen.")
            return
        clash = [d["label"] for d in config.NOTE_DEFS
                 if self.app.cfg["notes"].get(d["button"], {}).get("hz")
                 and abs(pitch.cents(hz) - pitch.cents(self.app.cfg["notes"][d["button"]]["hz"])) < 60]
        if clash and not messagebox.askyesno("Ocarina Translator", f"That pitch is very close to your "
                                             f"{', '.join(clash)} note, so they may get mixed up. Save anyway?"):
            return
        self.maps[self.sel] = {
            "name": self.v["name"].get().strip() or "Mapping", "hz": round(hz, 2), "input": self.v["input"].get(),
            "x": round(self.v_x.get(), 2), "y": round(self.v_y.get(), 2), "amount": round(self.v_amt.get(), 2),
            "mode": self.v_mode.get(), "seconds": max(0.05, seconds), "delay": max(0.0, delay),
            "when_away": True, "enabled": True}
        self.app.save()
        self._refresh_list(select=self.sel)
        if self.app.engine:
            self.listen_lbl.config(text="Saved -- press Stop then Start to use it.")

    # -- capture a pitch from the mic -----------------------------------------
    def _listen(self):
        if self.app.engine or not self.app.monitor:
            messagebox.showwarning("Ocarina Translator", "Stop playing first (the mic is in use), then Listen.")
            return
        self.heard = []
        self.listening_until = time.monotonic() + LISTEN_SECONDS
        self.listen_lbl.config(text="play the note now…")

    def on_readings(self, readings):
        if not self.listening_until:
            return
        p = config.match_params(self.app.cfg)
        gate = max(p.min_level, p.noise_floor * p.level_margin)
        self.heard += [r.freq for r in readings if r.freq and r.conf >= p.min_conf and r.level >= gate]
        if time.monotonic() >= self.listening_until:
            self.listening_until = 0.0
            if len(self.heard) < 5:
                self.listen_lbl.config(text="didn't hear a clear note -- try again")
                return
            hz = statistics.median(self.heard)
            self.v["hz"].set(f"{hz:.1f}")
            self.listen_lbl.config(text=f"heard {hz:.1f} Hz ({note_name(hz)}) -- click Save mapping")

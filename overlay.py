"""Fingering pop-up: shows note fingerings over the game while the ocarina is up.

Styled after Longshot's own ocarina screen: a dark translucent panel with a
thin warm-gold edge, cream text, and the same white button chips the game uses
in its "Play a note  LB RB X Y B" prompt. It sits in the empty space left of
Link, fades in when the ocarina comes up and out when it's lowered, never takes
focus from the game and isn't in the taskbar. Drag it to move it; the spot is
remembered relative to Longshot's window.

Only notes not marked as learned are shown (config "overlay": {"enabled",
"learned": [buttons], "fx", "fy"}). Longshot must be windowed or borderless.
"""
import ctypes
import sys
import threading
import time
import tkinter as tk

from PIL import Image, ImageDraw, ImageFont, ImageTk

import config
import diagram
import fingering
import gamewin
from ocarina_flag import GameFlag

GAME_ORDER = ["LB", "RB", "X", "Y", "B"]       # order of the game's own note prompt
KEY = "#0b0c0e"                                # transparent key colour (close to the panel, hides AA fringe)
PANEL = (22, 23, 27)
GOLD = (190, 156, 102)
CREAM = (238, 230, 212)
MUTED = (150, 146, 136)
ALPHA = 0.82
POLL = 0.15
FADE_IN, FADE_OUT = 7, 4                       # frames (~40 ms each)
S = 4                                          # supersample: smooth edges, crisp when scaled up
MIN_SCALE, MAX_SCALE = 0.6, 2.0


def _font(size, bold=False):
    return diagram.load_font(size * S, bold)


def _chip(d, x, y, label):
    """White button chip like the game's prompt: circle for X/Y/B, pill for LB/RB."""
    f = _font(13, bold=True)
    h = 26 * S
    w = h if len(label) == 1 else 44 * S
    if len(label) == 1:
        d.ellipse([x, y, x + w, y + h], fill=(245, 245, 242))
    else:
        d.rounded_rectangle([x, y, x + w, y + h], radius=8 * S, fill=(245, 245, 242))
    tb = d.textbbox((0, 0), label, font=f)
    d.text((x + (w - (tb[2] - tb[0])) / 2 - tb[0], y + (h - (tb[3] - tb[1])) / 2 - tb[1]), label,
           fill=(30, 30, 32), font=f)
    return w


def _hole(d, cx, cy, r, covered):
    box = [cx - r, cy - r, cx + r, cy + r]
    if covered:
        d.ellipse(box, fill=CREAM)
    else:
        d.ellipse(box, outline=CREAM, width=2 * S)


def render_panel(notes, profile, scale=1.0):
    """One image with a header and a row per note: chip, game name, pitch, fingering."""
    row_h, width, top = 96, 340, 50
    H = top + row_h * len(notes) + 12
    img = Image.new("RGB", (width * S, H * S), KEY)
    d = ImageDraw.Draw(img)
    d.rounded_rectangle([0, 0, width * S - 1, H * S - 1], radius=14 * S, fill=PANEL, outline=GOLD, width=S)
    # header: "Fingerings" between two thin gold rules, like the game's banners
    f = _font(15)
    title = "Fingerings"
    tb = d.textbbox((0, 0), title, font=f)
    tw = tb[2] - tb[0]
    cx = width * S / 2
    d.text((cx - tw / 2 - tb[0], 12 * S - tb[1]), title, fill=CREAM, font=f)
    ly = 12 * S + (tb[3] - tb[1]) / 2
    d.line([22 * S, ly, cx - tw / 2 - 12 * S, ly], fill=GOLD, width=S)
    d.line([cx + tw / 2 + 12 * S, ly, width * S - 22 * S, ly], fill=GOLD, width=S)

    name_f, pitch_f, tiny, hand_f = _font(14, bold=True), _font(12), _font(10), _font(10, bold=True)
    for i, n in enumerate(notes):
        y0 = (top + i * row_h) * S
        if i:
            d.line([22 * S, y0 - 4 * S, width * S - 22 * S, y0 - 4 * S], fill=(48, 47, 44), width=S)
        cy = y0 + (row_h / 2 + 4) * S
        _chip(d, 20 * S, cy - 13 * S, n["button"])
        d.text((76 * S, cy - 20 * S), n["label"], fill=CREAM, font=name_f)
        d.text((76 * S, cy + 2 * S), n["pitch"], fill=MUTED, font=pitch_f)
        covered = set(fingering.holes(profile, n["pitch"]) or [])
        # front: two columns of four (left hand, right hand), centred on the row
        r, gx, gy = 7 * S, 20 * S, 17 * S
        fx = 214 * S
        fy = cy - 1.5 * gy
        for k in range(4):
            _hole(d, fx, fy + k * gy, r, f"L{k + 1}" in covered)
            _hole(d, fx + gx, fy + k * gy, r, f"R{k + 1}" in covered)
        # back: thumbs
        tx = 278 * S
        _hole(d, tx, cy - 6 * S, r, "TL" in covered)
        _hole(d, tx + gx, cy - 6 * S, r, "TR" in covered)
        tb = d.textbbox((0, 0), "thumbs", font=tiny)
        d.text((tx + gx / 2 - (tb[2] - tb[0]) / 2, cy + 6 * S), "thumbs", fill=MUTED, font=tiny)
        # L / R above each column (left/right hand), and above each thumb hole
        for x, top_y in ((fx, fy), (fx + gx, fy), (tx, cy - 6 * S), (tx + gx, cy - 6 * S)):
            t = "L" if x in (fx, tx) else "R"
            lb = d.textbbox((0, 0), t, font=hand_f)
            d.text((x - (lb[2] - lb[0]) / 2 - lb[0], top_y - r - 4 * S - (lb[3] - lb[1]) - lb[1]), t,
                   fill=GOLD, font=hand_f)
    # resize grip in the bottom-right corner: three short gold diagonals
    for k in (6, 11, 16):
        d.line([width * S - (5 + k) * S, H * S - 5 * S, width * S - 5 * S, H * S - (5 + k) * S],
               fill=GOLD, width=S)
    return img.resize((max(1, int(width * scale)), max(1, int(H * scale))), Image.LANCZOS)


# ---- Longshot's window ------------------------------------------------------
IS_WINDOWS = sys.platform == "win32"


def game_window_rect():
    """(left, top, right, bottom) of Longshot's window, or None (Linux: X11 with xdotool only)."""
    return gamewin.game_window()[1]


class FingeringOverlay:
    def __init__(self, app):
        self.app = app
        self.win = None
        self.label = None
        self.photo = None
        self._up = False
        self._rect = None          # Longshot window rect, refreshed by the poll thread
        self._shown = False
        self._alpha = 0.0
        self._stop = threading.Event()
        self._thread = None
        self._drag = None
        self._built_for = None
        self.on_scale = None       # callback so the Play tab slider follows wheel resizing

    @property
    def cfg(self):
        return self.app.cfg.setdefault("overlay", {"enabled": False, "learned": []})

    def pending_notes(self):
        learned = set(self.cfg.get("learned", []))
        defs = {d["button"]: d for d in config.NOTE_DEFS}
        return [defs[b] for b in GAME_ORDER if b in defs and b not in learned]

    def set_enabled(self, on):
        self.cfg["enabled"] = on
        self.app.save()
        self.start() if on else self.stop()

    def refresh(self):
        self._built_for = None

    def scale(self):
        return min(MAX_SCALE, max(MIN_SCALE, float(self.cfg.get("scale") or 1.0)))

    def set_scale(self, s, save=True):
        self.cfg["scale"] = round(min(MAX_SCALE, max(MIN_SCALE, s)), 2)
        if save:
            self.app.save()
        if self.on_scale:
            self.on_scale(self.cfg["scale"])

    def _in_grip(self, e):
        w, h = self.win.winfo_width(), self.win.winfo_height()
        g = 22 * self.scale()
        return e.x >= w - g and e.y >= h - g

    # -- background polling: flag state + game window position --------------
    def start(self):
        if self._thread and self._thread.is_alive():
            return
        self._stop.clear()
        self._thread = threading.Thread(target=self._poll, daemon=True)
        self._thread.start()

    def stop(self):
        self._stop.set()
        self._up = False

    def restart(self):
        """The chosen game changed: poll the new game's flag."""
        was_on = self.cfg.get("enabled")
        self.stop()
        if self._thread:
            self._thread.join(timeout=1)
        self._thread = None
        if was_on:
            self.start()

    def _poll(self):
        f = self.app.cfg["flag"]
        flag = GameFlag(f["address"], f["up_value"], f["down_value"])
        n = 0
        while not self._stop.is_set():
            try:
                self._up = bool(flag.read())
            except Exception:
                self._up = False
            if self._up and n % 7 == 0:     # window can move; check about once a second
                self._rect = game_window_rect()
            n += 1
            time.sleep(POLL)

    # -- window -------------------------------------------------------------
    def _ensure_window(self):
        if self.win is not None:
            return
        self.win = tk.Toplevel(self.app)
        self.win.withdraw()
        self.win.overrideredirect(True)
        self.win.configure(bg=KEY)
        self.win.attributes("-topmost", True)
        self.win.attributes("-alpha", 0.0)
        if IS_WINDOWS:    # rounded corners: Windows-only colour key; elsewhere the corners stay dark
            self.win.attributes("-transparentcolor", KEY)
        self.label = tk.Label(self.win, bg=KEY, bd=0)
        self.label.pack()
        for w in (self.win, self.label):
            w.bind("<ButtonPress-1>", self._drag_start)
            w.bind("<B1-Motion>", self._drag_move)
            w.bind("<ButtonRelease-1>", self._drag_end)
            w.bind("<Motion>", lambda e: self.label.config(
                cursor="size_nw_se" if self._in_grip(e) else "fleur"))
        self.win.update_idletasks()
        try:   # never take focus from the game; stay out of the taskbar and alt-tab
            u32 = ctypes.windll.user32
            hwnd = u32.GetParent(self.win.winfo_id()) or self.win.winfo_id()
            style = u32.GetWindowLongW(hwnd, -20)
            u32.SetWindowLongW(hwnd, -20, style | 0x08000000 | 0x00000080)
        except Exception:
            pass

    def _build(self):
        notes = self.pending_notes()
        key = (tuple(d["button"] for d in notes), self.scale())
        if self._built_for == key:
            return
        self._ensure_window()
        self.photo = ImageTk.PhotoImage(render_panel(notes, self.app.cfg.get("ocarina", "12-hole Alto C"),
                                                     self.scale()))
        self.label.config(image=self.photo)
        resized = self._built_for is not None and self._built_for[1] != key[1]
        self._built_for = key
        if resized and self._shown:
            self._place()

    def _place(self):
        """Position relative to the game window (default: left of Link, vertically centred)."""
        self.win.update_idletasks()
        w, h = self.win.winfo_reqwidth(), self.win.winfo_reqheight()
        r = self._rect or (0, 0, self.win.winfo_screenwidth(), self.win.winfo_screenheight())
        gw, gh = r[2] - r[0], r[3] - r[1]
        fx, fy = self.cfg.get("fx"), self.cfg.get("fy")
        if fx is None or fy is None:          # default: left of Link, vertically centred
            x, y = r[0] + 0.07 * gw, r[1] + (gh - h) / 2
        else:
            x, y = r[0] + fx * gw, r[1] + fy * gh
        self.win.geometry(f"+{int(x)}+{int(y)}")
        self._placed_for = r

    def _drag_start(self, e):
        if self._in_grip(e):   # corner grip: resize, keeping the top-left corner where it is
            self._resize = None
            self._drag = None
            self._drag_end(None)          # pin the current top-left so resizing doesn't re-centre it
            self._resize = (e.x_root, self.win.winfo_width(), self.scale())
        else:
            self._resize = None
            self._drag = (e.x_root - self.win.winfo_x(), e.y_root - self.win.winfo_y())

    def _drag_move(self, e):
        if getattr(self, "_resize", None):
            x0, w0, s0 = self._resize
            s = s0 * max(1, w0 + e.x_root - x0) / max(1, w0)
            now = time.monotonic()
            if abs(s - self.scale()) >= 0.02 and now - getattr(self, "_last_resize", 0) > 0.05:
                self._last_resize = now
                self.set_scale(s, save=False)
                self._build()
        elif self._drag:
            self.win.geometry(f"+{e.x_root - self._drag[0]}+{e.y_root - self._drag[1]}")

    def _drag_end(self, _e):
        if getattr(self, "_resize", None):
            self._resize = None
            self.app.save()
            return
        self._drag = None
        r = self._rect or (0, 0, self.win.winfo_screenwidth(), self.win.winfo_screenheight())
        gw, gh = max(1, r[2] - r[0]), max(1, r[3] - r[1])
        self.cfg["fx"] = (self.win.winfo_x() - r[0]) / gw
        self.cfg["fy"] = (self.win.winfo_y() - r[1]) / gh
        self.app.save()

    # -- called from the app's UI loop (~every 40 ms) -----------------------
    def tick(self):
        want = bool(self.cfg.get("enabled") and self._up and self.pending_notes())
        if want:
            self._build()
            if not self._shown:
                self._place()
                self.win.deiconify()
                self.win.attributes("-topmost", True)
                self._shown = True
            elif self._drag is None and self._rect != getattr(self, "_placed_for", None):
                self._place()     # game window moved or resized
        if self.win is None or not self._shown:
            return
        target = ALPHA if want else 0.0
        if abs(self._alpha - target) > 1e-3:
            step = ALPHA / (FADE_IN if want else FADE_OUT)
            self._alpha = min(target, self._alpha + step) if want else max(0.0, self._alpha - step)
            self.win.attributes("-alpha", self._alpha)
        elif not want:
            self.win.withdraw()
            self._shown = False

"""All user settings in one JSON file next to the app (or the .exe once packaged)."""
import json
import os
import sys
from dataclasses import asdict

from matcher import MatchParams

# The five OoT ocarina notes, the virtual Xbox button that plays each in Longshot
# (already includes the A/B and X/Y swap found in testing), the matching
# longshot_options.ini note slot, and the pad index to bind it to (copied from
# the user's own pad_* binding for that button).
NOTE_DEFS = [
    {"button": "LB", "label": "A-button note", "pitch": "D5", "ini_note": "pad_note_l", "ini_src": "pad_l"},
    {"button": "RB", "label": "C-Down", "pitch": "F5", "ini_note": "pad_note_r", "ini_src": "pad_r"},
    {"button": "B", "label": "C-Right", "pitch": "A5", "ini_note": "pad_note_a", "ini_src": "pad_a"},
    {"button": "X", "label": "C-Left", "pitch": "B5", "ini_note": "pad_note_y", "ini_src": "pad_y"},
    {"button": "Y", "label": "C-Up", "pitch": "D6", "ini_note": "pad_note_x", "ini_src": "pad_x"},
]

SONGS = {
    "Zelda's Lullaby": ["X", "Y", "B", "X", "Y", "B"],
    "Epona's Song": ["Y", "X", "B", "Y", "X", "B"],
    "Saria's Song": ["RB", "B", "X", "RB", "B", "X"],
    "Sun's Song": ["B", "RB", "Y", "B", "RB", "Y"],
    "Song of Time": ["B", "LB", "RB", "B", "LB", "RB"],
    "Song of Storms": ["LB", "RB", "Y", "LB", "RB", "Y"],
}


def app_dir():
    if getattr(sys, "frozen", False):
        return os.path.dirname(sys.executable)
    return os.path.dirname(os.path.abspath(__file__))


CONFIG_PATH = os.path.join(app_dir(), "config.json")

DEFAULTS = {
    "mic_name": "",
    "ocarina": "12-hole Alto C",
    "notes": {},            # button -> {"hz": mean, "spread_cents": float, "takes": [hz...]}
    "match": asdict(MatchParams()),
    "min_hold_seconds": 0.10,
    "switch_gap_seconds": 0.017,
    "gate_mode": "game",     # "game" (memory flag) | "hotkey" (Scroll Lock) | "always"
    "flag_grace_seconds": 0.40,
    "flag": {"address": None, "up_value": 0, "down_value": 1},
    "longshot_ini": "",
    "longshot_exe": "",       # remembered from the running game, for "Start Longshot"
    "noise_measured": False,
    # ignore pitches the game itself is playing (music, Link's note playback)
    # when the mic can hear the TV/speakers. device "" = Windows default output.
    "game_sound_filter": {"enabled": True, "device": ""},
    # fingering pop-up over the game while the ocarina is up; learned = buttons to hide
    "overlay": {"enabled": False, "learned": [], "x": None, "y": None},
}


def load():
    cfg = json.loads(json.dumps(DEFAULTS))
    if os.path.exists(CONFIG_PATH):
        with open(CONFIG_PATH, "r", encoding="utf-8") as f:
            saved = json.load(f)
        for k, v in saved.items():
            if isinstance(v, dict) and isinstance(cfg.get(k), dict):
                cfg[k].update(v)
            else:
                cfg[k] = v
    else:
        _migrate_old(cfg)
        save(cfg)
    return cfg


def save(cfg):
    tmp = CONFIG_PATH + ".tmp"
    with open(tmp, "w", encoding="utf-8") as f:
        json.dump(cfg, f, indent=2)
    os.replace(tmp, CONFIG_PATH)


def _migrate_old(cfg):
    """Carry over the earlier notes.json calibration and the found flag address."""
    old = os.path.join(app_dir(), "notes.json")
    if not os.path.exists(old):
        return
    with open(old, "r", encoding="utf-8") as f:
        for button, hz in json.load(f).items():
            cfg["notes"][button] = {"hz": hz, "spread_cents": 0.0, "takes": [hz]}
    # the original prototype's setup on the machine it was built on
    cfg["mic_name"] = "C922"
    cfg["flag"]["address"] = 0x1F812A0F784
    cfg["longshot_ini"] = r"A:\Games\longshot\longshot_options.ini"


def note_freqs(cfg):
    return {b: n["hz"] for b, n in cfg["notes"].items() if n.get("hz")}


def match_params(cfg):
    return MatchParams(**cfg["match"])

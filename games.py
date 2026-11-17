"""Game profiles: everything that differs between Ocarina of Time ports and emulators.

Each profile is a small JSON file in games/ (shipped with the app). Users can add
or override profiles by dropping JSON files into a `games` folder next to the app
(or next to config.json when running from source). Fields:

  id, name                 identifier and display name
  process  {windows, linux}  process names to look for
  window_title             regex used to find the game window (xdotool / fallback)
  settings_file            the game's options file next to its exe (null: none we manage)
  note_slots               true if the game has separate ocarina-note bindings (pad_note_*)
                           that must point at the controller buttons; false if the ocarina
                           already uses the game's normal A/L/R/X/Y buttons
  launcher {windows, linux, args}  glob patterns for a launcher, and its arguments
  flag {windows, linux}    "ocarina is up" offsets inside the emulated console's memory
                           (negative = counted from the end; empty = not found yet,
                           the manual scan on the Game Flag tab still works)
  setup_note               shown on the Setup tab when there's something to do by hand

The "Other" choice wraps any running program the user picks in a minimal profile.
"""
import glob
import json
import os
import sys
from dataclasses import dataclass, field

import config
import procmem

IS_WINDOWS = sys.platform == "win32"
DEFAULT_ID = "longshot"
CUSTOM_ID = "custom"


@dataclass
class Game:
    id: str
    name: str
    process: dict = field(default_factory=dict)
    window_title: str = ""
    settings_file: str | None = None
    note_slots: bool = False
    launcher: dict = field(default_factory=dict)
    flag: dict = field(default_factory=dict)
    setup_note: str = ""

    def process_names(self):
        names = self.process.get("windows" if IS_WINDOWS else "linux") or []
        if not IS_WINDOWS:   # Linux users sometimes run Windows builds under Wine/Proton
            names = list(names) + [n for n in self.process.get("windows", []) if n not in names]
        return tuple(names)

    def flag_offsets(self):
        return [int(str(o), 0) for o in self.flag.get("windows" if IS_WINDOWS else "linux", [])]

    def launcher_path(self):
        for pattern in self.launcher.get("windows" if IS_WINDOWS else "linux", []):
            hits = sorted(glob.glob(os.path.expandvars(os.path.expanduser(pattern))))
            if hits:
                return hits[-1]
        return None


def _bundled_dir():
    base = getattr(sys, "_MEIPASS", os.path.dirname(os.path.abspath(__file__)))
    return os.path.join(base, "games")


def _user_dir():
    return os.path.join(config.app_dir(), "games")


def load_all():
    """{id: Game} from the bundled profiles, then the user's folder (which can override)."""
    out = {}
    for folder in (_bundled_dir(), _user_dir()):
        for path in sorted(glob.glob(os.path.join(folder, "*.json"))):
            try:
                with open(path, encoding="utf-8") as f:
                    data = json.load(f)
                known = {k: v for k, v in data.items() if k in Game.__dataclass_fields__}
                g = Game(**known)
                out[g.id] = g
            except Exception as e:
                print(f"Skipping game profile {path}: {e}")
    return out


_all = None
_active = None


def all_games():
    global _all
    if _all is None:
        _all = load_all()
    return _all


def custom_game(process_name):
    name = process_name or "(pick a program)"
    return Game(id=CUSTOM_ID, name=name, process={"windows": [process_name], "linux": [process_name]},
                window_title="", settings_file=None, note_slots=False,
                setup_note="Bind the game's ocarina notes to the virtual Xbox pad's LB, RB, B, X and Y "
                           "in the game's or emulator's own controller settings.")


def activate(cfg):
    """Make the game chosen in cfg the active one (and point procmem at its process)."""
    global _active
    gid = cfg.get("game") or DEFAULT_ID
    if gid == CUSTOM_ID:
        _active = custom_game(cfg.get("custom_process", ""))
    else:
        _active = all_games().get(gid) or all_games().get(DEFAULT_ID) or custom_game("")
    procmem.set_target(_active.process_names())
    return _active


def active():
    return _active or activate({})


def paths(cfg, game=None):
    """Per-game remembered paths: {"ini": ..., "exe": ...}."""
    g = game or active()
    return cfg.setdefault("game_paths", {}).setdefault(g.id, {})


def migrate(cfg):
    """Older configs kept Longshot's paths at the top level; move them under game_paths."""
    gp = cfg.setdefault("game_paths", {}).setdefault(DEFAULT_ID, {})
    for old, new in (("longshot_ini", "ini"), ("longshot_exe", "exe")):
        if cfg.get(old) and not gp.get(new):
            gp[new] = cfg[old]
        cfg.pop(old, None)


def choices():
    """Known games for the picker, Longshot first."""
    return sorted(all_games().values(), key=lambda g: (g.id != DEFAULT_ID, g.name.lower()))


def detect_running():
    """Known games that are running right now."""
    return [g for g in all_games().values() if procmem.find_pid(g.process_names())]

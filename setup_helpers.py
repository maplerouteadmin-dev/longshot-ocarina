"""First-run checks: virtual-controller driver, and Longshot's note bindings."""
import ctypes
import os
import shutil
import subprocess
import time
from ctypes import wintypes

import config
from ocarina_flag import PROCESS_NAME, game_running

VIGEM_URL = "https://github.com/nefarius/ViGEmBus/releases"


def vigem_installed():
    try:
        out = subprocess.run(["sc", "query", "ViGEmBus"], capture_output=True, text=True,
                             creationflags=getattr(subprocess, "CREATE_NO_WINDOW", 0)).stdout
    except Exception:
        return False
    return "RUNNING" in out


def _running_exe_path():
    try:
        import pymem
        pm = pymem.Pymem(PROCESS_NAME)
    except Exception:
        return None
    buf = ctypes.create_unicode_buffer(1024)
    size = wintypes.DWORD(len(buf))
    if ctypes.windll.kernel32.QueryFullProcessImageNameW(pm.process_handle, 0, buf, ctypes.byref(size)):
        return buf.value
    return None


def find_ini(saved_path=""):
    """longshot_options.ini: the saved path, else next to the running game."""
    if saved_path and os.path.exists(saved_path):
        return saved_path
    exe = _running_exe_path()
    if exe:
        d = os.path.dirname(exe)
        for folder in (d, os.path.dirname(d)):
            p = os.path.join(folder, "longshot_options.ini")
            if os.path.exists(p):
                return p
    return None


def _parse(path):
    with open(path, "r", encoding="utf-8") as f:
        lines = f.read().splitlines()
    values = {}
    for line in lines:
        if "=" in line and not line.lstrip().startswith((";", "#", "[")):
            k, v = line.split("=", 1)
            values[k.strip()] = v.strip()
    return lines, values


def binding_status(path):
    """{note_slot: (current, wanted)} for each of the five ocarina notes."""
    _, values = _parse(path)
    return {d["ini_note"]: (values.get(d["ini_note"]), values.get(d["ini_src"])) for d in config.NOTE_DEFS}


def bindings_ok(path):
    return all(cur == want and want is not None for cur, want in binding_status(path).values())


def apply_bindings(path):
    """Point each pad_note_* at the same pad index as its normal button.

    Only pad_note_* is touched -- binding key_note_* (keyboard) disabled the
    real controller entirely in testing. Longshot must be closed, since it
    rewrites the file on exit. Returns the backup path."""
    if game_running():
        raise RuntimeError("Close Longshot first -- it overwrites this file when it exits.")
    lines, values = _parse(path)
    wanted = {d["ini_note"]: values.get(d["ini_src"]) for d in config.NOTE_DEFS}
    missing = [k for k, v in wanted.items() if v is None]
    if missing:
        raise RuntimeError(f"Couldn't find your normal button bindings for {missing} in {path}")
    backup = f"{path}.ocarina-backup-{time.strftime('%Y%m%d-%H%M%S')}"
    shutil.copy2(path, backup)
    done = set()
    for i, line in enumerate(lines):
        if "=" in line:
            k = line.split("=", 1)[0].strip()
            if k in wanted:
                lines[i] = f"{k}={wanted[k]}"
                done.add(k)
    lines += [f"{k}={v}" for k, v in wanted.items() if k not in done]
    with open(path, "w", encoding="utf-8", newline="") as f:
        f.write("\n".join(lines) + "\n")
    return backup

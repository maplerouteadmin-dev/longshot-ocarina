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
                             creationflags=NO_WINDOW).stdout
    except Exception:
        return False
    return "RUNNING" in out


NO_WINDOW = getattr(subprocess, "CREATE_NO_WINDOW", 0)


def launcher_path():
    p = os.path.join(os.environ.get("LOCALAPPDATA", ""), "Programs", "LongshotLauncher", "LongshotLauncher.exe")
    return p if os.path.exists(p) else None


def can_start_longshot(cfg):
    return bool(launcher_path() or (cfg.get("longshot_exe") and os.path.exists(cfg["longshot_exe"])))


def start_longshot(cfg):
    """Start the game the way the desktop shortcut does (launcher --play), or
    the game exe seen running before if the launcher isn't installed."""
    launcher = launcher_path()
    if launcher:
        subprocess.Popen([launcher, "--play"], cwd=os.path.dirname(launcher))
    elif cfg.get("longshot_exe") and os.path.exists(cfg["longshot_exe"]):
        subprocess.Popen([cfg["longshot_exe"]], cwd=os.path.dirname(cfg["longshot_exe"]))
    else:
        raise RuntimeError("Couldn't find Longshot or its launcher -- start it yourself once and the app "
                           "will remember where it is.")


def other_instances():
    """Other copies of this translator that are running -- each one holds its
    own virtual controller, which can make Longshot ignore this one's presses.
    Returns [(pid, description)]."""
    me = {os.getpid(), os.getppid()}
    ps = ("Get-CimInstance Win32_Process | Where-Object { $_.Name -in 'python.exe','pythonw.exe',"
          "'OcarinaTranslator.exe' } | ForEach-Object { \"$($_.ProcessId)|$($_.ParentProcessId)|$($_.Name)|"
          "$($_.CommandLine)\" }")
    try:
        out = subprocess.run(["powershell", "-NoProfile", "-Command", ps], capture_output=True, text=True,
                             timeout=10, creationflags=NO_WINDOW).stdout
    except Exception:
        return []
    found = []
    for line in out.splitlines():
        parts = line.split("|", 3)
        if len(parts) < 4:
            continue
        pid, ppid, name, cmd = int(parts[0]), int(parts[1]), parts[2], parts[3]
        if pid in me or ppid in me:
            continue
        low = cmd.lower()
        if name.lower() == "ocarinatranslator.exe":
            found.append((pid, "OcarinaTranslator.exe"))
        elif "translator.py" in low or "ocarinatranslator\\app.py" in low or "flag_scan" in low:
            found.append((pid, f"python {cmd.split('python.exe')[-1].strip(' \"')}"))
    return found


def close_instances(pids):
    for pid in pids:
        subprocess.run(["taskkill", "/PID", str(pid), "/F"], capture_output=True, creationflags=NO_WINDOW)


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


# ---- start with Windows, wait for Longshot -------------------------------
WAIT_FLAG = "--wait-for-longshot"
STARTUP_LNK = os.path.join(os.environ.get("APPDATA", ""), r"Microsoft\Windows\Start Menu\Programs\Startup",
                           "Ocarina Translator.lnk")


def autostart_enabled():
    return os.path.exists(STARTUP_LNK)


def set_autostart(on):
    """Add/remove a Startup-folder shortcut that runs this app in wait-for-Longshot mode."""
    import sys
    if not on:
        if os.path.exists(STARTUP_LNK):
            os.remove(STARTUP_LNK)
        return
    if getattr(sys, "frozen", False):
        target, args, workdir = sys.executable, WAIT_FLAG, os.path.dirname(sys.executable)
    else:
        here = os.path.dirname(os.path.abspath(__file__))
        pyw = os.path.join(os.path.dirname(sys.executable), "pythonw.exe")
        target, args, workdir = pyw, f'"{os.path.join(here, "app.py")}" {WAIT_FLAG}', here
    q = lambda s: s.replace("'", "''")
    ps = (f"$s=(New-Object -ComObject WScript.Shell).CreateShortcut('{q(STARTUP_LNK)}');"
          f"$s.TargetPath='{q(target)}';$s.Arguments='{q(args)}';$s.WorkingDirectory='{q(workdir)}';$s.Save()")
    subprocess.run(["powershell", "-NoProfile", "-Command", ps], check=True,
                   creationflags=getattr(subprocess, "CREATE_NO_WINDOW", 0))

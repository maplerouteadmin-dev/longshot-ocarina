"""First-run checks: virtual-controller driver, and Longshot's note bindings."""
import os
import shutil
import signal
import subprocess
import sys
import time

import config
import procmem
from ocarina_flag import game_running

IS_WINDOWS = sys.platform == "win32"
VIGEM_URL = "https://github.com/nefarius/ViGEmBus/releases"
LINUX_SETUP_URL = "https://github.com/maplerouteadmin-dev/longshot-ocarina#linux-experimental"
DRIVER_URL = VIGEM_URL if IS_WINDOWS else LINUX_SETUP_URL
DRIVER_OK_TEXT = ("Virtual controller driver (ViGEmBus) installed" if IS_WINDOWS
                  else "Allowed to create a virtual controller (/dev/uinput)")
DRIVER_MISSING_TEXT = ("ViGEmBus driver not installed -- needed to send notes to the game" if IS_WINDOWS
                       else "No permission for /dev/uinput -- needed to send notes to the game (see README)")


def vigem_installed():
    """Can we create the virtual controller? (Windows: ViGEmBus running; Linux: /dev/uinput writable.)"""
    if not IS_WINDOWS:
        return os.access("/dev/uinput", os.W_OK)
    try:
        out = subprocess.run(["sc", "query", "ViGEmBus"], capture_output=True, text=True,
                             creationflags=NO_WINDOW).stdout
    except Exception:
        return False
    return "RUNNING" in out


NO_WINDOW = getattr(subprocess, "CREATE_NO_WINDOW", 0)


def launcher_path():
    if IS_WINDOWS:
        p = os.path.join(os.environ.get("LOCALAPPDATA", ""), "Programs", "LongshotLauncher",
                         "LongshotLauncher.exe")
        return p if os.path.exists(p) else None
    import glob
    home = os.path.expanduser("~")
    for pattern in ("Applications/LongshotLauncher*.AppImage", ".local/bin/LongshotLauncher*",
                    "Downloads/LongshotLauncher*.AppImage", "LongshotLauncher*.AppImage"):
        hits = sorted(glob.glob(os.path.join(home, pattern)))
        if hits:
            return hits[-1]
    return None


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
    if not IS_WINDOWS:
        return _other_instances_linux(me)
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
        if WAIT_FLAG in low:
            continue   # autostart copy waiting for Longshot: no controller, and it stands down if we're open
        if name.lower() == "ocarinatranslator.exe":
            found.append((pid, "OcarinaTranslator.exe"))
        elif "translator.py" in low or "ocarinatranslator\\app.py" in low or "flag_scan" in low:
            found.append((pid, f"python {cmd.split('python.exe')[-1].strip(' \"')}"))
    return found


def _other_instances_linux(me):
    found = []
    for d in os.listdir("/proc"):
        if not d.isdigit() or int(d) in me:
            continue
        try:
            with open(f"/proc/{d}/cmdline", "rb") as f:
                cmd = f.read().replace(b"\x00", b" ").decode(errors="ignore")
            with open(f"/proc/{d}/stat") as f:
                ppid = int(f.read().rsplit(")", 1)[1].split()[1])
        except (OSError, ValueError, IndexError):
            continue
        low = cmd.lower()
        if ppid in me or WAIT_FLAG in low:
            continue
        if "ocarinatranslator" in low.replace(" ", "") and "app.py" not in low:
            found.append((int(d), "OcarinaTranslator"))
        elif "translator.py" in low or "ocarinatranslator/app.py" in low or "flag_scan" in low:
            found.append((int(d), cmd.strip()))
    return found


def close_instances(pids):
    for pid in pids:
        if IS_WINDOWS:
            subprocess.run(["taskkill", "/PID", str(pid), "/F"], capture_output=True, creationflags=NO_WINDOW)
        else:
            try:
                os.kill(pid, signal.SIGTERM)
            except OSError:
                pass


def _running_exe_path():
    proc = procmem.open_game()
    return proc.exe_path() if proc else None


def find_ini(saved_path=""):
    """longshot_options.ini: the saved path, else next to the running game."""
    if saved_path and os.path.exists(saved_path):
        return saved_path
    exe = _running_exe_path()
    folders = []
    if exe:
        d = os.path.dirname(exe)
        folders += [d, os.path.dirname(d)]
    if not IS_WINDOWS:   # Linux keeps per-user data here (saves, maybe the ini)
        folders.append(os.path.expanduser("~/.local/share/longshot"))
    for folder in folders:
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


def background_input_ok(path):
    """Longshot only reads the controller while focused unless controller_in_background=1;
    without it, notes are silently dropped after you click any other window."""
    return _parse(path)[1].get("controller_in_background") == "1"


def game_mic_off(path):
    """Longshot has its own microphone input; if it's on as well, the game reacts to your
    playing on its own and the notes double up / fight with the app's."""
    return _parse(path)[1].get("microphone", "0") == "0"


def turn_off_game_mic(path):
    """Set microphone=0 (Longshot must be closed). Returns the backup path."""
    return _set_ini(path, "microphone", "0")


def _set_ini(path, key, value):
    if game_running():
        raise RuntimeError("Close Longshot first -- it overwrites this file when it exits.")
    lines, _ = _parse(path)
    backup = f"{path}.ocarina-backup-{time.strftime('%Y%m%d-%H%M%S')}"
    shutil.copy2(path, backup)
    for i, line in enumerate(lines):
        if line.split("=", 1)[0].strip() == key:
            lines[i] = f"{key}={value}"
            break
    else:
        lines.append(f"{key}={value}")
    with open(path, "w", encoding="utf-8", newline="") as f:
        f.write("\n".join(lines) + "\n")
    return backup


def apply_background_input(path):
    """Set controller_in_background=1 (Longshot must be closed). Returns the backup path."""
    if game_running():
        raise RuntimeError("Close Longshot first -- it overwrites this file when it exits.")
    lines, _ = _parse(path)
    backup = f"{path}.ocarina-backup-{time.strftime('%Y%m%d-%H%M%S')}"
    shutil.copy2(path, backup)
    for i, line in enumerate(lines):
        if line.split("=", 1)[0].strip() == "controller_in_background":
            lines[i] = "controller_in_background=1"
            break
    else:
        lines.append("controller_in_background=1")
    with open(path, "w", encoding="utf-8", newline="") as f:
        f.write("\n".join(lines) + "\n")
    return backup


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
STARTUP_LNK = (os.path.join(os.environ.get("APPDATA", ""), r"Microsoft\Windows\Start Menu\Programs\Startup",
                            "Ocarina Translator.lnk") if IS_WINDOWS
               else os.path.expanduser("~/.config/autostart/ocarina-translator.desktop"))


def autostart_enabled():
    return os.path.exists(STARTUP_LNK)


def set_autostart(on):
    """Add/remove a Startup-folder shortcut that runs this app in wait-for-Longshot mode."""
    if not on:
        if os.path.exists(STARTUP_LNK):
            os.remove(STARTUP_LNK)
        return
    if not IS_WINDOWS:
        if getattr(sys, "frozen", False):
            cmd = f'"{sys.executable}" {WAIT_FLAG}'
        else:
            app_py = os.path.join(os.path.dirname(os.path.abspath(__file__)), "app.py")
            cmd = f'"{sys.executable}" "{app_py}" {WAIT_FLAG}'
        os.makedirs(os.path.dirname(STARTUP_LNK), exist_ok=True)
        lines = ["[Desktop Entry]", "Type=Application", "Name=Ocarina Translator", f"Exec={cmd}",
                 "X-GNOME-Autostart-enabled=true", "NoDisplay=true"]
        with open(STARTUP_LNK, "w") as f:
            f.write("\n".join(lines) + "\n")
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

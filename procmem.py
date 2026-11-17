"""Cross-platform access to Longshot's process: find it, read its memory, list regions.

Windows uses pymem / VirtualQueryEx (as before). Linux uses /proc/<pid>/maps and
/proc/<pid>/mem, which needs permission to inspect the game: run as the same
user and either set `kernel.yama.ptrace_scope = 0` or give the app
`cap_sys_ptrace` (see README). The API mirrors the bits of pymem the app used
(`read_bytes`, `process_id`) so callers don't care which OS they're on.
"""
import ctypes
import os
import sys
from dataclasses import dataclass

IS_WINDOWS = sys.platform == "win32"
PROCESS_NAMES = ("longshot.exe",) if IS_WINDOWS else ("longshot", "longshot.exe")


@dataclass
class Region:
    base: int
    size: int
    alloc_base: int       # Windows AllocationBase; on Linux the start of a run of adjacent anonymous maps
    committed: bool       # backed by memory (Linux: not PROT_NONE)
    private: bool         # heap-like (Windows MEM_PRIVATE; Linux anonymous mapping)
    writable: bool
    image: bool           # part of a loaded exe/dll/so


class ProcessNotFound(Exception):
    pass


# ---------------------------------------------------------------- Windows ----
if IS_WINDOWS:
    import ctypes.wintypes as wt

    import pymem

    class _MBI(ctypes.Structure):
        _fields_ = [("BaseAddress", ctypes.c_ulonglong), ("AllocationBase", ctypes.c_ulonglong),
                    ("AllocationProtect", wt.DWORD), ("PartitionId", wt.WORD),
                    ("RegionSize", ctypes.c_ulonglong), ("State", wt.DWORD),
                    ("Protect", wt.DWORD), ("Type", wt.DWORD)]

    _k32 = ctypes.WinDLL("kernel32", use_last_error=True)
    _k32.VirtualQueryEx.argtypes = [wt.HANDLE, ctypes.c_void_p, ctypes.POINTER(_MBI), ctypes.c_size_t]
    _k32.VirtualQueryEx.restype = ctypes.c_size_t
    _WRITABLE = {0x04, 0x08, 0x40, 0x80}

    class Process:
        def __init__(self, names=PROCESS_NAMES):
            last = None
            for n in names:
                try:
                    self._pm = pymem.Pymem(n)
                    break
                except Exception as e:
                    last = e
            else:
                raise ProcessNotFound(str(last))
            self.process_id = self._pm.process_id
            self.process_handle = self._pm.process_handle

        def read_bytes(self, addr, n):
            return self._pm.read_bytes(addr, n)

        def alive(self):
            code = wt.DWORD()
            ctypes.windll.kernel32.GetExitCodeProcess(self.process_handle, ctypes.byref(code))
            return code.value == 259          # STILL_ACTIVE

        def exe_path(self):
            try:
                return self._pm.process_base.filename
            except Exception:
                return None

        def regions(self):
            out, addr, m = [], 0, _MBI()
            while addr < 0x7FFFFFFFFFFF and _k32.VirtualQueryEx(self.process_handle, ctypes.c_void_p(addr),
                                                               ctypes.byref(m), ctypes.sizeof(m)):
                if m.State != 0x10000:            # not MEM_FREE
                    out.append(Region(m.BaseAddress, m.RegionSize, m.AllocationBase,
                                      committed=m.State == 0x1000, private=m.Type == 0x20000,
                                      writable=m.Protect in _WRITABLE,
                                      image=m.Type == 0x1000000))
                addr = m.BaseAddress + m.RegionSize
            return out

# ------------------------------------------------------------------ Linux ----
else:
    def _find_pid(names):
        want = {n.lower() for n in names}
        for d in os.listdir("/proc"):
            if not d.isdigit():
                continue
            try:
                with open(f"/proc/{d}/comm") as f:
                    comm = f.read().strip().lower()
                exe = os.path.basename(os.readlink(f"/proc/{d}/exe")).lower()
            except OSError:
                continue
            if comm in want or exe in want:
                return int(d)
        return None

    class Process:
        def __init__(self, names=PROCESS_NAMES):
            pid = _find_pid(names)
            if pid is None:
                raise ProcessNotFound(", ".join(names))
            self.process_id = pid
            self.process_handle = None
            try:
                self._fd = os.open(f"/proc/{pid}/mem", os.O_RDONLY)
            except PermissionError as e:
                raise PermissionError(
                    "Not allowed to read Longshot's memory. Run: sudo sysctl kernel.yama.ptrace_scope=0 "
                    "(or give this app cap_sys_ptrace) -- see the README.") from e

        def __del__(self):
            try:
                os.close(self._fd)
            except Exception:
                pass

        def read_bytes(self, addr, n):
            data = os.pread(self._fd, n, addr)
            if len(data) != n:
                raise OSError(f"short read at {addr:#x}")
            return data

        def alive(self):
            return os.path.exists(f"/proc/{self.process_id}")

        def exe_path(self):
            try:
                return os.readlink(f"/proc/{self.process_id}/exe")
            except OSError:
                return None

        def regions(self):
            out, run_start, prev_end = [], None, None
            with open(f"/proc/{self.process_id}/maps") as f:
                for line in f:
                    parts = line.split(None, 5)
                    lo, hi = (int(x, 16) for x in parts[0].split("-"))
                    perms = parts[1]
                    path = parts[5].strip() if len(parts) > 5 else ""
                    anon = path == "" or path.startswith("[heap") or path.startswith("[anon")
                    # adjacent anonymous maps (e.g. a big reservation committed piecewise) form one "allocation"
                    if anon and run_start is not None and prev_end == lo:
                        base = run_start
                    else:
                        base = run_start = lo
                    if not anon:
                        run_start = None
                    prev_end = hi
                    out.append(Region(lo, hi - lo, base, committed=perms[0] != "-" or perms[1] != "-",
                                      private=anon and perms[3] == "p", writable=perms[1] == "w",
                                      image=bool(path) and not path.startswith("[")))
            return out


def open_game():
    """Process for the running Longshot, or None."""
    try:
        return Process()
    except (ProcessNotFound, PermissionError, OSError):
        return None


def game_running():
    if IS_WINDOWS:
        return open_game() is not None
    return _find_pid(PROCESS_NAMES) is not None


def allocations(proc):
    """{alloc_base: total size} over all non-free regions."""
    sizes = {}
    for r in proc.regions():
        sizes[r.alloc_base] = sizes.get(r.alloc_base, 0) + r.size
    return sizes

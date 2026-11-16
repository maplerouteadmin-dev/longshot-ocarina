"""Reads Longshot's "ocarina is up" flag from process memory.

Longshot runs the game in an emulated console whose memory is one huge private
reservation in longshot.exe (the "arena"). Game variables sit at fixed offsets
inside it, so the flag survives restarts: we read the offsets in flag_spots.py
(found by arena_scan.py) and take the majority (1 = up, 0 = put away).

If that fails (e.g. a Longshot update moved things), the raw heap address saved
by the Game Flag scan (flag_scan.py) is used instead; that one moves on every
relaunch.

read() distinguishes "down" from "can't tell" (game not running, unreadable, or
no clear majority) so the engine can fall back to the hotkey instead of
silently never listening.
"""
import ctypes
import ctypes.wintypes as wt

import pymem

from flag_spots import OFFSETS

PROCESS_NAME = "longshot.exe"
SPOT_UP, SPOT_DOWN = 1, 0
MIN_ARENA = 0x1000000000          # the arena is a >= 64 GB reservation


class _MBI(ctypes.Structure):
    _fields_ = [("BaseAddress", ctypes.c_ulonglong), ("AllocationBase", ctypes.c_ulonglong),
                ("AllocationProtect", wt.DWORD), ("PartitionId", wt.WORD),
                ("RegionSize", ctypes.c_ulonglong), ("State", wt.DWORD),
                ("Protect", wt.DWORD), ("Type", wt.DWORD)]


_k32 = ctypes.WinDLL("kernel32", use_last_error=True)
_k32.VirtualQueryEx.argtypes = [wt.HANDLE, ctypes.c_void_p, ctypes.POINTER(_MBI), ctypes.c_size_t]
_k32.VirtualQueryEx.restype = ctypes.c_size_t


def find_arena(handle):
    """Base of the biggest private reservation (the emulated console memory), or None."""
    sizes, addr, m = {}, 0, _MBI()
    while addr < 0x7FFFFFFFFFFF and _k32.VirtualQueryEx(handle, ctypes.c_void_p(addr), ctypes.byref(m),
                                                        ctypes.sizeof(m)):
        if m.State != 0x10000 and m.Type == 0x20000:
            sizes[m.AllocationBase] = sizes.get(m.AllocationBase, 0) + m.RegionSize
        addr = m.BaseAddress + m.RegionSize
    if not sizes:
        return None
    base, size = max(sizes.items(), key=lambda kv: kv[1])
    return base if size >= MIN_ARENA else None


class GameFlag:
    def __init__(self, address, up_value=0, down_value=1, offsets=None):
        self.address = address            # raw fallback from the scan
        self.up_value = up_value
        self.down_value = down_value
        self.offsets = OFFSETS if offsets is None else offsets
        self._pm = None
        self._arena = None
        self.last_raw = None
        self.via_chains = False           # True when the last read used the arena spots ("automatic")

    def _attach(self):
        try:
            pm = pymem.Pymem(PROCESS_NAME)
        except Exception:
            self._pm = None
            return None
        self._pm = pm
        try:
            self._arena = find_arena(pm.process_handle)
        except Exception:
            self._arena = None
        return pm

    def _vote(self):
        """1/0 when a clear majority of the arena spots agree, else None."""
        up = down = 0
        for o in self.offsets:
            try:
                v = self._pm.read_bytes(self._arena + o, 1)[0]
            except Exception:
                continue
            up += v == SPOT_UP
            down += v == SPOT_DOWN
        need = len(self.offsets) * 2 // 3
        if up >= need:
            return SPOT_UP
        if down >= need:
            return SPOT_DOWN
        return None

    def current_address(self):
        return (self._arena + self.offsets[0]) if self.via_chains and self._arena else self.address

    def read(self):
        """True = ocarina up, False = put away, None = can't tell."""
        self.last_raw = None
        self.via_chains = False
        pm = self._pm or self._attach()
        if pm is None:
            return None
        if self._arena and self.offsets:
            v = self._vote()
            if v is None and not self._process_alive():
                pm = self._attach()       # Longshot restarted: find the new arena
                v = self._vote() if pm and self._arena else None
            if v is not None:
                self.via_chains = True
                self.last_raw = v
                return v == SPOT_UP
        if not self.address or self._pm is None:
            return None
        try:
            raw = self._pm.read_bytes(self.address, 1)[0]
        except Exception:
            # process restarted (new pid) or address no longer mapped
            if self._attach() is None:
                return None
            try:
                raw = self._pm.read_bytes(self.address, 1)[0]
            except Exception:
                return None
        self.last_raw = raw
        if raw == self.up_value:
            return True
        if raw == self.down_value:
            return False
        return None

    def _process_alive(self):
        try:
            code = wt.DWORD()
            ctypes.windll.kernel32.GetExitCodeProcess(self._pm.process_handle, ctypes.byref(code))
            return code.value == 259    # STILL_ACTIVE
        except Exception:
            return False


def game_running():
    try:
        pymem.Pymem(PROCESS_NAME)
        return True
    except Exception:
        return False

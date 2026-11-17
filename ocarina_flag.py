"""Reads Longshot's "ocarina is up" flag from process memory.

Longshot runs the game in an emulated console whose memory is one huge private
reservation in the game process (the "arena"). Game variables sit at fixed
offsets inside it, so the flag survives restarts: we read the offsets in
flag_spots.py (found by tools/arena_scan.py) and take the majority (1 = up,
0 = put away). The Windows and Linux builds lay memory out differently, so each
has its own offsets; Linux ones haven't been found yet (see the GitHub issue).

If that fails (e.g. a Longshot update moved things), the raw heap address saved
by the Game Flag scan (flag_scan.py) is used instead; that one moves on every
relaunch.

read() distinguishes "down" from "can't tell" (game not running, unreadable, or
no clear majority) so the engine can fall back to the hotkey instead of
silently never listening.
"""
import procmem
from flag_spots import LINUX_OFFSETS, OFFSETS

PROCESS_NAME = procmem.PROCESS_NAMES[0]
SPOT_UP, SPOT_DOWN = 1, 0
MIN_ARENA = 0x1000000000          # the arena is a >= 64 GB reservation
PLATFORM_OFFSETS = OFFSETS if procmem.IS_WINDOWS else LINUX_OFFSETS


def find_arena(proc):
    """Base of the biggest private reservation (the emulated console memory), or None."""
    sizes = {}
    for r in proc.regions():
        if r.private:
            sizes[r.alloc_base] = sizes.get(r.alloc_base, 0) + r.size
    if not sizes:
        return None
    base, size = max(sizes.items(), key=lambda kv: kv[1])
    return base if size >= MIN_ARENA else None


class GameFlag:
    def __init__(self, address, up_value=0, down_value=1, offsets=None):
        self.address = address            # raw fallback from the scan
        self.up_value = up_value
        self.down_value = down_value
        self.offsets = PLATFORM_OFFSETS if offsets is None else offsets
        self._pm = None
        self._arena = None
        self.last_raw = None
        self.via_chains = False           # True when the last read used the arena spots ("automatic")

    def _attach(self):
        self._pm = procmem.open_game()
        self._arena = None
        if self._pm is not None and self.offsets:
            try:
                self._arena = find_arena(self._pm)
            except Exception:
                self._arena = None
        return self._pm

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
            if v is None and not self._pm.alive():
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


def game_running():
    return procmem.game_running()

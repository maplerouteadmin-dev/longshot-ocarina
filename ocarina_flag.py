"""Reads Longshot's "ocarina is up" flag from process memory.

Longshot runs the game in an emulated console whose memory is one huge private
reservation in the game process (the "arena"). Game variables sit at fixed
offsets inside it, so the flag survives restarts: we read the offsets in
the active game profile (games/<game>.json, found by tools/arena_scan.py) and take the majority (1 = up,
0 = put away). The Windows and Linux builds lay memory out differently, so each
has its own offsets; Linux ones haven't been found yet (see the GitHub issue).

If that fails (e.g. a Longshot update moved things), the raw heap address saved
by the Game Flag scan (flag_scan.py) is used instead; that one moves on every
relaunch.

read() distinguishes "down" from "can't tell" (game not running, unreadable, or
no clear majority) so the engine can fall back to the hotkey instead of
silently never listening.
"""
import time

import procmem
PROCESS_NAME = procmem.PROCESS_NAMES[0]   # default only; the active game sets procmem's target
SPOT_UP, SPOT_DOWN = 1, 0
MIN_ARENA = 0x1000000000          # the arena is a >= 64 GB reservation


def find_arena_bounds(proc):
    """(start, end) of the biggest private reservation (the emulated console memory), or None."""
    sizes = {}
    for r in proc.regions():
        if r.private:
            sizes[r.alloc_base] = sizes.get(r.alloc_base, 0) + r.size
    if not sizes:
        return None
    base, size = max(sizes.items(), key=lambda kv: kv[1])
    return (base, base + size) if size >= MIN_ARENA else None


def find_arena(proc):
    """Start of the arena, or None."""
    b = find_arena_bounds(proc)
    return b[0] if b else None


class GameFlag:
    def __init__(self, address, up_value=0, down_value=1, offsets=None):
        self.address = address            # raw fallback from the scan
        self.up_value = up_value
        self.down_value = down_value
        if offsets is None:   # the active game's known flag spots (empty -> raw address only)
            import games
            offsets = games.active().flag_offsets()
        self.offsets = offsets
        self._pm = None
        self._arena = None
        self._arena_end = None
        self.last_raw = None
        self.via_chains = False           # True when the last read used the arena spots ("automatic")
        self._next_attach = 0.0           # throttle: looking for the game scans every process

    def _attach(self):
        now = time.monotonic()
        if now < self._next_attach:
            self._pm = None
            return None
        self._next_attach = now + 1.0
        self._pm = procmem.open_game()
        self._arena = self._arena_end = None
        if self._pm is not None and self.offsets:
            try:
                self._arena, self._arena_end = find_arena_bounds(self._pm) or (None, None)
            except Exception:
                self._arena = self._arena_end = None
        return self._pm

    def _addr(self, o):
        """Offsets >= 0 count from the arena's start; negative ones from its end (steadier on Linux,
        where the kernel can merge a neighbouring map onto the start)."""
        return self._arena + o if o >= 0 else self._arena_end + o

    def _vote(self):
        """1/0 when a clear majority of the arena spots agree, else None."""
        up = down = 0
        for o in self.offsets:
            try:
                v = self._pm.read_bytes(self._addr(o), 1)[0]
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
        return self._addr(self.offsets[0]) if self.via_chains and self._arena else self.address

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

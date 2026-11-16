"""Reads Longshot's "ocarina is up" byte from process memory.

The flag lives on the heap, so its address moves every time Longshot is
relaunched. It is found automatically by following the pointer chains in
flag_chains.py from a fixed spot in longshot_vk.dll (re-resolved about once a
second, so scene reloads are handled too). If no chain resolves, the raw
address saved by the Game Flag scan (flag_scan.py) is used instead.

read() distinguishes "down" from "can't tell" (game not running, address
unreadable, or a value that isn't one of the two states) so the engine can
fall back to the hotkey instead of silently never listening.
"""
import struct
import time
from collections import Counter

import pymem
import pymem.process

from flag_chains import CHAINS

PROCESS_NAME = "longshot.exe"
CHAIN_UP, CHAIN_DOWN = 1, 0      # polarity of the byte the chains point at
RESOLVE_EVERY = 1.0              # seconds


class GameFlag:
    def __init__(self, address, up_value=0, down_value=1, chains=None):
        self.address = address            # raw fallback from the scan
        self.up_value = up_value
        self.down_value = down_value
        self.chains = CHAINS if chains is None else chains
        self._pm = None
        self._bases = {}
        self._auto = None                 # address found via chains
        self._next_resolve = 0.0
        self.last_raw = None
        self.via_chains = False           # True when the last read used a chain

    def _attach(self):
        try:
            pm = pymem.Pymem(PROCESS_NAME)
        except Exception:
            self._pm = None
            return None
        self._pm, self._bases, self._auto, self._next_resolve = pm, {}, None, 0.0
        return pm

    def _base(self, name):
        if name not in self._bases:
            mod = pymem.process.module_from_name(self._pm.process_handle, name)
            self._bases[name] = mod.lpBaseOfDll if mod else None
        return self._bases[name]

    def _resolve(self):
        """Follow every chain; return the address most chains agree on (with a 0/1 value)."""
        votes = Counter()
        for name, modoff, offsets in self.chains:
            try:
                base = self._base(name)
                if base is None:
                    continue
                addr = base + modoff
                for o in offsets:
                    addr = struct.unpack("<Q", self._pm.read_bytes(addr, 8))[0] + o
                if self._pm.read_bytes(addr, 1)[0] in (CHAIN_UP, CHAIN_DOWN):
                    votes[addr] += 1
            except Exception:
                continue
        return votes.most_common(1)[0][0] if votes else None

    def current_address(self):
        return self._auto if self.via_chains else self.address

    def read(self):
        """True = ocarina up, False = put away, None = can't tell."""
        self.last_raw = None
        pm = self._pm or self._attach()
        if pm is None:
            self.via_chains = False
            return None
        if self.chains and time.monotonic() >= self._next_resolve:
            self._next_resolve = time.monotonic() + RESOLVE_EVERY
            self._auto = self._resolve()
        if self._auto is not None:
            try:
                raw = pm.read_bytes(self._auto, 1)[0]
                self.via_chains = True
                self.last_raw = raw
                return {CHAIN_UP: True, CHAIN_DOWN: False}.get(raw)
            except Exception:
                self._auto = None
        self.via_chains = False
        if not self.address:
            return None
        try:
            raw = pm.read_bytes(self.address, 1)[0]
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
    try:
        pymem.Pymem(PROCESS_NAME)
        return True
    except Exception:
        return False

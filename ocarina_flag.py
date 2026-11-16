"""Reads Longshot's "ocarina is up" byte from process memory.

The address is a heap address, so it moves every time Longshot is relaunched;
flag_scan.py finds it again. read() distinguishes "down" from "can't tell"
(game not running, address unreadable, or a value that isn't one of the two
calibrated states -- i.e. the address went stale after a relaunch) so the
engine can fall back to the hotkey instead of silently never listening.
"""
import pymem

PROCESS_NAME = "longshot.exe"


class GameFlag:
    def __init__(self, address, up_value=0, down_value=1):
        self.address = address
        self.up_value = up_value
        self.down_value = down_value
        self._pm = None
        self._pid = None
        self.last_raw = None

    def _attach(self):
        try:
            pm = pymem.Pymem(PROCESS_NAME)
        except Exception:
            self._pm = None
            return None
        self._pm, self._pid = pm, pm.process_id
        return pm

    def read(self):
        """True = ocarina up, False = put away, None = can't tell."""
        self.last_raw = None
        if not self.address:
            return None
        pm = self._pm or self._attach()
        if pm is None:
            return None
        try:
            raw = pm.read_bytes(self.address, 1)[0]
        except Exception:
            # process restarted (new pid) or address no longer mapped
            self._pm = None
            pm = self._attach()
            if pm is None:
                return None
            try:
                raw = pm.read_bytes(self.address, 1)[0]
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

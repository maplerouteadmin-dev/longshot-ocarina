"""
Reads Longshot's "ocarina is up" state directly from process memory, found
via scan-and-diff (see memscan.py / scan_session.py): address 0x1F812A0F784
reads 1 when the ocarina is put away, 0 when it's held up. Verified live
across 10+ open/close cycles before trusting it.

NOTE: this is a dynamically-allocated heap address found in THIS specific
run of the game. If Longshot is restarted, ASLR/heap layout may put this
value at a different address -- if detection stops working after a
relaunch, re-run scan_session.py to find the new address and update ADDR
below.
"""
import pymem

ADDR = 0x1F812A0F784

_pm = None


def _get_pm():
    global _pm
    if _pm is None:
        _pm = pymem.Pymem("longshot.exe")
    return _pm


def is_up() -> bool:
    try:
        val = _get_pm().read_bytes(ADDR, 1)[0]
        return val == 0
    except Exception:
        # process not running, address invalid after a relaunch, etc. --
        # fail safe to "not up" so we never inject input blindly.
        return False

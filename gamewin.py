"""Longshot's window: find it, and bring it to the front.

Focusing the game when a note is played means that if you'd clicked into
another window, your real controller is ready to go again straight away.
"""
import ctypes
import ctypes.wintypes as wt
import time

from ocarina_flag import PROCESS_NAME

_u32 = ctypes.windll.user32
_k32 = ctypes.windll.kernel32
_last_focus = 0.0


def _game_pid():
    try:
        import pymem
        return pymem.Pymem(PROCESS_NAME).process_id
    except Exception:
        return None


def game_window(pid=None):
    """(hwnd, (left, top, right, bottom)) of Longshot's biggest visible window, or (None, None)."""
    pid = pid or _game_pid()
    if not pid:
        return None, None
    best = []

    @ctypes.WINFUNCTYPE(wt.BOOL, wt.HWND, wt.LPARAM)
    def cb(hwnd, _):
        p = wt.DWORD()
        _u32.GetWindowThreadProcessId(hwnd, ctypes.byref(p))
        if p.value == pid and _u32.IsWindowVisible(hwnd):
            r = wt.RECT()
            _u32.GetWindowRect(hwnd, ctypes.byref(r))
            area = (r.right - r.left) * (r.bottom - r.top)
            if area > 0:
                best.append((area, hwnd, (r.left, r.top, r.right, r.bottom)))
        return True

    _u32.EnumWindows(cb, 0)
    if not best:
        return None, None
    _, hwnd, rect = max(best)
    return hwnd, rect


def focus_game(min_interval=0.5):
    """Bring Longshot to the front if it isn't already (throttled)."""
    global _last_focus
    now = time.monotonic()
    if now - _last_focus < min_interval:
        return
    _last_focus = now
    hwnd, _ = game_window()
    if not hwnd or _u32.GetForegroundWindow() == hwnd:
        return
    if _u32.IsIconic(hwnd):
        _u32.ShowWindow(hwnd, 9)   # SW_RESTORE
    # Windows only lets the foreground app hand over focus; briefly attach to
    # its input queue so the switch is allowed.
    fg = _u32.GetForegroundWindow()
    fg_thread = _u32.GetWindowThreadProcessId(fg, None)
    me = _k32.GetCurrentThreadId()
    attached = bool(fg_thread) and fg_thread != me and _u32.AttachThreadInput(me, fg_thread, True)
    try:
        _u32.BringWindowToTop(hwnd)
        _u32.SetForegroundWindow(hwnd)
    finally:
        if attached:
            _u32.AttachThreadInput(me, fg_thread, False)

"""Windows virtual-key send/release helpers via SendInput, plus GetAsyncKeyState polling."""
import ctypes
from ctypes import wintypes

user32 = ctypes.WinDLL("user32", use_last_error=True)

INPUT_KEYBOARD = 1
INPUT_MOUSE = 0
KEYEVENTF_KEYUP = 0x0002
MOUSEEVENTF_LEFTDOWN = 0x0002
MOUSEEVENTF_LEFTUP = 0x0004
MOUSEEVENTF_RIGHTDOWN = 0x0008
MOUSEEVENTF_RIGHTUP = 0x0010
MOUSEEVENTF_MIDDLEDOWN = 0x0020
MOUSEEVENTF_MIDDLEUP = 0x0040

VK_SCROLL = 0x91

# Longshot's options.ini encodes EVERY binding (keyboard or mouse) in the same
# numeric field. Codes 1/2/4 are the Windows virtual-key codes for the left,
# right and middle mouse buttons (VK_LBUTTON/VK_RBUTTON/VK_MBUTTON) -- not
# keyboard keys -- and must be injected as real mouse clicks, since the game
# reads mouse buttons through a different path than keyboard VK state.
# Everything else is a normal keyboard VK code (confirmed: key_move_up=87 ->
# 'W' = 0x57, key_a=69 -> 'E', key_x=32 -> Space, key_l=81 -> 'Q', key_r=82
# -> 'R').
MOUSE_CODES = {1: "left", 2: "right", 4: "middle"}

VK_F13 = 0x7C
VK_F14 = 0x7D
VK_F15 = 0x7E
VK_F16 = 0x7F
VK_F17 = 0x80

# Matches longshot_options.ini's key_note_l/r/a/y/x bindings (set to F13-F17,
# keys nothing else on a real keyboard uses, so pressing them live can only
# ever come from this app). NOTE: binding these disables controller-based
# note input entirely -- that's expected, not a bug, since this app is what
# drives notes now. If the user rebinds key_note_* in longshot_options.ini,
# update this to match.
NOTE_KEYS = {
    "L": VK_F13,
    "R": VK_F14,
    "A": VK_F15,
    "Y": VK_F16,
    "X": VK_F17,
}


ULONG_PTR = ctypes.c_size_t  # matches Windows' ULONG_PTR on both 32- and 64-bit


class KEYBDINPUT(ctypes.Structure):
    _fields_ = [
        ("wVk", wintypes.WORD),
        ("wScan", wintypes.WORD),
        ("dwFlags", wintypes.DWORD),
        ("time", wintypes.DWORD),
        ("dwExtraInfo", ULONG_PTR),
    ]


class MOUSEINPUT(ctypes.Structure):
    _fields_ = [
        ("dx", wintypes.LONG),
        ("dy", wintypes.LONG),
        ("mouseData", wintypes.DWORD),
        ("dwFlags", wintypes.DWORD),
        ("time", wintypes.DWORD),
        ("dwExtraInfo", ULONG_PTR),
    ]


class HARDWAREINPUT(ctypes.Structure):
    _fields_ = [
        ("uMsg", wintypes.DWORD),
        ("wParamL", wintypes.WORD),
        ("wParamH", wintypes.WORD),
    ]


class _INPUTUNION(ctypes.Union):
    # Must include all three (even unused ones) so this union is sized/aligned
    # exactly like the real Windows INPUT struct -- SendInput validates cbSize
    # against that real size, and a too-small custom struct fails silently.
    _fields_ = [("ki", KEYBDINPUT), ("mi", MOUSEINPUT), ("hi", HARDWAREINPUT)]


class INPUT(ctypes.Structure):
    _anonymous_ = ("u",)
    _fields_ = [("type", wintypes.DWORD), ("u", _INPUTUNION)]


user32.SendInput.argtypes = (wintypes.UINT, ctypes.POINTER(INPUT), ctypes.c_int)
user32.SendInput.restype = wintypes.UINT


def _send_struct(inp: "INPUT"):
    sent = user32.SendInput(1, ctypes.byref(inp), ctypes.sizeof(INPUT))
    if sent != 1:
        raise ctypes.WinError(ctypes.get_last_error())


def _send_key(vk: int, key_up: bool):
    flags = KEYEVENTF_KEYUP if key_up else 0
    inp = INPUT(type=INPUT_KEYBOARD, ki=KEYBDINPUT(wVk=vk, wScan=0, dwFlags=flags, time=0, dwExtraInfo=0))
    _send_struct(inp)


def _send_mouse(button: str, button_up: bool):
    flags = {
        "left": MOUSEEVENTF_LEFTUP if button_up else MOUSEEVENTF_LEFTDOWN,
        "right": MOUSEEVENTF_RIGHTUP if button_up else MOUSEEVENTF_RIGHTDOWN,
        "middle": MOUSEEVENTF_MIDDLEUP if button_up else MOUSEEVENTF_MIDDLEDOWN,
    }[button]
    inp = INPUT(type=INPUT_MOUSE, mi=MOUSEINPUT(dx=0, dy=0, mouseData=0, dwFlags=flags, time=0, dwExtraInfo=0))
    _send_struct(inp)


def key_down(code: int):
    if code in MOUSE_CODES:
        _send_mouse(MOUSE_CODES[code], button_up=False)
    else:
        _send_key(code, key_up=False)


def key_up(code: int):
    if code in MOUSE_CODES:
        _send_mouse(MOUSE_CODES[code], button_up=True)
    else:
        _send_key(code, key_up=True)


def is_pressed(vk: int) -> bool:
    return bool(user32.GetAsyncKeyState(vk) & 0x8000)


def is_toggled(vk: int) -> bool:
    """For lock keys (Scroll Lock, Caps Lock, Num Lock): current on/off state,
    read via the low-order bit, which reliably reflects the lock state even
    when GetAsyncKeyState misses the brief keydown pulse."""
    return bool(user32.GetKeyState(vk) & 0x0001)

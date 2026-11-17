"""Linux virtual controller: an Xbox 360-style pad created through uinput (python-evdev).

Needs write access to /dev/uinput. Most distros need a one-time udev rule, e.g.
  echo 'KERNEL=="uinput", MODE="0660", GROUP="input", OPTIONS+="static_node=uinput"' |
      sudo tee /etc/udev/rules.d/60-ocarina-uinput.rules
  sudo usermod -aG input $USER     # then log out and back in
It reports itself as a Microsoft X-Box 360 pad so SDL (and so Longshot) maps it
like the Windows virtual pad: the same button names mean the same thing here.
"""
from evdev import AbsInfo, UInput, ecodes as e

_BTN = {
    "A": e.BTN_A, "B": e.BTN_B, "X": e.BTN_X, "Y": e.BTN_Y,
    "LB": e.BTN_TL, "RB": e.BTN_TR, "Start": e.BTN_START, "Back": e.BTN_SELECT, "Guide": e.BTN_MODE,
    "Left stick click": e.BTN_THUMBL, "Right stick click": e.BTN_THUMBR,
}
_DPAD = {"D-pad up": (e.ABS_HAT0Y, -1), "D-pad down": (e.ABS_HAT0Y, 1),
         "D-pad left": (e.ABS_HAT0X, -1), "D-pad right": (e.ABS_HAT0X, 1)}

BUTTONS = {**{k: k for k in _BTN}, **{k: k for k in _DPAD}}
TRIGGERS = ["LT", "RT"]
STICKS = ["Left stick", "Right stick"]
ALL_INPUTS = list(BUTTONS) + TRIGGERS + STICKS
# ocarina-note slots (same names as on Windows; see gamepad_win.py for the A/B, X/Y story)
SLOT_BUTTONS = {"LB": "LB", "RB": "RB", "B": "B", "X": "X", "Y": "Y", "DLEFT": "D-pad left"}

_STICK = AbsInfo(value=0, min=-32768, max=32767, fuzz=16, flat=128, resolution=0)
_TRIG = AbsInfo(value=0, min=0, max=255, fuzz=0, flat=0, resolution=0)
_HAT = AbsInfo(value=0, min=-1, max=1, fuzz=0, flat=0, resolution=0)
_CAPS = {
    e.EV_KEY: list(_BTN.values()),
    e.EV_ABS: [(e.ABS_X, _STICK), (e.ABS_Y, _STICK), (e.ABS_RX, _STICK), (e.ABS_RY, _STICK),
               (e.ABS_Z, _TRIG), (e.ABS_RZ, _TRIG), (e.ABS_HAT0X, _HAT), (e.ABS_HAT0Y, _HAT)],
}

_pad = None


def connect():
    global _pad
    if _pad is None:
        try:
            _pad = UInput(_CAPS, name="Microsoft X-Box 360 pad", vendor=0x045E, product=0x028E, version=0x110)
        except PermissionError as ex:
            raise PermissionError("No permission to create a virtual controller (/dev/uinput). "
                                  "See the README's Linux section for the one-time udev rule.") from ex
    return _pad


def disconnect():
    global _pad
    if _pad is not None:
        _pad.close()
        _pad = None


def _set(name, on, x=0.0, y=0.0, amount=1.0):
    pad = connect()
    if name in _BTN:
        pad.write(e.EV_KEY, _BTN[name], 1 if on else 0)
    elif name in _DPAD:
        axis, val = _DPAD[name]
        pad.write(e.EV_ABS, axis, val if on else 0)
    elif name in ("LT", "RT"):
        pad.write(e.EV_ABS, e.ABS_Z if name == "LT" else e.ABS_RZ, int(255 * amount) if on else 0)
    elif name in STICKS:
        ax, ay = (e.ABS_X, e.ABS_Y) if name == "Left stick" else (e.ABS_RX, e.ABS_RY)
        # our y is "up = +1"; evdev's Y axis grows downwards
        pad.write(e.EV_ABS, ax, int(32767 * x) if on else 0)
        pad.write(e.EV_ABS, ay, int(-32767 * y) if on else 0)
    else:
        return
    pad.syn()


def press(slot):
    _set(SLOT_BUTTONS[slot], True)


def release(slot):
    _set(SLOT_BUTTONS[slot], False)


def set_input(name, on, x=0.0, y=0.0, amount=1.0):
    _set(name, on, x, y, amount)

"""Scroll Lock state for the hotkey gate (the fallback when the game flag can't be read)."""
import glob
import sys

VK_SCROLL = 0x91


def is_toggled(vk: int) -> bool:
    """On/off state of a lock key. Reads the toggle bit rather than catching the
    keypress itself, which was too brief to poll reliably."""
    if sys.platform == "win32":
        import ctypes
        return bool(ctypes.windll.user32.GetKeyState(vk) & 0x0001)
    # Linux: the keyboard's Scroll Lock LED, exposed by the kernel under /sys/class/leds
    for path in glob.glob("/sys/class/leds/*::scrolllock/brightness"):
        try:
            with open(path) as f:
                if f.read().strip() not in ("", "0"):
                    return True
        except OSError:
            continue
    return False

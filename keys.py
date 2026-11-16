"""Scroll Lock state for the hotkey gate (the fallback when the game flag can't be read)."""
import ctypes

VK_SCROLL = 0x91


def is_toggled(vk: int) -> bool:
    """On/off state of a lock key. Reads the toggle bit rather than catching the
    keypress itself, which was too brief to poll reliably."""
    return bool(ctypes.windll.user32.GetKeyState(vk) & 0x0001)

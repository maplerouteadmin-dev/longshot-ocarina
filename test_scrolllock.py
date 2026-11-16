import ctypes
import time

user32 = ctypes.windll.user32
VK_SCROLL = 0x91

print("Press Scroll Lock any time in the next 10 seconds...")
t0 = time.time()
seen = False
while time.time() - t0 < 10:
    state = user32.GetAsyncKeyState(VK_SCROLL)
    if state & 0x8000:
        print("DETECTED key-down, raw state =", state)
        seen = True
    time.sleep(0.02)

print("Done. Saw any press:", seen)

toggle_state = user32.GetKeyState(VK_SCROLL)
print("Current Scroll Lock LOCK state (toggled on/off):", bool(toggle_state & 0x0001))

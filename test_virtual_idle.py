"""Creates a virtual Xbox controller and keeps it connected (idle, no presses)
so we can test whether its mere presence disrupts the real controller."""
import time
import vgamepad as vg

gp = vg.VX360Gamepad()
print("Virtual controller created and connected. Idle -- not pressing anything.")
print("Go test your real controller in Longshot now. Ctrl+C here when done.")

try:
    while True:
        time.sleep(1)
except KeyboardInterrupt:
    print("\nDisconnecting virtual controller.")

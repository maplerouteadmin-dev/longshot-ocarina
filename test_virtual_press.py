import sys
import time
import vgamepad as vg

button_name = sys.argv[1] if len(sys.argv) > 1 else "A"
button = getattr(vg.XUSB_BUTTON, f"XUSB_GAMEPAD_{button_name.upper()}")

gp = vg.VX360Gamepad()
print(f"Virtual controller connected. Pressing {button_name} in 2 seconds...")
time.sleep(2)
gp.press_button(button=button)
gp.update()
print(f"{button_name} pressed, holding for 1 second...")
time.sleep(1)
gp.release_button(button=button)
gp.update()
print("Released.")

import time
import vgamepad as vg

gp = vg.VX360Gamepad()
print("Virtual controller connected. Pressing A in 2 seconds...")
time.sleep(2)
gp.press_button(button=vg.XUSB_BUTTON.XUSB_GAMEPAD_A)
gp.update()
print("A pressed, holding for 1 second...")
time.sleep(1)
gp.release_button(button=vg.XUSB_BUTTON.XUSB_GAMEPAD_A)
gp.update()
print("Released.")

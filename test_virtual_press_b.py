import time
import vgamepad as vg

gp = vg.VX360Gamepad()
print("Virtual controller connected. Pressing B in 2 seconds...")
time.sleep(2)
gp.press_button(button=vg.XUSB_BUTTON.XUSB_GAMEPAD_B)
gp.update()
print("B pressed, holding for 1 second...")
time.sleep(1)
gp.release_button(button=vg.XUSB_BUTTON.XUSB_GAMEPAD_B)
gp.update()
print("Released.")

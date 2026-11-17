"""Virtual controller: picks the Windows (ViGEmBus) or Linux (uinput) backend.

Both expose the same API: connect(), disconnect(), press(slot), release(slot),
set_input(name, on, x, y, amount), SLOT_BUTTONS, BUTTONS, TRIGGERS, STICKS,
ALL_INPUTS.
"""
import sys

if sys.platform == "win32":
    from gamepad_win import *          # noqa: F401,F403
    from gamepad_win import ALL_INPUTS, BUTTONS, SLOT_BUTTONS, STICKS, TRIGGERS  # noqa: F401
else:
    from gamepad_linux import *        # noqa: F401,F403
    from gamepad_linux import ALL_INPUTS, BUTTONS, SLOT_BUTTONS, STICKS, TRIGGERS  # noqa: F401

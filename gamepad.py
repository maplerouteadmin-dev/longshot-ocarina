"""
Virtual-controller note injection via ViGEmBus/vgamepad, replacing the
keyboard-based keys.py approach (which turned out to disable real-controller
input entirely when key_note_* was bound to anything).

Longshot's pad_note_* fields take the same simple button-index scheme as its
normal pad_a/pad_b/pad_x/pad_y/pad_l/pad_r fields (confirmed from
longshot_options.ini: pad_b=0, pad_a=1, pad_y=2, pad_x=3, pad_l=9, pad_r=10
-- a sequential index, not an XInput bitmask).

IMPORTANT, confirmed empirically in-game: the virtual controller's raw XInput
face buttons map to the OPPOSITE engine index from what their Xbox label
would suggest -- pressing virtual A triggered the engine's "B" action
(closed the ocarina), and pressing virtual B correctly triggered the A-note.
This matches the user's real controller also being Switch-layout (A/B and
X/Y swapped from Xbox convention), so we swap A<->B and X<->Y here too.
Shoulder buttons (L/R) are assumed NOT swapped -- not yet empirically
verified, flag if L/R notes come out wrong.
"""
import vgamepad as vg

XUSB = vg.XUSB_BUTTON

# Keys here are named after the Xbox button ACTUALLY pressed -- "B" presses
# virtual B, "X" presses virtual X, etc. This already bakes in the A/B and
# X/Y swap: pressing virtual B is what triggers the engine's pad_a (index 1,
# the A-button note), pressing virtual X triggers pad_y (index 2, C-Left),
# pressing virtual Y triggers pad_x (index 3, C-Up). So the slot name IS the
# literal button pressed; no further mental translation needed anywhere else
# in the codebase.
SLOT_BUTTONS = {
    "LB": XUSB.XUSB_GAMEPAD_LEFT_SHOULDER,
    "RB": XUSB.XUSB_GAMEPAD_RIGHT_SHOULDER,
    "B": XUSB.XUSB_GAMEPAD_B,
    "X": XUSB.XUSB_GAMEPAD_X,
    "Y": XUSB.XUSB_GAMEPAD_Y,
}

_gamepad = None


def connect():
    global _gamepad
    if _gamepad is None:
        _gamepad = vg.VX360Gamepad()
    return _gamepad


def disconnect():
    global _gamepad
    _gamepad = None  # vgamepad disconnects the virtual device on GC/drop


def press(slot: str):
    gp = connect()
    gp.press_button(button=SLOT_BUTTONS[slot])
    gp.update()


def release(slot: str):
    gp = connect()
    gp.release_button(button=SLOT_BUTTONS[slot])
    gp.update()

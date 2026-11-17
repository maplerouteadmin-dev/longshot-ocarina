"""Offsets of the ocarina flag inside Longshot's guest-memory arena.

The arena is the emulated console's memory: Longshot's biggest private
reservation (64 GB+). Found by arena_scan.py. Every offset stayed at the same
position across a real Longshot restart, read 1 while the ocarina was up (also
while playing notes) and 0 when it was put away. The flag is the majority vote.
"""
OFFSETS = [
    0x10073F78EC,
    0x1034D0334D,
    0x1050880024,
    0x1066E1B964,
    0x106849BACF,
    0x106EBA0188,
    0x107DB3F3F0,
    0x107DD3E4F0,
    0x107E3EC920,
    0x107EDCFB10,
    0x107EDE1370,
    0x107EDFBD50,
    0x107EE068E8,
    0x113B561F81,
    0x113B7BD000,
    0x113B7C7000,
    0x113B7D1000,
    0x113B7DB000,
    0x113B7E5000,
    0x113B7EF000,
    0x113B7F9000,
    0x113B803020,
    0x113B80D0C0,
    0x113B84F008,
    0x113B859058,
    0x113B863008,
    0x113B86D008,
    0x113B87A8BE,
    0x113B88720E,
    0x113B8920FE,
    0x115BC401E7,
]

# The Linux build of Longshot lays memory out differently. These need finding
# with tools/arena_scan.py on Linux (see GitHub issue #1); until then Linux
# users use the manual scan on the Game Flag tab.
LINUX_OFFSETS = []

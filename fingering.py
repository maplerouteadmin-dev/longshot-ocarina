"""Fingering charts per ocarina type, keyed by the pitch name each note plays.

12-hole Alto C: A5/B5/D6 confirmed for the user's printables.com #474058 model
(both thumbs down, left hand only). D5/F5 come from general 12-hole charts and
are NOT yet confirmed for that model -- the calibrate screen flags them.
Holes: TL/TR thumbs on the back; L1-L4 / R1-R4 front, index (nearest the
mouthpiece) to pinky.
"""

PROFILES = {
    "12-hole Alto C": {
        "D5": {"holes": {"TL", "TR", "L1", "L2", "L3", "L4", "R1", "R2", "R3"}, "confirmed": False},
        "F5": {"holes": {"TL", "TR", "L1", "L2", "L3", "L4", "R1"}, "confirmed": False},
        "A5": {"holes": {"TL", "TR", "L1", "L2", "L3"}, "confirmed": True},
        "B5": {"holes": {"TL", "TR", "L1", "L2"}, "confirmed": True},
        "D6": {"holes": {"TL", "TR"}, "confirmed": True},
    },
}


def holes(profile, pitch_name):
    entry = PROFILES.get(profile, {}).get(pitch_name)
    return entry["holes"] if entry else None


def confirmed(profile, pitch_name):
    entry = PROFILES.get(profile, {}).get(pitch_name)
    return bool(entry and entry["confirmed"])

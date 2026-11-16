"""
Calibration step: play each of your ocarina's 5 notes when prompted so the
translator learns YOUR instrument's actual pitches, instead of assuming a
generic frequency range.

Run this once (and again any time you switch physical ocarinas).
"""
import json
import os
import time

import numpy as np
import sounddevice as sd

from pitch import detect_pitch, SAMPLE_RATE

OUT_FILE = "notes.json"

# Mapping from the REAL VIRTUAL XBOX BUTTON this app presses (gamepad.py's
# SLOT_BUTTONS, already includes the A/B and X/Y swap we found empirically)
# to the real OoT ocarina buttons and their fixed pitches (confirmed via
# community ocarina-tab references): A-button=D5 (lowest), C-Down=F5,
# C-Right=A5, C-Left=B5, C-Up=D6 (highest). Keys here are literally the
# Xbox button pressed -- "B" means this app presses virtual B for that note.
NOTE_SLOTS = [
    ("LB", "A-button note", "D5"),
    ("RB", "C-Down note", "F5"),
    ("B", "C-Right note", "A5"),
    ("X", "C-Left note", "B5"),
    ("Y", "C-Up note (highest)", "D6"),
]

# Fingering chart for a standard 12-hole Alto C ocarina (the common
# "Ocarina of Time replica" style, e.g. Songbird Ocarina / Ocarina Windworks
# / the printables.com Alto C model). TL/TR = thumb holes on the back.
# L1-L4 / R1-R4 = front finger holes, numbered innermost (nearest the
# mouthpiece, played by index fingers) to outermost (nearest the bell,
# played by pinkies). The two tiny sub-holes used only for the very lowest
# notes (below this instrument's range here) aren't needed for D5-D6.
FINGERING_12_HOLE_ALTO_C = {
    # A5/B5/D6 confirmed directly from this exact model's designer
    # (E.C.3D, printables.com/model/474058) -- both thumbs stay covered
    # throughout, right hand is never used for these three notes.
    # D5/F5 are NOT yet confirmed against this specific model; still
    # pending -- see the A-button/C-Down TODO.
    "D5": {"TL", "TR", "L1", "L2", "L3", "L4", "R1", "R2", "R3"},  # UNVERIFIED for this model
    "F5": {"TL", "TR", "L1", "L2", "L3", "L4", "R1"},  # UNVERIFIED for this model
    "A5": {"TL", "TR", "L1", "L2", "L3"},   # C-Right -- confirmed
    "B5": {"TL", "TR", "L1", "L2"},         # C-Left -- confirmed
    "D6": {"TL", "TR"},                      # C-Up (highest) -- confirmed
}

ALL_HOLES = ["TL", "TR", "L1", "L2", "L3", "L4", "R1", "R2", "R3", "R4"]


def render_fingering(note: str):
    covered = FINGERING_12_HOLE_ALTO_C.get(note)
    if not covered:
        return None

    def mark(h):
        return "X" if h in covered else "."  # X = covered, . = open

    lines = [
        f"      Thumb(back):  TL[{mark('TL')}]   TR[{mark('TR')}]",
        "      Front:",
        f"        Left hand :  L1[{mark('L1')}] L2[{mark('L2')}] L3[{mark('L3')}] L4[{mark('L4')}]",
        f"        Right hand:  R1[{mark('R1')}] R2[{mark('R2')}] R3[{mark('R3')}] R4[{mark('R4')}]",
        "      (X = cover this hole, . = leave open; L1/R1 = nearest mouthpiece)",
    ]
    return "\n".join(lines)

RECORD_SECONDS = 5.0
SAMPLES_PER_NOTE = 6  # how many pitch readings to collect and average


def record_note(label: str, note_name: str = None) -> float:
    print(f"\n>>> Next note: {label}")
    if note_name:
        import diagram  # lazy import: diagram.py imports FINGERING_12_HOLE_ALTO_C from here
        path = diagram.render_and_open(note_name)
        print(f"    Opened fingering picture for {note_name}: {path}")
    input("    Get your fingers positioned on the holes shown, then press Enter when ready...")
    for i in (3, 2, 1):
        print(f"  {i}...")
        time.sleep(0.6)
    print("  PLAY NOW (hold the note steady)...")

    audio = sd.rec(int(RECORD_SECONDS * SAMPLE_RATE), samplerate=SAMPLE_RATE, channels=1, dtype="float32")
    remaining = RECORD_SECONDS
    while remaining > 0:
        print(f"\r  listening... {remaining:0.1f}s left ", end="", flush=True)
        step = min(0.2, remaining)
        time.sleep(step)
        remaining -= step
    sd.wait()
    print("\r  done listening.                  ")
    audio = audio[:, 0]

    chunk = int(SAMPLE_RATE * 0.08)
    readings = []
    for start in range(0, len(audio) - chunk, chunk):
        freq, conf = detect_pitch(audio[start:start + chunk], SAMPLE_RATE)
        if freq is not None and conf > 0.4:
            readings.append(freq)

    if len(readings) < 3:
        print("  Couldn't get a clean pitch reading -- let's try that note again.")
        return record_note(label, note_name)

    # use the median of the most consistent cluster, not a plain mean
    readings = np.array(sorted(readings))
    mid = readings[len(readings) // 4: len(readings) * 3 // 4 + 1]
    freq = float(np.median(mid if len(mid) else readings))
    print(f"  Got it: {freq:.1f} Hz")
    return freq


def main():
    import sys

    wanted = set(a.upper() for a in sys.argv[1:])
    slots_to_do = [s for s in NOTE_SLOTS if not wanted or s[0] in wanted]
    if wanted:
        unknown = wanted - {s[0] for s in NOTE_SLOTS}
        if unknown:
            print(f"Unknown slot(s) {unknown}; valid slots are L R A Y X. Exiting.")
            return

    print("Ocarina calibration")
    if slots_to_do != NOTE_SLOTS:
        print("Calibrating only:", ", ".join(f"{s}({n})" for s, l, n in slots_to_do))
    print("Make sure your mic is selected as the default input device (or run")
    print("sounddevice list below to confirm the right one is default).")
    print(sd.query_devices())

    # merge with any existing calibration rather than clobbering it
    notes = {}
    if os.path.exists(OUT_FILE):
        with open(OUT_FILE, "r", encoding="utf-8") as f:
            notes = json.load(f)

    for slot, label, note_name in slots_to_do:
        notes[slot] = record_note(label, note_name)

    with open(OUT_FILE, "w", encoding="utf-8") as f:
        json.dump(notes, f, indent=2)

    print("\nCalibration saved to", OUT_FILE)
    for slot, freq in notes.items():
        print(f"  {slot}: {freq:.1f} Hz")
    print("\nIf two notes came out suspiciously close in frequency, try that")
    print("note again with a steadier breath, then re-run this script.")


if __name__ == "__main__":
    main()

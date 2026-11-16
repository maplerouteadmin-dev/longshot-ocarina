"""Same as translator.py but with the ocarina-up gate forced ON permanently,
to isolate whether the gate-flicker or the detection itself is causing extra
spurious note presses. Ctrl+C to stop -- always release the game's ocarina
UI (or close Longshot) before/after, since this injects constantly."""
import json
import time

import numpy as np
import sounddevice as sd

from pitch import detect_pitch, SAMPLE_RATE
import gamepad

CHUNK_SECONDS = 0.08
SILENCE_RELEASE_CHUNKS = 3
MAX_CENTS_OFF = 150
CONFIRM_CHUNKS = 2
MIN_HOLD_SECONDS = 0.15


def cents_between(f1, f2):
    return 1200.0 * np.log2(f1 / f2)


def nearest_note(freq, notes):
    best_slot, best_dist = None, 1e9
    for slot, note_freq in notes.items():
        for octave_mult in (0.5, 1.0, 2.0):
            dist = abs(cents_between(freq, note_freq * octave_mult))
            if dist < best_dist:
                best_slot, best_dist = slot, dist
    if best_dist <= MAX_CENTS_OFF:
        return best_slot
    return None


def main():
    with open("notes.json", "r", encoding="utf-8") as f:
        notes = json.load(f)
    print("Loaded calibrated notes:", notes)
    print("ALWAYS LISTENING (no gate). Ctrl+C to stop.")

    gamepad.connect()
    held_slot = None
    held_slot_press_time = None
    quiet_count = 0
    candidate_slot = None
    candidate_count = 0

    def press_slot(slot):
        nonlocal held_slot, held_slot_press_time
        gamepad.press(slot)
        held_slot = slot
        held_slot_press_time = time.monotonic()

    def release_held():
        nonlocal held_slot, held_slot_press_time
        if held_slot is None:
            return
        elapsed = time.monotonic() - held_slot_press_time
        if elapsed < MIN_HOLD_SECONDS:
            time.sleep(MIN_HOLD_SECONDS - elapsed)
        gamepad.release(held_slot)
        held_slot = None
        held_slot_press_time = None

    chunk_len = int(SAMPLE_RATE * CHUNK_SECONDS)
    stream = sd.InputStream(samplerate=SAMPLE_RATE, channels=1, dtype="float32", blocksize=chunk_len)
    stream.start()

    try:
        while True:
            audio, _ = stream.read(chunk_len)
            freq, conf = detect_pitch(audio[:, 0], SAMPLE_RATE)

            if freq is None:
                quiet_count += 1
                candidate_slot = None
                candidate_count = 0
                if quiet_count >= SILENCE_RELEASE_CHUNKS and held_slot is not None:
                    release_held()
                continue
            quiet_count = 0

            slot = nearest_note(freq, notes)
            if slot == held_slot:
                candidate_slot = None
                candidate_count = 0
                continue

            if slot == candidate_slot:
                candidate_count += 1
            else:
                candidate_slot = slot
                candidate_count = 1

            if candidate_count >= CONFIRM_CHUNKS:
                if held_slot is not None:
                    release_held()
                if slot is not None:
                    press_slot(slot)
                    print(f"\r{freq:6.1f} Hz -> note {slot}   ", end="", flush=True)
                candidate_slot = None
                candidate_count = 0
    except KeyboardInterrupt:
        pass
    finally:
        if held_slot is not None:
            release_held()
        gamepad.disconnect()
        stream.stop()
        stream.close()
        print("\nStopped.")


if __name__ == "__main__":
    main()

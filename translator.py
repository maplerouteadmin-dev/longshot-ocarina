"""
Ocarina-to-virtual-controller translator.

Listens to the mic ONLY while the game itself reports the ocarina is up
(read directly from Longshot's process memory -- see ocarina_flag.py), so
background noise/talking never registers as notes while you're not actually
playing. Detects which of your calibrated notes is closest to what you're
playing, and holds down the matching button on a virtual Xbox controller
(ViGEmBus), bound in longshot_options.ini's pad_note_l/r/a/y/x fields. This
replaces an earlier keyboard-based approach (key_note_*) that turned out to
disable real-controller input entirely whenever any key_note_* slot was
bound.

Requires notes.json from calibrate.py.
"""
import json
import queue
import time

import numpy as np
import sounddevice as sd

from pitch import detect_pitch, SAMPLE_RATE
import gamepad
import ocarina_flag

FLAG_POLL_SECONDS = 0.1  # how often to re-check the ocarina-up memory flag

OCARINA_DOWN_GRACE_SECONDS = 0.5  # the game's "ocarina up" flag pulses briefly during
                                   # normal note-to-note playing -- require it to read
                                   # "down" continuously for this long before actually
                                   # cutting off listening, so mid-song blips don't count
CHUNK_SECONDS = 0.05
SILENCE_RELEASE_CHUNKS = 3  # how many quiet chunks before we let go of a held note
MAX_CENTS_OFF = 150  # how far (in cents) a reading may be from a calibrated note and still count
CONFIRM_SECONDS = 0.075  # how long a new note must read consistently before we switch to it
                          # (filters out brief attack-transient blips). Time-based rather than
                          # chunk-counted so it isn't locked to whole multiples of CHUNK_SECONDS --
                          # this sits between 1 chunk (0.05s, too jittery) and 2 chunks (0.10s).
MIN_HOLD_SECONDS = 0.15  # guarantee every virtual-button press lasts at least this long,
                          # so a too-brief press (e.g. from the ocarina-up flag flickering
                          # mid-note) doesn't get silently ignored by the game


def cents_between(f1: float, f2: float) -> float:
    return 1200.0 * np.log2(f1 / f2)


def nearest_note(freq: float, notes: dict):
    # Octave-tolerant: a physically limited ocarina (especially the highest
    # note) or a harder/softer breath than calibration can shift what you
    # actually produce by a full octave. Check the calibrated pitch AND its
    # octave up/down, and match whichever is closest -- the NOTE identity is
    # what we care about, not which octave it came out in.
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
    print("Listening automatically whenever the game shows the ocarina is up. Ctrl+C here to quit.")

    gamepad.connect()
    print("Virtual controller connected.")

    listening = ocarina_flag.is_up()
    print("[Listening ON]" if listening else "[Listening OFF]", "(ocarina up/down, read from the game)")
    held_slot = None
    held_slot_press_time = None
    quiet_count = 0
    candidate_slot = None
    candidate_since = None
    last_flag_check = 0.0
    down_since = None  # when the flag first started reading "down" (None while up)

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

    # Persistent callback-based stream: avoids both the per-chunk device
    # reopen overhead of calling sd.rec() in a loop (way too slow -- each
    # call re-opens the WASAPI device) AND the earlier manual
    # InputStream.read(chunk_len) blocking-read quirk that produced
    # consistently halved frequency readings on this webcam device.
    # PortAudio delivers audio to the callback on its own schedule; we just
    # buffer it into fixed-size windows ourselves.
    audio_queue = queue.Queue()

    def _callback(indata, frames, time_info, status):
        audio_queue.put(indata[:, 0].copy())

    audio_stream = sd.InputStream(
        samplerate=SAMPLE_RATE, channels=1, dtype="float32", blocksize=chunk_len, callback=_callback
    )
    audio_stream.start()

    try:
        while True:
            now = time.monotonic()
            if now - last_flag_check >= FLAG_POLL_SECONDS:
                last_flag_check = now
                now_up = ocarina_flag.is_up()

                if now_up:
                    down_since = None
                    if not listening:
                        listening = True
                        print("\n[Listening ON]")
                else:
                    if down_since is None:
                        down_since = now
                    elif listening and (now - down_since) >= OCARINA_DOWN_GRACE_SECONDS:
                        listening = False
                        print("\n[Listening OFF]")
                        release_held()
                        quiet_count = 0
                        candidate_slot = None
                        candidate_since = None

            if not listening:
                # drain any buffered audio so we don't process a stale
                # backlog the moment listening turns back on
                try:
                    while True:
                        audio_queue.get_nowait()
                except queue.Empty:
                    pass
                time.sleep(0.02)
                continue

            try:
                audio = audio_queue.get(timeout=0.5)
            except queue.Empty:
                continue
            freq, conf = detect_pitch(audio, SAMPLE_RATE)

            if freq is None:
                quiet_count += 1
                candidate_slot = None
                candidate_since = None
                if quiet_count >= SILENCE_RELEASE_CHUNKS and held_slot is not None:
                    release_held()
                continue
            quiet_count = 0

            slot = nearest_note(freq, notes)

            if slot == held_slot:
                candidate_slot = None
                candidate_since = None
                continue

            # require the SAME new slot to read consistently for
            # CONFIRM_SECONDS before actually switching -- a single blip
            # during the attack transient of a note shouldn't trigger a
            # button press. Time-based, not chunk-counted, so it isn't
            # locked to whole multiples of CHUNK_SECONDS.
            now2 = time.monotonic()
            if slot == candidate_slot:
                confirmed = (now2 - candidate_since) >= CONFIRM_SECONDS
            else:
                candidate_slot = slot
                candidate_since = now2
                confirmed = False

            if confirmed:
                # Only block starting a brand-new note during the post-"down"
                # grace window when we're not ALREADY mid-note (held_slot is
                # None) -- that's the real "ocarina might genuinely be put
                # away" case. The underlying flag flickers constantly even
                # during normal continuous play, so blocking note-to-note
                # switches too (held_slot already set) made every note feel
                # like it needed a long hold to register.
                starting_new = slot is not None and slot != held_slot
                if starting_new and down_since is not None and held_slot is None:
                    candidate_slot = None
                    candidate_since = None
                    continue
                if held_slot is not None:
                    release_held()
                if slot is not None:
                    press_slot(slot)
                    print(f"\r{freq:6.1f} Hz -> note {slot}   ", end="", flush=True)
                candidate_slot = None
                candidate_since = None
    except KeyboardInterrupt:
        pass
    finally:
        if held_slot is not None:
            gamepad.release(held_slot)
        gamepad.disconnect()
        audio_stream.stop()
        audio_stream.close()
        print("\nStopped.")


if __name__ == "__main__":
    main()

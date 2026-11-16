"""Always-on listening test: no toggle, no key injection, just prints what it hears."""
import json

import sounddevice as sd

from pitch import detect_pitch, SAMPLE_RATE

with open("notes.json", "r", encoding="utf-8") as f:
    notes = json.load(f)
print("Calibrated notes:", notes)
print("Listening continuously. Ctrl+C to stop.\n")

chunk_len = int(SAMPLE_RATE * 0.08)
stream = sd.InputStream(samplerate=SAMPLE_RATE, channels=1, dtype="float32", blocksize=chunk_len)
stream.start()

try:
    while True:
        audio, _ = stream.read(chunk_len)
        freq, conf = detect_pitch(audio[:, 0], SAMPLE_RATE)
        if freq is None:
            continue
        # show distance to every calibrated note, not just the closest match
        import numpy as np
        dists = {slot: abs(1200 * np.log2(freq / f)) for slot, f in notes.items()}
        closest = min(dists, key=dists.get)
        print(f"{freq:7.1f} Hz (conf {conf:.2f})  closest: {closest} ({dists[closest]:.0f} cents off)")
except KeyboardInterrupt:
    pass
finally:
    stream.stop()
    stream.close()
    print("\nStopped.")

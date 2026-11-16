"""Command-line version of the app's Play tab: python translator.py"""
import time

import config
from engine import Engine


def main():
    cfg = config.load()
    if not config.note_freqs(cfg):
        print("No calibrated notes -- run the app's Calibrate tab or calibrate.py first.")
        return
    eng = Engine(cfg)
    eng.start()
    print(f"Mic: {eng.mic_label}   gate: {cfg['gate_mode']}   Ctrl+C to quit.")
    try:
        while True:
            while not eng.status.empty():
                item = eng.status.get()
                if item[0] == "gate":
                    print(("\n[listening]" if item[1] else "\n[not listening]") + f" ({item[2]})")
                else:
                    d = item[1]
                    for kind, key in d.events:
                        if kind == "press":
                            print(f"\r{d.freq:7.1f} Hz -> {key}   ", end="", flush=True)
            time.sleep(0.05)
    except KeyboardInterrupt:
        pass
    finally:
        eng.stop()
        print("\nStopped.")


if __name__ == "__main__":
    main()

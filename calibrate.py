"""Command-line calibration (the app's Calibrate tab does the same thing with a UI).

    python calibrate.py              # all five notes
    python calibrate.py X Y B        # just these buttons
"""
import sys

import audio
import calibration
import config
import diagram

TAKES = 3


def main():
    cfg = config.load()
    wanted = {a.upper() for a in sys.argv[1:]}
    defs = [d for d in config.NOTE_DEFS if not wanted or d["button"] in wanted]

    idx, name, sr = audio.find_device(cfg["mic_name"])
    print(f"Mic: {name} ({sr} Hz)")
    an = audio.Analyzer(idx, sr)
    an.start()
    try:
        input("\nStay quiet for 2 seconds to measure background noise -- press Enter to start...")
        floor = audio.measure_noise_floor(an)
        cfg["match"]["noise_floor"] = floor
        print(f"  background level: {floor:.4f}")
        params = config.match_params(cfg)

        for d in defs:
            print(f"\n>>> {d['button']}: {d['label']} ({d['pitch']})")
            diagram.render_and_open(d["pitch"])
            takes = []
            while len(takes) < TAKES:
                input(f"  Take {len(takes) + 1}/{TAKES}: press Enter, then play the note whenever you're ready "
                      "and hold it ~2s (recording starts when it hears you)...")
                take = calibration.record_take(an, params, wait_for_note=15,
                                               on_start=lambda: print("  recording..."))
                if take is None:
                    print("  Didn't hear a steady note -- try again.")
                    continue
                print(f"  {take['hz']:.1f} Hz (wandered {take['spread_cents']:.0f} cents)")
                takes.append(take)
            cfg["notes"][d["button"]] = calibration.combine(takes)
            print(f"  saved {cfg['notes'][d['button']]['hz']:.1f} Hz")

        config.save(cfg)
        for w in calibration.check_notes(cfg["notes"]):
            print("WARNING:", w)
        print(f"\nSaved to {config.CONFIG_PATH}")
    finally:
        an.stop()


if __name__ == "__main__":
    main()

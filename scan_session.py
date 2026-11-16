"""Interactive scan-and-diff session to find Longshot's "ocarina is up" flag.

Run this, follow the prompts (put the ocarina up/away when asked). Each
round's snapshots are saved to disk as they're taken, so a crash doesn't
waste the cycles you already did. Candidates are narrowed progressively in
pure numpy (never materialized as one giant Python dict), which is what
caused the earlier MemoryError.
"""
import pickle
import time

import memscan


def take_snapshot(pm, regions, label):
    input(f"\n>>> {label}, then press Enter...")
    print("Snapshotting (this can take a little while)...")
    t0 = time.time()
    snap = memscan.snapshot(pm, regions)
    print(f"Done in {time.time() - t0:.1f}s, {len(snap)} regions captured.")
    return snap


def main():
    pm = memscan.attach()
    print("Enumerating writable regions...")
    regions = memscan.list_writable_regions(pm)
    print(f"{len(regions)} regions.")

    candidates = None
    for cycle in range(1, 4):
        print(f"\n=== Cycle {cycle} of 3 ===")
        down_snap = take_snapshot(pm, regions, "Make sure the ocarina is PUT AWAY (not up)")
        up_snap = take_snapshot(pm, regions, "Now bring the ocarina UP")

        print("Diffing...")
        t0 = time.time()
        if candidates is None:
            candidates = memscan.initial_candidates(down_snap, up_snap)
        else:
            candidates = memscan.narrow_candidates(candidates, down_snap, up_snap)
        print(f"Diff done in {time.time() - t0:.1f}s. Surviving candidates: {memscan.total_count(candidates)}")

        with open(f"candidates_after_cycle{cycle}.pkl", "wb") as f:
            pickle.dump(candidates, f)

        if cycle < 3:
            input(">>> Put the ocarina away again, then press Enter to continue...")

    final = memscan.to_list(candidates, limit=200)
    print(f"\n{len(final)} final candidate(s) (capped at 200):")
    for addr, down_val, up_val in sorted(final):
        print(f"  0x{addr:X}: {down_val} (down) -> {up_val} (up)")

    with open("candidates_final.pkl", "wb") as f:
        pickle.dump(candidates, f)
    print("\nSaved to candidates_final.pkl")


if __name__ == "__main__":
    main()

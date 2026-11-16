"""Continue narrowing an existing candidate set with more cycles, without
redoing the cycles already saved."""
import pickle
import sys
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
    start_file = sys.argv[1] if len(sys.argv) > 1 else "candidates_final.pkl"
    extra_cycles = int(sys.argv[2]) if len(sys.argv) > 2 else 3

    with open(start_file, "rb") as f:
        candidates = pickle.load(f)
    print(f"Loaded {memscan.total_count(candidates)} candidates from {start_file}")

    pm = memscan.attach()
    regions = memscan.list_writable_regions(pm)

    for cycle in range(1, extra_cycles + 1):
        print(f"\n=== Extra cycle {cycle} of {extra_cycles} ===")
        down_snap = take_snapshot(pm, regions, "Make sure the ocarina is PUT AWAY (not up)")
        up_snap = take_snapshot(pm, regions, "Now bring the ocarina UP")
        print("Narrowing...")
        candidates = memscan.narrow_candidates(candidates, down_snap, up_snap)
        count = memscan.total_count(candidates)
        print(f"Surviving candidates: {count}")
        with open("candidates_final.pkl", "wb") as f:
            pickle.dump(candidates, f)
        if count <= 30:
            print("Down to a small enough set -- stopping early.")
            break
        if cycle < extra_cycles:
            input(">>> Put the ocarina away again, then press Enter to continue...")

    final = memscan.to_list(candidates, limit=200)
    print(f"\n{len(final)} final candidate(s):")
    for addr, down_val, up_val in sorted(final):
        print(f"  0x{addr:X}: {down_val} (down) -> {up_val} (up)")


if __name__ == "__main__":
    main()

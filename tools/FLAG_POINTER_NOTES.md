# Ocarina flag across Longshot restarts

## What works: fixed offsets in the guest-memory arena
Longshot runs the game in an emulated console whose memory is its biggest
private reservation (64 GB+, at 0x100000000000 so far, ~10 GB committed). The
normal scan (`flag_scan.py`) skips regions over 64 MB, so it never searched it.

`toolsrena_scan.py` scans just the arena: `down` / `up` rounds, `hold <0|1> <secs>`
(drop spots that flicker while playing), `report`. Results from 2026-11-16:
192,635 → 35,443 after two rounds. After a *verified* restart (new pid)
30,789 still tracked the ocarina; 20,981 stayed steady through 15 s of
playing and 6 s put away. `flag_spots.py` keeps 31 of them (one per page,
spread out), and `GameFlag` takes a 2/3 majority (1 = up, 0 = away). It falls
back to the scanned heap address if the vote fails.

## What failed
- Stage A (fixed offset in the flag's 16 MB heap block): the offset changes.
- Stage B (`ptrscan.py`, pointer chains from `longshot_vk.dll`): 199 chains
  looked fine, but the "restart" test hadn't really restarted Longshot; after a
  real restart 0 of 199 resolved. Always check the pid changed.

## If a Longshot update breaks it
In game, ocarina away: `python toolsrena_scan.py down`; up: `... up`; repeat once.
Restart Longshot (check the pid changed), then do `down`/`up` again, and
`hold 1 15` while playing and `hold 0 6` while put away. Then regenerate
`flag_spots.py` from `arena_state\cands.npy` (one offset per page, ~31).

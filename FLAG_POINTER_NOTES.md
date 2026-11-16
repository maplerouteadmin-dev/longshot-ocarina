# Ocarina flag across Longshot restarts — status

## Done
- Scan fix (3d539db): Verify unlocks at <=300 candidates or after 3 rounds
  (Longshot keeps ~42 copies of the flag, so the scan never got below 40).
- `flag_probe.py`: shows the flag's allocation base, size and offset.

## Stage A result: fails
| run | flag | alloc size | offset | same-size allocs |
|---|---|---|---|---|
| before restart | 0x1F30A2FEBA5 | 0x1000000 | 0x2FEBA5 | 57 (index 13) |
| after restart  | 0x1F2C5A036C2 | 0x1000000 | 0xA036C2 | 57 (index 10) |

The flag sits in one of 57 16 MB heap blocks, at a different offset each time,
and the bytes around it differ (only 1703 of 4096 bytes on its page match).
The scan may also pick a different one of the ~42 copies each time.

## Next: Stage B (pointer scan)
- Reuse `memscan.list_writable_regions` / `snapshot` to read memory.
- Build a sorted numpy array of 8-byte-aligned values that point into the
  writable regions, with their locations.
- Search back from the flag (and ideally from every surviving copy): depth
  up to 4, offset up to 0x2000, ending at a static address in
  longshot.exe or a DLL image (module + offset). Save the chains to disk.
- After a restart and re-scan, keep only the chains that resolve to an
  address whose value tracks the ocarina (any copy counts, not just the
  saved one).
- Then add `flag.locator` in `config.py` and resolve it in `GameFlag`,
  falling back to the saved address, and show this on the Game Flag tab.

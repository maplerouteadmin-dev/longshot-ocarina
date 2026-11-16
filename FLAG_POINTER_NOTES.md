# Ocarina flag across Longshot restarts — solved

- The flag sits at a different heap offset each run (Stage A failed: the
  offset changed from 0x2FEBA5 to 0xA036C2 inside one of 57 16 MB blocks).
- `ptrscan.py` (depth 4, offsets up to 0x10000) found 199 chains rooted in
  `longshot_vk.dll`. After a full restart, 196 still tracked the ocarina.
- `flag_chains.py` keeps 16 of them. `GameFlag` follows all of them about
  once a second and uses the address most of them agree on (byte 1 = up,
  0 = put away). It falls back to the scanned address if none resolve.
- If a Longshot update breaks the chains: scan the flag in the app, then run
  `python ptrscan.py scan` (set PS_DEPTH=6 and PS_OFF=0x10000; ~4 min per
  level). Restart Longshot, run `python ptrscan.py check 0` with the ocarina
  put away and `python ptrscan.py check 1` with it out, then regenerate
  `flag_chains.py` from `ptr_chains.json`.

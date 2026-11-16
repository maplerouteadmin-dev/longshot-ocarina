# Ocarina flag across Longshot restarts — status

Stopped early: the 5-hour usage budget was already at 71% when this started.

Done:
- `flag_probe.py` (Stage A): for the current flag address, prints its
  allocation base, allocation size, offset in the allocation, and how many
  allocations share that size.

Next steps:
1. In the app, Game Flag tab -> Start scan -> "Use this flag".
2. Run `python flag_probe.py` with Longshot running and note the three lines.
3. Restart Longshot completely, scan again, run the probe again.
4. If size and offset match and the size is unique (or near unique), have
   `GameFlag` find the allocation by size and read base + offset (setting
   `flag.locator = {"alloc_size": ..., "offset": ...}`), falling back to the
   saved raw address.
5. If they don't match, do Stage B: a pointer scan from a module-static
   address (see the original brief).

`flag.address` was assumed to be a hex string or int in `dist\config.json`;
if that's wrong, pass the address as an argument instead.

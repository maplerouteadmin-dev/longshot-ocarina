"""Stage A probe: where does the ocarina flag live inside Longshot's memory?

Usage:  python flag_probe.py [hex_address]
(default: flag.address from dist\\config.json). Prints the containing
allocation's base/size, the flag's offset in it, and how many other
allocations share that exact size. Run it after each Longshot restart +
re-scan and compare the offset/size lines.
"""
import ctypes, ctypes.wintypes as wt, json, os, sys
import pymem

class MBI(ctypes.Structure):
    _fields_ = [("BaseAddress", ctypes.c_ulonglong), ("AllocationBase", ctypes.c_ulonglong),
                ("AllocationProtect", wt.DWORD), ("PartitionId", wt.WORD),
                ("RegionSize", ctypes.c_ulonglong), ("State", wt.DWORD),
                ("Protect", wt.DWORD), ("Type", wt.DWORD)]

k32 = ctypes.WinDLL("kernel32", use_last_error=True)
k32.VirtualQueryEx.argtypes = [wt.HANDLE, ctypes.c_void_p, ctypes.POINTER(MBI), ctypes.c_size_t]
k32.VirtualQueryEx.restype = ctypes.c_size_t


def allocations(h):
    """{AllocationBase: total size} over all committed/reserved regions."""
    out, addr, m = {}, 0, MBI()
    while addr < 0x7FFFFFFFFFFF and k32.VirtualQueryEx(h, ctypes.c_void_p(addr), ctypes.byref(m), ctypes.sizeof(m)):
        if m.State != 0x10000:  # not MEM_FREE
            out[m.AllocationBase] = out.get(m.AllocationBase, 0) + m.RegionSize
        addr = m.BaseAddress + m.RegionSize
    return out


def main():
    if len(sys.argv) > 1:
        flag = int(sys.argv[1], 16)
    else:
        cfg = json.load(open(os.path.join(os.path.dirname(os.path.dirname(os.path.abspath(__file__))), "dist", "config.json")))
        flag = int(str(cfg["flag"]["address"]), 0)
    pm = pymem.Pymem("longshot.exe")
    allocs = allocations(pm.process_handle)
    base = max(b for b in allocs if b <= flag)
    size = allocs[base]
    same = sum(1 for s in allocs.values() if s == size)
    print(f"flag      0x{flag:X}  value={pm.read_bytes(flag, 1)[0]}")
    print(f"allocbase 0x{base:X}  size=0x{size:X}  offset=0x{flag - base:X}")
    print(f"allocations with this exact size: {same} (of {len(allocs)})")


if __name__ == "__main__":
    main()

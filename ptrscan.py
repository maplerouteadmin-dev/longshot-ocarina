"""Stage B: pointer scan for Longshot's ocarina flag.

  python ptrscan.py scan            # from flag.address in dist\\config.json -> ptr_chains.json
  python ptrscan.py check <0|1>     # after a restart: keep chains whose target now reads <value>
  python ptrscan.py show            # print the surviving chains (shortest first)

A chain is (module, module_offset, [o_k, ..., o_1]):
  addr = module_base + module_offset; for o in offsets: addr = read_u64(addr) + o
and the final addr is the flag byte.
"""
import ctypes, ctypes.wintypes as wt, json, os, struct, sys, time
import numpy as np
import pymem

HERE = os.path.dirname(os.path.abspath(__file__))
CHAINS = os.path.join(HERE, "ptr_chains.json")
MAX_DEPTH = int(os.environ.get("PS_DEPTH", 4))
FIRST_OFF = 0x20000     # the flag may sit deep inside a big game-state struct
MAX_OFF = int(os.environ.get("PS_OFF", "0x2000"), 0)
MAX_TARGETS = 300_000   # per level, to keep memory and time bounded
WRITABLE = {0x04, 0x08, 0x40, 0x80}


class MBI(ctypes.Structure):
    _fields_ = [("BaseAddress", ctypes.c_ulonglong), ("AllocationBase", ctypes.c_ulonglong),
                ("AllocationProtect", wt.DWORD), ("PartitionId", wt.WORD),
                ("RegionSize", ctypes.c_ulonglong), ("State", wt.DWORD),
                ("Protect", wt.DWORD), ("Type", wt.DWORD)]


k32 = ctypes.WinDLL("kernel32", use_last_error=True)
k32.VirtualQueryEx.argtypes = [wt.HANDLE, ctypes.c_void_p, ctypes.POINTER(MBI), ctypes.c_size_t]
k32.VirtualQueryEx.restype = ctypes.c_size_t


def regions(h):
    """Committed, writable, non-guard regions: [(base, size, is_image)]."""
    out, addr, m = [], 0, MBI()
    while addr < 0x7FFFFFFFFFFF and k32.VirtualQueryEx(h, ctypes.c_void_p(addr), ctypes.byref(m), ctypes.sizeof(m)):
        if m.State == 0x1000 and (m.Protect & 0xFF) in WRITABLE and not m.Protect & 0x100:
            out.append((m.BaseAddress, m.RegionSize, m.Type == 0x1000000))
        addr = m.BaseAddress + m.RegionSize
    return out


def modules(pm):
    return [(m.name, m.lpBaseOfDll, m.SizeOfImage) for m in pm.list_modules()]


def read_region(pm, base, size, chunk=64 << 20):
    for off in range(0, size, chunk):
        n = min(chunk, size - off)
        try:
            yield base + off, pm.read_bytes(base + off, n)
        except Exception:
            continue


def find_pointers(pm, regs, targets, maxoff):
    """All 8-aligned locations L whose u64 value v has some target t with 0 <= t - v <= maxoff.
    Returns arrays (loc, target_index, offset)."""
    tg = np.asarray(targets, dtype=np.uint64)
    lo, hi = int(tg.min()) - maxoff, int(tg.max())
    locs, tis, offs = [], [], []
    for base, size, _ in regs:
        for cbase, data in read_region(pm, base, size):
            v = np.frombuffer(data, dtype=np.uint64, count=len(data) // 8)
            cand = np.nonzero((v >= lo) & (v <= hi))[0]
            if not len(cand):
                continue
            vv = v[cand]
            idx = np.searchsorted(tg, vv, side="left")
            ok = idx < len(tg)
            cand, vv, idx = cand[ok], vv[ok], idx[ok]
            d = tg[idx] - vv
            ok = d <= maxoff
            locs.append(np.uint64(cbase) + cand[ok].astype(np.uint64) * np.uint64(8))
            tis.append(idx[ok]); offs.append(d[ok])
    if not locs:
        return np.zeros(0, np.uint64), np.zeros(0, np.int64), np.zeros(0, np.uint64)
    return np.concatenate(locs), np.concatenate(tis), np.concatenate(offs)


def scan(flag):
    pm = pymem.Pymem("longshot.exe")
    regs = regions(pm.process_handle)
    mods = modules(pm)
    print(f"{len(regs)} writable regions, {sum(r[1] for r in regs) >> 20} MB", flush=True)
    targets = np.array([flag], dtype=np.uint64)
    levels = []          # per level: (locs, target_idx_into_prev, offs)
    chains = []
    for depth in range(1, MAX_DEPTH + 1):
        t0 = time.time()
        locs, tis, offs = find_pointers(pm, regs, targets, FIRST_OFF if depth == 1 else MAX_OFF)
        levels.append((targets, locs, tis, offs))
        roots = 0
        for name, mb, ms in mods:
            hit = np.nonzero((locs >= np.uint64(mb)) & (locs < np.uint64(mb + ms)))[0]
            for i in hit[:2000].tolist():
                chains.append(build_chain(levels, depth, i, name, int(locs[i]) - mb))
                roots += 1
        print(f"depth {depth}: {len(locs)} pointers, {roots} static roots, {time.time() - t0:.0f}s", flush=True)
        uniq = np.unique(locs)
        if len(uniq) > MAX_TARGETS:
            print(f"  too many targets ({len(uniq)}), stopping here")
            break
        targets = uniq
    json.dump({"flag": flag, "chains": chains}, open(CHAINS, "w"))
    print(f"saved {len(chains)} chains to {CHAINS}")


def build_chain(levels, depth, i, name, modoff):
    offsets = []
    for d in range(depth - 1, -1, -1):
        targets, locs, tis, offs = levels[d]
        offsets.append(int(offs[i]))
        tgt = int(targets[tis[i]])
        if d:
            prev_locs = levels[d - 1][1]
            # the target of this level is a location from the previous level; find one of its indices
            i = int(np.nonzero(prev_locs == np.uint64(tgt))[0][0])
    return [name, modoff, offsets]


def resolve(pm, chain, bases):
    name, modoff, offsets = chain
    addr = bases[name.lower()] + modoff
    for o in offsets:
        addr = struct.unpack("<Q", pm.read_bytes(addr, 8))[0] + o
    return addr


def check(value):
    pm = pymem.Pymem("longshot.exe")
    bases = {m.name.lower(): m.lpBaseOfDll for m in pm.list_modules()}
    data = json.load(open(CHAINS))
    keep = []
    for c in data["chains"]:
        try:
            if pm.read_bytes(resolve(pm, c, bases), 1)[0] == value:
                keep.append(c)
        except Exception:
            pass
    print(f"{len(keep)} of {len(data['chains'])} chains read {value}")
    data["chains"] = keep
    json.dump(data, open(CHAINS, "w"))


def show():
    ch = sorted(json.load(open(CHAINS))["chains"], key=lambda c: (len(c[2]), c[0] != "longshot.exe"))
    for c in ch[:15]:
        print(c[0], hex(c[1]), [hex(o) for o in c[2]])
    print(len(ch), "total")


if __name__ == "__main__":
    cmd = sys.argv[1] if len(sys.argv) > 1 else "scan"
    if cmd == "scan":
        cfg = json.load(open(os.path.join(HERE, "dist", "config.json")))
        scan(int(cfg["flag"]["address"]))
    elif cmd == "check":
        check(int(sys.argv[2]))
    else:
        show()

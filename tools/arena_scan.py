"""Find the ocarina flag inside Longshot's big guest-memory block ("arena").

The normal scan (flag_scan.py) skips regions over 64 MB, so it never looks in
the emulated console's memory, where game variables may sit at a fixed offset.

  python arena_scan.py down     # ocarina put away (first time: records every 0 byte)
  python arena_scan.py up       # ocarina up: keep bytes that went 0 -> 1
  python arena_scan.py down/up  # repeat to narrow down
  python arena_scan.py report   # print candidate offsets from the arena base
  python arena_scan.py test     # check saved offsets against a fresh (restarted) arena
State lives in the scratch dir given by ARENA_DIR (default: .\\arena_state).
"""
import ctypes, json, os, sys
import numpy as np
import pymem
from flag_probe import MBI, k32

STATE = os.environ.get("ARENA_DIR", os.path.join(os.path.dirname(os.path.abspath(__file__)), "arena_state"))
CHUNK = 64 << 20
MIN_RESERVE = 0x1000000000          # the guest arena is a huge (>=64 GB) private reservation


def arena(h):
    """(base, [(region_base, size)]) of the biggest private reservation's committed RW regions."""
    allocs, addr, m = {}, 0, MBI()
    while addr < 0x7FFFFFFFFFFF and k32.VirtualQueryEx(h, ctypes.c_void_p(addr), ctypes.byref(m), ctypes.sizeof(m)):
        if m.State != 0x10000:
            a = allocs.setdefault(m.AllocationBase, [0, []])
            a[0] += m.RegionSize
            if m.State == 0x1000 and m.Type == 0x20000 and m.Protect == 0x04:
                a[1].append((m.BaseAddress, m.RegionSize))
        addr = m.BaseAddress + m.RegionSize
    base, (size, regs) = max(allocs.items(), key=lambda kv: kv[1][0])
    assert size >= MIN_RESERVE, "no guest arena found"
    return base, regs


def chunks(regs):
    for b, s in regs:
        for o in range(0, s, CHUNK):
            yield b + o, min(CHUNK, s - o)


def main():
    cmd = sys.argv[1]
    os.makedirs(STATE, exist_ok=True)
    pm = pymem.Pymem("longshot.exe")
    base, regs = arena(pm.process_handle)
    cand_path = os.path.join(STATE, "cands.npy")
    if cmd == "report" or cmd == "test":
        offs = np.load(cand_path)
        if cmd == "report":
            print(f"arena 0x{base:X}: {len(offs)} candidates;", [hex(int(o)) for o in offs[:20]])
            return
        ok = []
        for o in offs.tolist():
            try:
                ok.append((hex(o), pm.read_bytes(base + o, 1)[0]))
            except Exception:
                pass
        print(f"arena 0x{base:X}: values at saved offsets:", ok[:20])
        return

    if cmd == "hold":
        # python arena_scan.py hold <0|1> <seconds>: keep candidates that read <value> the whole time
        want, secs = int(sys.argv[2]), float(sys.argv[3])
        import time
        offs = np.load(cand_path)
        pages = {}
        for k, o in enumerate(offs.tolist()):
            pages.setdefault(o & ~0xFFF, []).append(k)
        keep = np.ones(len(offs), bool)
        end, samples = time.time() + secs, 0
        while time.time() < end:
            for pg, ks in pages.items():
                try:
                    v = pm.read_bytes(base + pg, 4096)
                except Exception:
                    keep[ks] = False
                    continue
                for k in ks:
                    if v[int(offs[k]) - pg] != want:
                        keep[k] = False
            samples += 1
        offs = offs[keep]
        np.save(cand_path, offs)
        print(f"{samples} samples over {len(pages)} pages: {len(offs)} candidates left")
        return

    want = 0 if cmd == "down" else 1
    if cmd == "down" and not os.path.exists(cand_path) and not os.path.exists(os.path.join(STATE, "zeros.json")):
        # first pass: remember where every 0 byte is (packed bitmask per chunk)
        index = []
        for i, (cb, n) in enumerate(chunks(regs)):
            try:
                v = np.frombuffer(pm.read_bytes(cb, n), dtype=np.uint8)
            except Exception:
                continue
            np.save(os.path.join(STATE, f"z{i}.npy"), np.packbits(v == 0))
            index.append((i, cb - base, n))
        json.dump(index, open(os.path.join(STATE, "zeros.json"), "w"))
        print(f"arena 0x{base:X}: recorded {sum(x[2] for x in index) >> 20} MB")
        return
    if not os.path.exists(cand_path):
        # first 'up': candidates = was 0, now 1
        found = []
        for i, off, n in json.load(open(os.path.join(STATE, "zeros.json"))):
            try:
                v = np.frombuffer(pm.read_bytes(base + off, n), dtype=np.uint8)
            except Exception:
                continue
            z = np.unpackbits(np.load(os.path.join(STATE, f"z{i}.npy")))[:n].astype(bool)
            found.append(np.nonzero(z & (v == 1))[0].astype(np.uint64) + np.uint64(off))
            os.remove(os.path.join(STATE, f"z{i}.npy"))
        offs = np.concatenate(found) if found else np.zeros(0, np.uint64)
    else:
        offs = np.load(cand_path)
        keep = np.zeros(len(offs), bool)
        # read each candidate's surrounding chunk once
        order = np.argsort(offs)
        offs = offs[order]
        i = 0
        while i < len(offs):
            start = int(offs[i])
            j = int(np.searchsorted(offs, np.uint64(start + CHUNK)))
            span = int(offs[j - 1]) - start + 1
            try:
                v = np.frombuffer(pm.read_bytes(base + start, span), dtype=np.uint8)
                keep[i:j] = v[(offs[i:j] - np.uint64(start)).astype(np.int64)] == want
            except Exception:
                pass
            i = j
        offs = offs[keep]
    np.save(cand_path, offs)
    print(f"arena 0x{base:X}: {len(offs)} candidates")


if __name__ == "__main__":
    main()

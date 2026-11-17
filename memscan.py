"""
Scan-and-diff memory finder for Longshot's "ocarina is up" flag.

Standard Cheat-Engine-style technique, done in pure Python: snapshot all
writable/private memory, change game state, snapshot again, keep only the
addresses whose value changed consistently the same way across several
open/close cycles. Restricted to writable, private (heap, not file-mapped
textures/assets) regions under a size cap, since a small state flag won't
live inside a huge texture buffer and scanning all ~15GB+ of this process
would be impractically slow.
"""
import numpy as np

import procmem

MAX_REGION_SIZE = 64 * 1024 * 1024  # skip anything bigger than 64MB per region


def attach(process_name=None):
    pm = procmem.Process() if process_name is None else procmem.Process((process_name,))
    print(f"Attached to Longshot, pid={pm.process_id}")
    return pm


def list_writable_regions(pm):
    """Committed, writable, private (heap-like) regions up to MAX_REGION_SIZE: [(base, size)]."""
    return [(r.base, r.size) for r in pm.regions()
            if r.committed and r.private and r.writable and 0 < r.size <= MAX_REGION_SIZE]


def snapshot(pm, regions):
    """Read every region into a dict {base_address: numpy uint8 array}. Skips unreadable regions."""
    out = {}
    for base, size in regions:
        try:
            data = pm.read_bytes(base, size)
            out[base] = np.frombuffer(data, dtype=np.uint8)
        except Exception:
            continue
    return out


def initial_candidates(snap_a, snap_b):
    """Candidate set after the FIRST down->up diff, kept as per-region numpy
    arrays (never materialized as 70M individual Python dict entries, which
    is what caused the earlier MemoryError -- CPython dict entries are much
    heavier than the raw bytes they represent)."""
    candidates = {}  # base -> (local_offsets uint32 array, down_vals, up_vals)
    for base in snap_a:
        if base not in snap_b:
            continue
        a = snap_a[base]
        b = snap_b[base]
        if len(a) != len(b):
            continue
        mask = a != b
        if not mask.any():
            continue
        idx = np.nonzero(mask)[0]
        candidates[base] = (idx, a[idx], b[idx])
    return candidates


def narrow_candidates(candidates, snap_a, snap_b):
    """Re-check an existing (already small-ish) candidate set against a NEW
    down/up snapshot pair, keeping only addresses whose (down_val, up_val)
    pair is IDENTICAL to what it was before. Shrinks monotonically each
    round -- by round 2 or 3 this is cheap even though it started from ~70M
    candidates, since most regions/offsets get dropped by round 1 already
    having only a tiny surviving set if candidates is passed through
    narrow_candidates repeatedly rather than re-running initial_candidates."""
    survivors = {}
    for base, (idx, prev_down, prev_up) in candidates.items():
        if base not in snap_a or base not in snap_b:
            continue
        a = snap_a[base]
        b = snap_b[base]
        max_len = min(len(a), len(b))
        valid = idx < max_len
        idx_v = idx[valid]
        if len(idx_v) == 0:
            continue
        new_down = a[idx_v]
        new_up = b[idx_v]
        same = (new_down == prev_down[valid]) & (new_up == prev_up[valid])
        if same.any():
            keep = idx_v[same]
            survivors[base] = (keep, new_down[same], new_up[same])
    return survivors


def total_count(candidates):
    return sum(len(idx) for idx, _, _ in candidates.values())


def to_list(candidates, limit=200):
    """Flatten to [(absolute_address, down_val, up_val), ...], capped since
    this is only for final human-readable output after narrowing."""
    out = []
    for base, (idx, down_vals, up_vals) in candidates.items():
        for i, d, u in zip(idx, down_vals, up_vals):
            out.append((base + int(i), int(d), int(u)))
            if len(out) >= limit:
                return out
    return out

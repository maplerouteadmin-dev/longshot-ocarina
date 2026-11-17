"""Re-finds Longshot's "ocarina is up" byte after a relaunch moves it.

Wizard steps (driven by the app's Game Flag tab, or scan_cli.py):
  1. capture("down")  -- ocarina put away
  2. capture("up")    -- ocarina held up, NOT playing
  ...repeat 1-2 until few candidates remain...
  3. verify_while_playing() -- hold it up and play notes; keeps candidates
     that stay steady (the original flag pulsed during play)
  4. verify_down()    -- put it away; candidates must return to their down value

Compared to scan_session.py: the first "up" capture is diffed against the
"down" snapshot region by region instead of holding two full ~5GB snapshots,
later cycles only re-read regions that still have candidates, and by default
only on/off-style bytes (0<->1) are kept, so it converges in a few cycles.
"""
import time

import numpy as np

import memscan
import procmem
from ocarina_flag import PROCESS_NAME


class FlagScanner:
    def __init__(self, bool_only=True, progress=None):
        self.bool_only = bool_only
        self.progress = progress or (lambda msg: None)
        self.pm = None
        self.regions = []
        self.candidates = None   # base -> (offsets int64, down_vals uint8, up_vals uint8)
        self._down = None        # pending "down" capture
        self.cycles = 0
        self.steady = {}         # addr -> fraction of play-time readings at up value

    def attach(self):
        self.pm = procmem.Process()
        self.regions = memscan.list_writable_regions(self.pm)
        self.progress(f"Attached to {PROCESS_NAME} ({len(self.regions)} memory regions)")

    def count(self):
        if self.candidates is None:
            return None
        return int(sum(len(o) for o, _, _ in self.candidates.values()))

    def _read(self, base, size):
        try:
            return np.frombuffer(self.pm.read_bytes(base, size), dtype=np.uint8)
        except Exception:
            return None

    def capture(self, state):
        if self.pm is None:
            self.attach()
        t0 = time.monotonic()
        if state == "down":
            if self.candidates is None:
                self._down = {}
                for base, size in self.regions:
                    data = self._read(base, size)
                    if data is not None:
                        self._down[base] = data.copy()
            else:
                self._down = {}
                for base, (offs, _, _) in self.candidates.items():
                    data = self._read(base, int(offs.max()) + 1)
                    if data is not None:
                        self._down[base] = data[offs].copy()
            self.progress(f"Captured 'put away' in {time.monotonic() - t0:.1f}s")
            return

        if self._down is None:
            raise RuntimeError("capture('down') first")
        if self.candidates is None:
            cands = {}
            for base, size in self.regions:
                down = self._down.get(base)
                if down is None:
                    continue
                up = self._read(base, size)
                if up is None or len(up) != len(down):
                    continue
                mask = down != up
                if self.bool_only:
                    mask &= (down <= 1) & (up <= 1)
                if mask.any():
                    offs = np.nonzero(mask)[0].astype(np.int64)
                    cands[base] = (offs, down[offs].copy(), up[offs].copy())
        else:
            cands = {}
            for base, (offs, prev_down, prev_up) in self.candidates.items():
                down = self._down.get(base)
                up = self._read(base, int(offs.max()) + 1)
                if down is None or up is None:
                    continue
                up = up[offs]
                keep = (down == prev_down) & (up == prev_up)
                if keep.any():
                    cands[base] = (offs[keep], prev_down[keep], prev_up[keep])
        self.candidates = cands
        self._down = None
        self.cycles += 1
        self.progress(f"Cycle {self.cycles}: {self.count()} candidates ({time.monotonic() - t0:.1f}s)")

    def addresses(self, limit=None):
        out = []
        for base, (offs, down, up) in self.candidates.items():
            for o, d, u in zip(offs, down, up):
                out.append((base + int(o), int(d), int(u)))
        out.sort()
        return out[:limit] if limit else out

    def _poll(self, addrs, seconds):
        samples = {a: [] for a, _, _ in addrs}
        end = time.monotonic() + seconds
        while time.monotonic() < end:
            for a, _, _ in addrs:
                try:
                    samples[a].append(self.pm.read_bytes(a, 1)[0])
                except Exception:
                    samples[a].append(None)
            time.sleep(0.02)
        return samples

    def verify_while_playing(self, seconds=6.0, max_candidates=500):
        """Ocarina held up and notes being played: score how steadily each
        candidate stays at its 'up' value."""
        addrs = self.addresses(limit=max_candidates)
        samples = self._poll(addrs, seconds)
        self.steady = {}
        for a, _, up in addrs:
            vals = samples[a]
            self.steady[a] = sum(v == up for v in vals) / len(vals) if vals else 0.0
        good = sum(1 for s in self.steady.values() if s >= 0.98)
        self.progress(f"{good} candidate(s) stayed steady while playing")

    def verify_down(self, seconds=2.0):
        """Ocarina put away: drop candidates that don't sit at their down value."""
        addrs = [x for x in self.addresses() if x[0] in self.steady] if self.steady else self.addresses(limit=500)
        samples = self._poll(addrs, seconds)
        ok = {a for a, down, _ in addrs if samples[a] and all(v == down for v in samples[a])}
        for base in list(self.candidates):
            offs, d, u = self.candidates[base]
            keep = np.array([(base + int(o)) in ok for o in offs], dtype=bool)
            if keep.any():
                self.candidates[base] = (offs[keep], d[keep], u[keep])
            else:
                del self.candidates[base]
        self.progress(f"{self.count()} candidate(s) return to 'put away' correctly")

    def best(self):
        """Best (address, up_value, down_value, steadiness), preferring flags
        that stayed steady during play."""
        addrs = self.addresses()
        if not addrs:
            return None
        ranked = sorted(addrs, key=lambda x: (-self.steady.get(x[0], 0.0), x[0]))
        a, down, up = ranked[0]
        return {"address": a, "up_value": up, "down_value": down, "steadiness": self.steady.get(a, 0.0)}

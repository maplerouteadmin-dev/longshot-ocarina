"""Turns a stream of pitch readings into note press/release decisions.

Three things keep it both fast and free of stray presses:

* Steadiness, not just "same note": a note is only confirmed once the pitch
  has stayed within a narrow band for STABLE_SECONDS. When you start blowing,
  the pitch sweeps up through other notes -- that sweep never holds steady, so
  it never confirms anything, while a clean note confirms in ~30ms.
* Attack gating: readings taken while the volume is still climbing restart the
  steadiness timer, so the breath attack itself can't confirm a note.
* Sticky held notes: once a note is held it keeps counting slightly past its
  boundary, so a wobble mid-breath doesn't flip to the neighbouring note.

Each note's acceptance window is half the distance to its nearest calibrated
neighbour (capped), so adding notes automatically tightens the windows instead
of letting them overlap. There is no octave folding: D5 and D6 are both real
notes an octave apart, and folding would make them indistinguishable.
"""
from collections import deque
from dataclasses import dataclass, field

import pitch


@dataclass
class MatchParams:
    noise_floor: float = 0.002     # measured background RMS
    level_margin: float = 3.0      # a note must be this many times louder than the floor
    min_level: float = 0.004       # absolute floor regardless of measurement
    min_conf: float = 0.80         # YIN confidence needed to count as a tone
    max_window_cents: float = 120  # widest a note's acceptance window can be
    guard_cents: float = 8         # dead zone between neighbouring windows
    stable_seconds: float = 0.030  # how long the pitch must hold steady to confirm
    stable_spread_cents: float = 35  # how steady "steady" is
    attack_ratio: float = 1.35     # volume rising faster than this = still attacking
    attack_lookback: float = 0.015
    release_seconds: float = 0.060  # silence/off-note time before releasing a held note
    sticky_cents: float = 18       # extra tolerance for the note currently held


@dataclass
class NoteRef:
    key: str
    cents: float
    window: float = 0.0


@dataclass
class Decision:
    """What happened on one reading -- for the UI and for the engine."""
    t: float
    freq: float | None
    level: float
    voiced: bool
    nearest: str | None = None
    offset_cents: float | None = None
    candidate: str | None = None
    held: str | None = None
    events: list = field(default_factory=list)  # [("press", key) | ("release", key)]


class NoteMatcher:
    def __init__(self, notes: dict, params: MatchParams | None = None):
        """notes: {button_key: mean_frequency_hz}"""
        self.params = params or MatchParams()
        self.set_notes(notes)
        self.held = None
        self._run_key = None
        self._run_start = 0.0
        self._run_lo = self._run_hi = 0.0
        self._last_held_seen = 0.0
        self._levels = deque()

    def set_notes(self, notes: dict):
        refs = sorted((NoteRef(k, pitch.cents(f)) for k, f in notes.items() if f), key=lambda r: r.cents)
        p = self.params
        for i, r in enumerate(refs):
            gaps = []
            if i > 0:
                gaps.append(r.cents - refs[i - 1].cents)
            if i + 1 < len(refs):
                gaps.append(refs[i + 1].cents - r.cents)
            half = (min(gaps) / 2 - p.guard_cents) if gaps else p.max_window_cents
            r.window = max(10.0, min(p.max_window_cents, half))
        self.refs = refs

    def gate_level(self) -> float:
        p = self.params
        return max(p.min_level, p.noise_floor * p.level_margin)

    def classify(self, freq):
        """(nearest_key, offset_cents, inside_window) for a frequency."""
        if not freq or not self.refs:
            return None, None, False
        c = pitch.cents(freq)
        best = min(self.refs, key=lambda r: abs(c - r.cents))
        off = c - best.cents
        window = best.window + (self.params.sticky_cents if best.key == self.held else 0)
        if self.held and best.key != self.held:
            # hysteresis: stay on the held note if we're still close to it
            h = next(r for r in self.refs if r.key == self.held)
            if abs(c - h.cents) <= h.window + self.params.sticky_cents:
                return h.key, c - h.cents, True
        return best.key, off, abs(off) <= window

    def _attacking(self, t, level):
        p = self.params
        self._levels.append((t, level))
        while self._levels and self._levels[0][0] < t - 0.1:
            self._levels.popleft()
        past = [lv for (ts, lv) in self._levels if ts <= t - p.attack_lookback]
        return bool(past) and level > past[-1] * p.attack_ratio

    def update(self, reading, allow_new: bool = True) -> Decision:
        p = self.params
        t, freq, level = reading.t, reading.freq, reading.level
        voiced = bool(freq) and reading.conf >= p.min_conf and level >= self.gate_level()
        d = Decision(t, freq, level, voiced, held=self.held)
        key, off, inside = self.classify(freq) if voiced else (None, None, False)
        d.nearest, d.offset_cents = key, off
        match = key if (voiced and inside) else None
        attacking = voiced and self._attacking(t, level)

        if match is not None and self.held == match:
            self._last_held_seen = t

        # steadiness run
        c = pitch.cents(freq) if voiced else None
        if match is None:
            self._run_key = None
        elif match != self._run_key or attacking:
            self._run_key, self._run_start, self._run_lo, self._run_hi = match, t, c, c
        else:
            self._run_lo, self._run_hi = min(self._run_lo, c), max(self._run_hi, c)
            if self._run_hi - self._run_lo > p.stable_spread_cents:
                self._run_start, self._run_lo, self._run_hi = t, c, c
        d.candidate = self._run_key

        confirmed = (
            self._run_key is not None
            and self._run_key != self.held
            and t - self._run_start >= p.stable_seconds
        )
        if confirmed and (allow_new or self.held is not None):
            if self.held is not None:
                d.events.append(("release", self.held))
            self.held = self._run_key
            self._last_held_seen = t
            d.events.append(("press", self.held))
        elif self.held is not None and t - self._last_held_seen >= p.release_seconds:
            d.events.append(("release", self.held))
            self.held = None

        d.held = self.held
        return d

    def reset(self):
        events = [("release", self.held)] if self.held else []
        self.held = None
        self._run_key = None
        self._levels.clear()
        return events

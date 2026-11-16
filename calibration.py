"""Calibration helpers shared by the app and the command-line calibrate.py.

Each note is recorded as several takes; we keep the median pitch of the steady
part of each take, then the median across takes. "Spread" is how much the
note wandered (within and across takes) -- if two notes' spreads overlap, the
matcher can't reliably tell them apart, and check_notes() says so.
"""
import time

import numpy as np

import pitch
from matcher import MatchParams


def record_take(analyzer, params: MatchParams, seconds=2.0, settle=0.25, abort=None,
                wait_for_note=None, on_start=None):
    """Collect one take from a running Analyzer.

    wait_for_note: if set, wait up to this many seconds for the note to begin
    and start the `seconds`-long recording from there, so the player can take
    their time getting their fingers on after clicking Record. on_start() is
    called when the note is heard.

    Returns {"hz", "spread_cents", "n"} or None if no steady tone was heard.
    `settle` skips the start of the note (the breath attack) once sound begins.
    """
    gate = max(params.min_level, params.noise_floor * params.level_margin)

    def is_voiced(r):
        return r.freq and r.conf >= params.min_conf and r.level >= gate

    analyzer.drain()
    voiced = []
    if wait_for_note:
        deadline = time.monotonic() + wait_for_note
        streak = []
        while not voiced:
            if (abort and abort()) or time.monotonic() > deadline:
                return None
            for r in analyzer.drain():
                streak = streak + [r] if is_voiced(r) else []
                if streak and streak[-1].t - streak[0].t >= 0.08:   # sustained, not a click
                    voiced = [(x.t, x.freq) for x in streak]
                    break
            time.sleep(0.02)
        if on_start:
            on_start()
    end = time.monotonic() + seconds
    while time.monotonic() < end:
        if abort and abort():
            return None
        for r in analyzer.drain():
            if is_voiced(r):
                voiced.append((r.t, r.freq))
        time.sleep(0.02)
    if not voiced:
        return None
    t0 = voiced[0][0]
    steady = [f for (t, f) in voiced if t - t0 >= settle] or [f for (_, f) in voiced]
    if len(steady) < 10:
        return None
    c = np.array([pitch.cents(f) for f in steady])
    med = float(np.median(c))
    # drop readings far from the median (stray octave/noise blips)
    c = c[np.abs(c - med) < 100]
    if len(c) < 10:
        return None
    q1, q3 = np.percentile(c, [10, 90])
    return {"hz": float(440.0 * 2 ** (np.median(c) / 1200)), "spread_cents": float(q3 - q1), "n": int(len(c))}


def combine(takes):
    """Merge takes into one note entry: median pitch, spread covering all takes."""
    takes = [t for t in takes if t]
    if not takes:
        return None
    cs = np.array([pitch.cents(t["hz"]) for t in takes])
    center = float(np.median(cs))
    within = max(t["spread_cents"] for t in takes)
    across = float(cs.max() - cs.min())
    return {
        "hz": float(440.0 * 2 ** (center / 1200)),
        "spread_cents": float(max(within, across)),
        "takes": [t["hz"] for t in takes],
    }


def check_notes(notes: dict):
    """Warnings for notes too close to separate. notes: {button: entry}."""
    items = sorted(((pitch.cents(e["hz"]), b, e) for b, e in notes.items() if e.get("hz")))
    warnings = []
    for (c1, b1, e1), (c2, b2, e2) in zip(items, items[1:]):
        gap = c2 - c1
        need = (e1.get("spread_cents", 0) + e2.get("spread_cents", 0)) / 2
        if gap < 60:
            warnings.append(f"{b1} and {b2} are only {gap:.0f} cents apart -- re-record one; they may be the same fingering.")
        elif need > gap * 0.8:
            warnings.append(f"{b1} and {b2} wander ({need:.0f} cents) almost as much as they're apart ({gap:.0f}) -- "
                            "try steadier breath for those two.")
    return warnings

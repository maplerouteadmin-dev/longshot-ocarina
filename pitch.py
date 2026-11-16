"""YIN pitch detection.

Replaces plain autocorrelation peak-picking, which grabbed the *strongest*
peak and so regularly reported half or double the real pitch (the 490Hz /
2000Hz readings we saw). YIN normalises the difference function and takes the
*first* dip below a threshold, which is the true period for a near-sinusoidal
instrument like an ocarina. It also stays accurate on ~20ms windows, which is
what lets the sliding analyser in audio.py react quickly.
"""
import numpy as np

DEFAULT_FMIN = 200.0   # Hz -- below the lowest note of a 12-hole alto C (A4 = 440Hz)
DEFAULT_FMAX = 2500.0  # Hz -- above the highest (F6 ~ 1397Hz), with headroom


def window_size_for(sample_rate: int, fmin: float = DEFAULT_FMIN) -> int:
    """Smallest power of two holding two periods of fmin (YIN needs a lag range
    plus an integration window of the same size)."""
    need = int(2 * sample_rate / fmin) + 1
    n = 256
    while n < need:
        n *= 2
    return n


def detect_pitch(frame: np.ndarray, sample_rate: int, fmin: float = DEFAULT_FMIN,
                 fmax: float = DEFAULT_FMAX, threshold: float = 0.15):
    """Return (frequency_hz, confidence 0..1) for one mono frame, or (None, 0.0).

    Loudness gating is done by the caller (it knows the measured noise floor);
    this only decides whether there is a clear periodic tone.
    """
    x = np.asarray(frame, dtype=np.float64)
    x = x - x.mean()
    n = len(x)
    tau_min = max(2, int(sample_rate / fmax))
    tau_max = min(int(sample_rate / fmin), n // 2)
    if tau_max <= tau_min + 2:
        return None, 0.0
    w = n - tau_max

    # difference function d(tau) = sum_{j<w} (x_j - x_{j+tau})^2, via FFT
    cum = np.concatenate(([0.0], np.cumsum(x * x)))
    energy = cum[w:w + tau_max + 1] - cum[:tau_max + 1]
    size = 1
    while size < n + w:
        size *= 2
    corr = np.fft.irfft(np.fft.rfft(x, size) * np.conj(np.fft.rfft(x[:w], size)), size)[:tau_max + 1]
    d = energy[0] + energy - 2.0 * corr
    d[0] = 0.0

    # cumulative mean normalised difference
    cmnd = np.ones_like(d)
    running = np.cumsum(d[1:])
    taus = np.arange(1, tau_max + 1)
    with np.errstate(divide="ignore", invalid="ignore"):
        cmnd[1:] = np.where(running > 0, d[1:] * taus / running, 1.0)

    # first dip below threshold, then walk down to that dip's local minimum
    region = cmnd[tau_min:tau_max]
    below = np.nonzero(region < threshold)[0]
    if len(below):
        tau = tau_min + int(below[0])
        while tau + 1 < tau_max and cmnd[tau + 1] < cmnd[tau]:
            tau += 1
    else:
        tau = tau_min + int(np.argmin(region))
        if cmnd[tau] > 0.35:
            return None, float(1.0 - cmnd[tau])

    # parabolic interpolation for sub-sample period
    if 1 <= tau < tau_max:
        a, b, c = cmnd[tau - 1], cmnd[tau], cmnd[tau + 1]
        denom = a - 2 * b + c
        shift = 0.5 * (a - c) / denom if abs(denom) > 1e-12 else 0.0
    else:
        shift = 0.0
    period = tau + shift
    if period <= 0:
        return None, 0.0
    return float(sample_rate / period), float(max(0.0, 1.0 - cmnd[tau]))


def rms(frame: np.ndarray) -> float:
    x = np.asarray(frame, dtype=np.float64)
    return float(np.sqrt(np.mean((x - x.mean()) ** 2)))


def cents(freq: float, ref: float = 440.0) -> float:
    return 1200.0 * np.log2(freq / ref)

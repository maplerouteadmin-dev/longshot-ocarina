"""Shared pitch-detection helpers: autocorrelation-based fundamental frequency estimate."""
import numpy as np
import sounddevice as sd

FMIN = 80.0   # Hz, lowest note we'll ever expect from a physical ocarina
FMAX = 2000.0  # Hz, highest

# Pin the mic input to the C922 webcam for this mod specifically, without
# touching the user's Windows system-wide default recording device (which
# stays whatever they have it set to for everything else). The webcam's
# WASAPI device doesn't support 44100Hz (only 48000Hz), so SAMPLE_RATE is
# set dynamically to whatever the selected device actually reports instead
# of a hardcoded value.
def _set_default_input():
    try:
        for i, d in enumerate(sd.query_devices()):
            if "C922" in d["name"] and d["max_input_channels"] > 0 and d["hostapi"] == 2:  # WASAPI
                sd.default.device = (i, sd.default.device[1] if isinstance(sd.default.device, (list, tuple)) else None)
                return i, int(d["default_samplerate"])
    except Exception:
        pass
    return None, 44100


_C922_DEVICE_INDEX, SAMPLE_RATE = _set_default_input()

def detect_pitch(samples: np.ndarray, sample_rate: int = SAMPLE_RATE):
    """Return (frequency_hz, confidence) for a mono float32 buffer, or (None, 0.0) if too quiet/noisy."""
    samples = samples.astype(np.float64)
    samples = samples - np.mean(samples)

    rms = np.sqrt(np.mean(samples ** 2))
    if rms < 0.004:
        return None, 0.0

    # window to reduce edge artifacts
    window = np.hanning(len(samples))
    windowed = samples * window

    # autocorrelation via FFT (fast, equivalent to direct autocorrelation)
    n = len(windowed)
    fft = np.fft.rfft(windowed, n=2 * n)
    acf = np.fft.irfft(fft * np.conj(fft))[:n]

    min_lag = int(sample_rate / FMAX)
    max_lag = int(sample_rate / FMIN)
    max_lag = min(max_lag, n - 1)
    if max_lag <= min_lag:
        return None, 0.0

    segment = acf[min_lag:max_lag]
    if len(segment) == 0:
        return None, 0.0

    peak_idx = int(np.argmax(segment))
    peak_lag = peak_idx + min_lag

    # confidence: peak height relative to zero-lag energy
    confidence = segment[peak_idx] / (acf[0] + 1e-9)
    if confidence < 0.25:
        return None, float(confidence)

    # parabolic interpolation around the peak for sub-sample precision
    if 0 < peak_idx < len(segment) - 1:
        y0, y1, y2 = segment[peak_idx - 1], segment[peak_idx], segment[peak_idx + 1]
        denom = (y0 - 2 * y1 + y2)
        if abs(denom) > 1e-9:
            shift = 0.5 * (y0 - y2) / denom
            peak_lag = peak_lag + shift

    if peak_lag <= 0:
        return None, 0.0

    freq = sample_rate / peak_lag
    return float(freq), float(confidence)

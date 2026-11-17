"""Listens to what the PC is sending to the speakers/TV (WASAPI loopback) so
the translator can ignore game sounds the mic picks up -- the music, and
especially Link playing your note back right after the game registers it.

It keeps the last ~0.5s of the game audio's spectrum. present(freq, t) answers
"was the game playing this pitch in the last LOOKBACK seconds?" -- checked
against the whole spectrum, so it catches notes inside chords and music, not
just a single dominant pitch. LOOKBACK covers the delay between the PC sending
audio and the mic hearing it back from the TV (HDMI + room).
"""
import threading
import time
import warnings
from collections import deque

import numpy as np

FRAME = 512          # samples per loopback read (~10.7ms at 48kHz)
FFT_WINDOW = 4096    # ~85ms -> ~12Hz bins, fine enough for 600-1400Hz notes
SAMPLE_RATE = 48000
HISTORY_SECONDS = 0.6


def output_devices():
    """Names of playback devices that can be listened to."""
    try:
        import soundcard as sc
        return [s.name for s in sc.all_speakers()]
    except Exception:
        return []


def default_output():
    try:
        import soundcard as sc
        return sc.default_speaker().name
    except Exception:
        return ""


class GameAudio:
    def __init__(self, device_name="", lookback=0.35, cents_tol=60.0, prominence=6.0, min_level=0.002):
        self.device_name = device_name or default_output()
        self.lookback = lookback
        self.cents_tol = cents_tol
        self.prominence = prominence
        self.min_level = min_level
        self.frames = deque()     # (t, rms, magnitude spectrum)
        self._lock = threading.Lock()
        self._stop = threading.Event()
        self._thread = None
        self.error = None
        self.freqs = np.fft.rfftfreq(FFT_WINDOW, 1 / SAMPLE_RATE)
        self._band = (self.freqs >= 150) & (self.freqs <= 3000)
        self._win = np.hanning(FFT_WINDOW).astype(np.float32)

    def start(self):
        self._stop.clear()
        self._thread = threading.Thread(target=self._run, daemon=True)
        self._thread.start()

    def stop(self):
        self._stop.set()
        if self._thread:
            self._thread.join(timeout=1)

    def _run(self):
        try:
            import sys
            if sys.platform == "win32":
                import ctypes
                ctypes.windll.ole32.CoInitializeEx(None, 0)  # soundcard only inits COM on the importing thread
            import soundcard as sc
            mic = sc.get_microphone(id=str(self.device_name), include_loopback=True)
        except Exception as e:
            self.error = f"Can't listen to '{self.device_name}': {e}"
            return
        buf = np.zeros(FFT_WINDOW, dtype=np.float32)
        with warnings.catch_warnings():
            warnings.simplefilter("ignore")   # soundcard emits numpy deprecation/discontinuity warnings
            try:
                with mic.recorder(samplerate=SAMPLE_RATE, channels=1, blocksize=FRAME) as rec:
                    while not self._stop.is_set():
                        data = rec.record(numframes=FRAME)[:, 0].astype(np.float32)
                        buf = np.concatenate((buf[len(data):], data))
                        rms = float(np.sqrt(np.mean(buf[-2048:] ** 2)))
                        spec = np.abs(np.fft.rfft(buf * self._win)).astype(np.float32)
                        band = spec[self._band]
                        med, bmax = float(np.median(band)), float(band.max())
                        now = time.monotonic()
                        with self._lock:
                            self.frames.append((now, rms, spec, med, bmax))
                            while self.frames and self.frames[0][0] < now - HISTORY_SECONDS:
                                self.frames.popleft()
            except Exception as e:
                self.error = f"Game audio capture stopped: {e}"

    def level(self):
        with self._lock:
            return self.frames[-1][1] if self.frames else 0.0

    def annotate(self, readings, gate_level):
        """Flag mic readings whose pitch the game is playing. Only loud-enough
        voiced readings are checked (the rest can't start a note anyway)."""
        for r in readings:
            if r.freq and r.level >= gate_level and self.present(r.freq, r.t):
                r.echo = True
        return readings

    def present(self, freq, t):
        """Was the game playing (near) this pitch in the last `lookback` seconds?"""
        if not freq:
            return False
        lo = freq * 2 ** (-self.cents_tol / 1200)
        hi = freq * 2 ** (self.cents_tol / 1200)
        sel = (self.freqs >= lo) & (self.freqs <= hi)
        if not sel.any():
            return False
        with self._lock:
            frames = [f for f in self.frames if t - self.lookback <= f[0] <= t + 0.02]
        for _, rms, spec, med, bmax in frames:
            if rms < self.min_level:
                continue
            peak = float(spec[sel].max())
            if peak > self.prominence * med and peak > 0.1 * bmax:
                return True
        return False

    def dominant(self):
        """Loudest pitch in the game audio right now (for the UI)."""
        with self._lock:
            if not self.frames:
                return None
            _, rms, spec, _, _ = self.frames[-1]
        if rms < self.min_level:
            return None
        band = np.where(self._band, spec, 0)
        return float(self.freqs[int(np.argmax(band))])

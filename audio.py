"""Mic selection and the sliding-window pitch analyser.

The analyser keeps a rolling buffer and runs YIN every HOP samples, so it
produces a reading every ~5ms from overlapping ~21ms windows, instead of one
reading per non-overlapping 50ms chunk. More readings per note means notes can
be confirmed faster without trusting any single noisy reading.
"""
import queue
import threading
import time
from dataclasses import dataclass

import numpy as np
import sounddevice as sd

import pitch

HOP = 256  # samples between readings (~5.3ms at 48kHz)


def input_devices():
    """Input devices, WASAPI first (lowest latency on Windows), one entry per
    physical device name. Returns [(index, name, default_samplerate)]."""
    try:
        hostapis = sd.query_hostapis()
        devices = sd.query_devices()
    except Exception:
        return []
    # Windows: prefer WASAPI. Linux/macOS: take whatever PortAudio offers (PulseAudio/PipeWire, ALSA, JACK).
    order = {"Windows WASAPI": 0, "Windows DirectSound": 1, "MME": 2,
             "PulseAudio": 0, "ALSA": 1, "JACK Audio Connection Kit": 2, "Core Audio": 0}
    seen, out = set(), []
    candidates = []
    for i, d in enumerate(devices):
        if d["max_input_channels"] <= 0:
            continue
        api = hostapis[d["hostapi"]]["name"]
        if api not in order:
            if api.startswith("Windows") or api == "MME":
                continue
            order[api] = 5
        candidates.append((order[api], i, d["name"], int(d["default_samplerate"])))
    for _, i, name, sr in sorted(candidates):
        key = name[:28].lower()  # MME truncates names to ~31 chars
        if key in seen:
            continue
        seen.add(key)
        out.append((i, name, sr))
    return out


def find_device(name_hint: str):
    """Best matching input device for a saved name, or the Windows default."""
    devices = input_devices()
    if name_hint:
        for i, name, sr in devices:
            if name_hint.lower() in name.lower() or name.lower() in name_hint.lower():
                return i, name, sr
    try:
        default_in = sd.default.device[0]
        info = sd.query_devices(default_in)
        return default_in, info["name"], int(info["default_samplerate"])
    except Exception:
        return devices[0] if devices else (None, "", 48000)


@dataclass
class Reading:
    t: float          # time.monotonic() of the reading
    freq: float       # Hz, or None when no clear tone
    conf: float       # YIN confidence 0..1
    level: float      # RMS of the window
    echo: bool = False  # the game was playing this pitch too (set by echo.GameAudio)


class Analyzer:
    """Opens the mic once and emits a Reading every HOP samples on a queue.

    Callback-based: PortAudio hands us audio on its own schedule. (A manual
    blocking InputStream.read() at a fixed blocksize gave halved pitches on the
    WASAPI webcam, and calling sd.rec() per chunk re-opened the device every
    time and was far too slow.)
    """

    def __init__(self, device_index, sample_rate, fmin=pitch.DEFAULT_FMIN, fmax=pitch.DEFAULT_FMAX):
        self.device_index = device_index
        self.sample_rate = int(sample_rate)
        self.fmin, self.fmax = fmin, fmax
        self.window = pitch.window_size_for(self.sample_rate, fmin) * 2
        self.readings = queue.Queue(maxsize=2000)
        self._raw = queue.Queue()
        self._stream = None
        self._thread = None
        self._stop = threading.Event()

    def _callback(self, indata, frames, time_info, status):
        self._raw.put(indata[:, 0].copy())

    def start(self):
        self._stream = sd.InputStream(
            device=self.device_index, samplerate=self.sample_rate, channels=1,
            dtype="float32", blocksize=HOP, callback=self._callback,
        )
        self._stream.start()
        self._stop.clear()
        self._thread = threading.Thread(target=self._run, daemon=True)
        self._thread.start()

    def _run(self):
        buf = np.zeros(self.window, dtype=np.float32)
        pending = np.zeros(0, dtype=np.float32)
        while not self._stop.is_set():
            try:
                block = self._raw.get(timeout=0.2)
            except queue.Empty:
                continue
            pending = np.concatenate((pending, block))
            while len(pending) >= HOP:
                hop, pending = pending[:HOP], pending[HOP:]
                buf = np.concatenate((buf[HOP:], hop))
                level = pitch.rms(buf)
                freq, conf = pitch.detect_pitch(buf, self.sample_rate, self.fmin, self.fmax)
                reading = Reading(time.monotonic(), freq, conf, level)
                try:
                    self.readings.put_nowait(reading)
                except queue.Full:
                    try:
                        self.readings.get_nowait()
                    except queue.Empty:
                        pass
                    self.readings.put_nowait(reading)

    def drain(self):
        out = []
        while True:
            try:
                out.append(self.readings.get_nowait())
            except queue.Empty:
                return out

    def stop(self):
        self._stop.set()
        if self._stream is not None:
            self._stream.stop()
            self._stream.close()
            self._stream = None
        if self._thread is not None:
            self._thread.join(timeout=1)
            self._thread = None


def measure_noise_floor(analyzer: Analyzer, seconds: float = 2.0) -> float:
    """Typical background level while the user stays quiet (90th percentile RMS,
    so a single cough doesn't skew it)."""
    analyzer.drain()
    end = time.monotonic() + seconds
    levels = []
    while time.monotonic() < end:
        levels.extend(r.level for r in analyzer.drain())
        time.sleep(0.05)
    return float(np.percentile(levels, 90)) if levels else 0.002

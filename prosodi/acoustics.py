"""Parselmouth extraction: F0 contour, intensity contour, speech/silence intervals."""

from dataclasses import dataclass

import numpy as np
import parselmouth
from parselmouth.praat import call

from .config import Config


@dataclass
class Acoustics:
    duration_s: float
    pitch_times: np.ndarray      # frame times, seconds
    f0_hz: np.ndarray            # 0.0 where unvoiced
    intensity_times: np.ndarray
    intensity_db: np.ndarray     # may contain non-finite values at the edges
    sounding: list[tuple[float, float]]   # speech intervals
    silences: list[tuple[float, float]]   # internal silences only
    silence_threshold_abs_db: float       # the adaptive threshold actually used

    def voiced_mask(self) -> np.ndarray:
        return self.f0_hz > 0


def extract(wav_path: str, cfg: Config) -> Acoustics:
    snd = parselmouth.Sound(wav_path)
    duration = snd.get_total_duration()

    pitch = snd.to_pitch(pitch_floor=cfg.pitch_floor_hz, pitch_ceiling=cfg.pitch_ceiling_hz)
    f0 = pitch.selected_array["frequency"]
    pitch_times = pitch.xs()

    intensity = snd.to_intensity()
    int_times = intensity.xs()
    int_vals = intensity.values[0]

    # Anchor the silence threshold to the speech mass (p98) with a noise-floor
    # guard, then express it relative to the max as praat expects. See Config.
    finite = int_vals[np.isfinite(int_vals)]
    max_db = float(np.max(finite))
    p98 = float(np.percentile(finite, 98))
    p10 = float(np.percentile(finite, 10))
    thr_abs = max(p98 + cfg.silence_threshold_db, p10 + cfg.noise_floor_margin_db)
    praat_threshold = thr_abs - max_db

    tg = call(
        snd, "To TextGrid (silences)",
        100, 0.0, praat_threshold, cfg.min_pause_s, cfg.min_sounding_s,
        "silent", "sounding",
    )
    n = call(tg, "Get number of intervals", 1)
    sounding: list[tuple[float, float]] = []
    silences: list[tuple[float, float]] = []
    for i in range(1, n + 1):
        label = call(tg, "Get label of interval", 1, i)
        s = call(tg, "Get start time of interval", 1, i)
        e = call(tg, "Get end time of interval", 1, i)
        if label == "sounding":
            sounding.append((s, e))
        elif i not in (1, n):
            # Leading and trailing silence is not a pause anyone dictated.
            silences.append((s, e))

    return Acoustics(
        duration_s=duration,
        pitch_times=pitch_times,
        f0_hz=f0,
        intensity_times=int_times,
        intensity_db=int_vals,
        sounding=sounding,
        silences=silences,
        silence_threshold_abs_db=thr_abs,
    )


def overlap(a: tuple[float, float], b: tuple[float, float]) -> float:
    return max(0.0, min(a[1], b[1]) - max(a[0], b[0]))


def intersect_span(span: tuple[float, float], intervals: list[tuple[float, float]]) -> list[tuple[float, float]]:
    """Pieces of span that fall inside the given intervals."""
    out = []
    for iv in intervals:
        s = max(span[0], iv[0])
        e = min(span[1], iv[1])
        if e > s:
            out.append((s, e))
    return out

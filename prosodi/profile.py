"""Build a speaker profile: corpus-level baselines over a directory of WAVs.

The per-recording baseline (analyze.py) cannot see global agitation: a file
dictated fast end to end has a "normal" local rate. The profile fixes that by
measuring the speaker's own corpus medians once, so any single recording can
be compared against them (analyze --profile).

Only parselmouth runs here (0.02-0.07s per file), never whisper, so a
600-file corpus profiles in about a minute. Rate stats (words/sec, chars/sec
over non-pause time) therefore need an external transcript per file, supplied
as a stem TAB text TSV (--transcripts-tsv). Files without a transcript still
contribute F0 and intensity stats. The source directory is read only, all
output goes to --out.
"""

import math
import sys
import time
from datetime import datetime, timezone
from pathlib import Path

import numpy as np

from .acoustics import extract
from .config import Config


def _st(f_hz: float, ref_hz: float) -> float:
    return 12.0 * math.log2(f_hz / ref_hz)


def _char_count(text: str) -> int:
    return sum(1 for ch in text if ch.isalnum())


def _median(vals: list[float]) -> float | None:
    return round(float(np.median(vals)), 2) if vals else None


def _pct(vals: list[float], q: float) -> float | None:
    return round(float(np.percentile(vals, q)), 2) if vals else None


def build_profile(wav_dir: Path, transcripts: dict[str, str], cfg: Config) -> dict:
    wavs = sorted(wav_dir.glob("*.wav"))
    f0_medians: list[float] = []
    f0_ranges_st: list[float] = []
    int_p50s: list[float] = []
    int_p90s: list[float] = []
    rates_wps: list[float] = []
    rates_cps: list[float] = []
    total_speech_s = 0.0
    total_dur_s = 0.0
    with_transcript = 0
    failed: list[str] = []

    t0 = time.perf_counter()
    for n, wav in enumerate(wavs, 1):
        try:
            ac = extract(str(wav), cfg)
        except Exception as e:  # unreadable or corrupt wav: count it, keep going
            failed.append(wav.name)
            print(f"  skip {wav.name}: {e}", file=sys.stderr)
            continue

        total_dur_s += ac.duration_s
        speech_s = sum(e - s for s, e in ac.sounding)
        total_speech_s += speech_s

        voiced = ac.f0_hz[ac.voiced_mask()]
        if len(voiced) >= 10:
            f0_medians.append(float(np.median(voiced)))
            p5, p95 = np.percentile(voiced, [5, 95])
            f0_ranges_st.append(_st(float(p95), float(p5)))

        mask = np.zeros(len(ac.intensity_times), dtype=bool)
        for s, e in ac.sounding:
            mask |= (ac.intensity_times >= s) & (ac.intensity_times <= e)
        speech_int = ac.intensity_db[mask & np.isfinite(ac.intensity_db)]
        if len(speech_int):
            int_p50s.append(float(np.percentile(speech_int, 50)))
            int_p90s.append(float(np.percentile(speech_int, 90)))

        text = transcripts.get(wav.stem)
        if text and speech_s > 0.5:
            with_transcript += 1
            rates_wps.append(len(text.split()) / speech_s)
            rates_cps.append(_char_count(text) / speech_s)

        if n % 50 == 0 or n == len(wavs):
            print(f"  {n}/{len(wavs)} files, {time.perf_counter() - t0:.0f}s",
                  file=sys.stderr)

    return {
        "tool": "prosodi 0.1.0",
        "kind": "speaker-profile",
        "built": datetime.now(timezone.utc).strftime("%Y-%m-%d"),
        "source_dir": str(wav_dir),
        "files": {
            "total": len(wavs),
            "ok": len(wavs) - len(failed),
            "failed": len(failed),
            "failed_names": failed,
            "with_transcript": with_transcript,
        },
        "audio_total_s": round(total_dur_s, 1),
        "speech_total_s": round(total_speech_s, 1),
        # Medians of per-file stats, every file weighted equally.
        "f0_median_hz": _median(f0_medians),
        "f0_median_hz_p25": _pct(f0_medians, 25),
        "f0_median_hz_p75": _pct(f0_medians, 75),
        "f0_range_p5_p95_st_median": _median(f0_ranges_st),
        "speech_rate_wps_median": _median(rates_wps),
        "speech_rate_wps_p25": _pct(rates_wps, 25),
        "speech_rate_wps_p75": _pct(rates_wps, 75),
        "chars_per_s_median": _median(rates_cps),
        "chars_per_s_p25": _pct(rates_cps, 25),
        "chars_per_s_p75": _pct(rates_cps, 75),
        "intensity_speech_p50_db_median": _median(int_p50s),
        "intensity_speech_p90_db_median": _median(int_p90s),
    }

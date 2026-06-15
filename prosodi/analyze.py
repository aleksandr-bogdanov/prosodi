"""Fuse whisper word timestamps with parselmouth acoustics into one record.

The record (returned as a plain dict, dumped as <name>.prosodi.json) is the
machine-readable layer. Everything the text annotation renders is derivable
from it.

The one critical correction (see TOOLING.md): whisper stretches a word's span
across adjacent pauses and silently drops disfluencies. So every word span is
first intersected with parselmouth's speech (sounding) intervals. Durations,
F0 and intensity are computed over that intersection only.
"""

import math

import numpy as np

from .acoustics import Acoustics, extract, intersect_span, overlap
from .config import Config
from .transcribe import transcribe_words


def _st(f_hz: float, ref_hz: float) -> float:
    return 12.0 * math.log2(f_hz / ref_hz)


def _char_count(text: str) -> int:
    # Letters and digits only. Works for Cyrillic via isalnum.
    return sum(1 for ch in text if ch.isalnum())


def _frames_in(times: np.ndarray, intervals: list[tuple[float, float]]) -> np.ndarray:
    mask = np.zeros(len(times), dtype=bool)
    for s, e in intervals:
        mask |= (times >= s) & (times <= e)
    return mask


def analyze_file(wav_path: str, cfg: Config, reference_transcript: str | None = None,
                 profile: dict | None = None) -> dict:
    ac = extract(wav_path, cfg)
    tr = transcribe_words(wav_path, cfg)
    return build_record(wav_path, ac, tr, cfg, reference_transcript, profile)


def build_record(wav_path: str, ac: Acoustics, tr: dict, cfg: Config,
                 reference_transcript: str | None, profile: dict | None = None) -> dict:
    words_in = tr["words"]
    voiced = ac.voiced_mask()

    # --- utterance F0 baseline (over the whole file's voiced frames) ---
    voiced_f0 = ac.f0_hz[voiced]
    voiced_times = ac.pitch_times[voiced]
    if len(voiced_f0) >= cfg.min_voiced_frames:
        utt_f0_median = float(np.median(voiced_f0))
        p5, p95 = np.percentile(voiced_f0, [5, 95])
        utt_f0_range_st = _st(float(p95), float(p5))
        # Declination trend: F0 drifts down over an utterance, so "above the
        # median" overcounts early words. Emphasis is measured against this
        # linear trend (in semitones vs the median) instead of the flat median.
        if len(voiced_f0) >= 10:
            st_all = 12.0 * np.log2(voiced_f0 / utt_f0_median)
            decl = np.polyfit(voiced_times, st_all, 1)
        else:
            decl = np.array([0.0, 0.0])
    else:
        # Whispered or toneless audio. Everything F0-based degrades to null.
        utt_f0_median = None
        utt_f0_range_st = None
        decl = None

    # --- utterance intensity baseline (speech frames only) ---
    int_mask = _frames_in(ac.intensity_times, ac.sounding) & np.isfinite(ac.intensity_db)
    speech_int = ac.intensity_db[int_mask]
    utt_int_mean = float(np.mean(speech_int)) if len(speech_int) else None
    utt_int_max = float(np.max(speech_int)) if len(speech_int) else None

    # --- per-word: trim spans to speech, then measure ---
    words: list[dict] = []
    for w in words_in:
        span = (w["start"], w["end"])
        raw_dur = max(0.0, span[1] - span[0])
        all_pieces = intersect_span(span, ac.sounding)
        in_speech = bool(all_pieces)
        if not all_pieces:
            # Whole span sits below the silence threshold (very quiet word or a
            # whisper hallucination). Keep the raw span and flag it.
            all_pieces = [span]
        # A spoken word cannot straddle a real pause. When the span covers
        # several speech runs, whisper has absorbed a neighbor (often a dropped
        # disfluency), so the word is assigned to the run it overlaps most and
        # measured there only.
        pieces = [max(all_pieces, key=lambda p: p[1] - p[0])]
        eff_dur = pieces[0][1] - pieces[0][0]
        pause_inside = max(0.0, raw_dur - sum(e - s for s, e in all_pieces)) if in_speech else 0.0
        absorbed = sum(e - s for s, e in all_pieces) - eff_dur

        pmask = _frames_in(ac.pitch_times, pieces) & voiced
        wf0 = ac.f0_hz[pmask]
        wtimes = ac.pitch_times[pmask]
        if len(wf0) >= cfg.min_voiced_frames and utt_f0_median:
            f0_median = float(np.median(wf0))
            st_vals = 12.0 * np.log2(wf0 / utt_f0_median)
            # Slope: linear fit in st/s over the word's voiced frames.
            slope = float(np.polyfit(wtimes, st_vals, 1)[0]) if len(wf0) >= 3 else None
            # Movement: last voiced third vs first voiced third, in semitones.
            k = max(1, len(wf0) // 3)
            delta = float(np.mean(st_vals[-k:]) - np.mean(st_vals[:k]))
            if delta >= cfg.movement_st:
                movement = "rise"
            elif delta <= -cfg.movement_st:
                movement = "fall"
            else:
                movement = "flat"
        else:
            f0_median, slope, delta, movement = None, None, None, None

        imask = _frames_in(ac.intensity_times, pieces) & np.isfinite(ac.intensity_db)
        w_int = ac.intensity_db[imask]
        int_mean = float(np.mean(w_int)) if len(w_int) else None

        words.append({
            "text": w["text"],
            "start": round(span[0], 3),
            "end": round(span[1], 3),
            "duration_s": round(raw_dur, 3),
            "effective_duration_s": round(eff_dur, 3),
            "pause_inside_s": round(pause_inside, 3),
            "in_speech": in_speech,
            "probability": round(w["probability"], 3),
            "f0_median_hz": round(f0_median, 1) if f0_median else None,
            "f0_slope_st_per_s": round(slope, 2) if slope is not None else None,
            "f0_delta_st": round(delta, 2) if delta is not None else None,
            "f0_movement": movement,
            "intensity_mean_db": round(int_mean, 1) if int_mean is not None else None,
            "speech_pieces": [(round(s, 3), round(e, 3)) for s, e in pieces],
            "absorbed_speech_s": round(absorbed, 3),
        })

    # --- expected duration from the utterance's own chars-per-second rate ---
    total_chars = sum(_char_count(w["text"]) + cfg.word_overhead_chars for w in words)
    total_eff = sum(w["effective_duration_s"] for w in words)
    chars_per_s = total_chars / total_eff if total_eff > 0 else None
    for w in words:
        if chars_per_s:
            expected = max(cfg.min_expected_s,
                           (_char_count(w["text"]) + cfg.word_overhead_chars) / chars_per_s)
            w["expected_duration_s"] = round(expected, 3)
            w["stretch_factor"] = round(w["effective_duration_s"] / expected, 2)
        else:
            w["expected_duration_s"] = None
            w["stretch_factor"] = None

    # --- emphasis intensity baseline: median of per-word means, so "+5 dB" is
    # relative to a typical word, the frame-level mean sits lower because it
    # includes word edges and breaths ---
    word_ints = [w["intensity_mean_db"] for w in words if w["intensity_mean_db"] is not None]
    utt_int_word_median = float(np.median(word_ints)) if word_ints else None

    # --- pauses: gaps between speech-trimmed word edges, validated by silences ---
    pauses: list[dict] = []
    for i in range(len(words) - 1):
        gap_start = words[i]["speech_pieces"][-1][1]
        gap_end = words[i + 1]["speech_pieces"][0][0]
        gap = gap_end - gap_start
        if gap < cfg.min_pause_s:
            continue
        sil = sum(overlap((gap_start, gap_end), s) for s in ac.silences)
        pauses.append({
            "after_word": i,
            "start": round(gap_start, 3),
            "end": round(gap_end, 3),
            "gap_s": round(gap, 3),
            "silence_overlap_s": round(sil, 3),
            "rendered": sil >= cfg.render_min_pause_s,
        })

    # --- annotations: emphasis, stretch, boundary tones, tempo ---
    pause_after = {p["after_word"]: p for p in pauses if p["rendered"]}
    for i, w in enumerate(words):
        ann = {"emphasized": False, "stretched": None, "boundary": None, "tempo": None}
        if w["probability"] >= cfg.min_word_prob:
            if w["f0_median_hz"] and utt_f0_median:
                # Semitones above the utterance's declination trend at this
                # word's position, so early-utterance high pitch is not counted
                # as emphasis.
                t_mid = (w["speech_pieces"][0][0] + w["speech_pieces"][-1][1]) / 2.0
                trend = float(decl[0] * t_mid + decl[1]) if decl is not None else 0.0
                f0_above = _st(w["f0_median_hz"], utt_f0_median) - trend
            else:
                f0_above = None
            int_above = (w["intensity_mean_db"] - utt_int_word_median
                         if w["intensity_mean_db"] is not None and utt_int_word_median is not None
                         else None)
            f0_route = (f0_above is not None and f0_above >= cfg.emphasis_f0_st
                        and int_above is not None and int_above >= cfg.emphasis_f0_min_db)
            int_route = int_above is not None and int_above >= cfg.emphasis_db
            ann["emphasized"] = bool(f0_route or int_route)
            w["f0_above_baseline_st"] = round(f0_above, 2) if f0_above is not None else None
            w["intensity_above_baseline_db"] = round(int_above, 1) if int_above is not None else None
            # The character and absolute-duration floors gate the rendered
            # marker only, stretch_factor stays in the JSON for every word.
            if (w["stretch_factor"] is not None
                    and w["stretch_factor"] >= cfg.stretch_threshold
                    and w["effective_duration_s"] >= cfg.min_stretched_s
                    and w["effective_duration_s"] >= cfg.stretch_min_abs_s
                    and _char_count(w["text"]) >= cfg.stretch_min_chars):
                ann["stretched"] = w["stretch_factor"]
            # Boundary tone only at clause ends: before a rendered pause or at
            # the end of the utterance.
            if (i in pause_after or i == len(words) - 1) and w["f0_movement"] in ("rise", "fall"):
                ann["boundary"] = w["f0_movement"]
        else:
            w["f0_above_baseline_st"] = None
            w["intensity_above_baseline_db"] = None
        w["annotation"] = ann

    _cap_emphasis(words, cfg)
    _mark_tempo(words, chars_per_s, cfg)
    tempo_spans = _tempo_spans(words)

    # --- utterance stats ---
    total_sounding = sum(e - s for s, e in ac.sounding)
    rendered_pauses = [p for p in pauses if p["rendered"]]
    utterance = {
        "duration_s": round(ac.duration_s, 2),
        "n_words": len(words),
        "f0_median_hz": round(utt_f0_median, 1) if utt_f0_median else None,
        "f0_range_p5_p95_st": round(utt_f0_range_st, 1) if utt_f0_range_st else None,
        "f0_declination_st_per_s": round(float(decl[0]), 2) if decl is not None else None,
        "intensity_mean_db": round(utt_int_mean, 1) if utt_int_mean is not None else None,
        "intensity_max_db": round(utt_int_max, 1) if utt_int_max is not None else None,
        "intensity_word_median_db": (round(utt_int_word_median, 1)
                                     if utt_int_word_median is not None else None),
        "speech_time_s": round(total_sounding, 2),
        "silence_threshold_db": round(ac.silence_threshold_abs_db, 1),
        "speech_rate_wps": round(len(words) / total_sounding, 2) if total_sounding else None,
        "chars_per_s": round(chars_per_s, 2) if chars_per_s else None,
        "pause_count": len(rendered_pauses),
        "pause_total_s": round(sum(p["silence_overlap_s"] for p in rendered_pauses), 2),
    }

    record = {
        "file": wav_path,
        "tool": "prosodi 0.1.0",
        "language": tr["language"],
        "whisper_text": tr["text"],
        "reference_transcript": reference_transcript,
        "config": cfg.to_dict(),
        "utterance": utterance,
        "words": words,
        "pauses": pauses,
        "tempo_spans": tempo_spans,
        "silences": [(round(s, 3), round(e, 3)) for s, e in ac.silences],
    }
    if profile is not None:
        record["global"] = _global_block(utterance, profile, cfg)
    return record


def _cap_emphasis(words: list[dict], cfg: Config) -> None:
    """Per-recording emphasis density cap.

    Every word that passed the absolute thresholds keeps emphasis_candidate
    and its emphasis_salience in the JSON. The rendered star survives only on
    the top emphasis_max_word_pct percent of the recording's words, ranked by
    salience. Files already under the cap are untouched.
    """
    candidates = [w for w in words if w["annotation"]["emphasized"]]
    if not candidates:
        return
    for w in candidates:
        f0_above = w["f0_above_baseline_st"]
        int_above = w["intensity_above_baseline_db"]
        salience = (max(0.0, f0_above) if f0_above is not None else 0.0) \
            + (max(0.0, int_above) if int_above is not None else 0.0)
        w["emphasis_candidate"] = True
        w["emphasis_salience"] = round(salience, 2)
    cap = max(1, round(len(words) * cfg.emphasis_max_word_pct / 100.0))
    if len(candidates) <= cap:
        return
    ranked = sorted(candidates, key=lambda w: w["emphasis_salience"], reverse=True)
    for w in ranked[cap:]:
        w["annotation"]["emphasized"] = False


def _global_block(utterance: dict, profile: dict, cfg: Config) -> dict:
    """Compare this recording's baseline to the speaker's corpus profile."""
    rate = utterance["speech_rate_wps"]
    sp_rate = profile.get("speech_rate_wps_median")
    cps = utterance["chars_per_s"]
    sp_cps = profile.get("chars_per_s_median")
    f0 = utterance["f0_median_hz"]
    sp_f0 = profile.get("f0_median_hz")

    rate_dev_pct = round(100.0 * (rate / sp_rate - 1.0)) if rate and sp_rate else None
    cps_dev_pct = round(100.0 * (cps / sp_cps - 1.0)) if cps and sp_cps else None
    f0_dev_st = round(_st(f0, sp_f0), 2) if f0 and sp_f0 else None

    marker = None
    if rate and sp_rate:
        ratio = rate / sp_rate
        if ratio >= cfg.profile_agitated_rate_ratio:
            marker = f"agitated rate {rate_dev_pct:+d}%"
        elif ratio <= cfg.profile_subdued_rate_ratio:
            marker = f"subdued rate {rate_dev_pct:+d}%"

    return {
        "profile_built": profile.get("built"),
        "profile_files_ok": (profile.get("files") or {}).get("ok"),
        "rate_wps": rate,
        "speaker_rate_wps": sp_rate,
        "rate_dev_pct": rate_dev_pct,
        "chars_per_s": cps,
        "speaker_chars_per_s": sp_cps,
        "cps_dev_pct": cps_dev_pct,
        "f0_median_hz": f0,
        "speaker_f0_median_hz": sp_f0,
        "f0_dev_st": f0_dev_st,
        "marker": marker,
    }


def _mark_tempo(words: list[dict], chars_per_s: float | None, cfg: Config) -> None:
    """Label each word faster/slower from a centered window's local rate."""
    n = len(words)
    if not chars_per_s or n < cfg.tempo_window_words:
        return
    half = cfg.tempo_window_words // 2
    labels: list[str | None] = [None] * n
    for i in range(n):
        lo, hi = max(0, i - half), min(n, i + half + 1)
        win = words[lo:hi]
        dur = sum(w["effective_duration_s"] for w in win)
        chars = sum(_char_count(w["text"]) + cfg.word_overhead_chars for w in win)
        if dur <= 0:
            continue
        ratio = (chars / dur) / chars_per_s
        if ratio >= cfg.tempo_faster_ratio:
            labels[i] = "faster"
        elif ratio <= cfg.tempo_slower_ratio:
            labels[i] = "slower"
        words[i]["tempo_ratio"] = round(ratio, 2)
    # Keep only runs of at least tempo_min_run.
    i = 0
    while i < n:
        if labels[i] is None:
            i += 1
            continue
        j = i
        while j < n and labels[j] == labels[i]:
            j += 1
        if j - i >= cfg.tempo_min_run:
            for k in range(i, j):
                words[k]["annotation"]["tempo"] = labels[i]
        i = j


def _tempo_spans(words: list[dict]) -> list[dict]:
    spans = []
    i, n = 0, len(words)
    while i < n:
        t = words[i]["annotation"]["tempo"]
        if t is None:
            i += 1
            continue
        j = i
        while j < n and words[j]["annotation"]["tempo"] == t:
            j += 1
        spans.append({"kind": t, "first_word": i, "last_word": j - 1,
                      "start": words[i]["start"], "end": words[j - 1]["end"]})
        i = j
    return spans

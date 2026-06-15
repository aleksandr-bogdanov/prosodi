"""Adapters between the web server and the prosodi package.

Everything the server does to audio funnels through here: analyze a recording,
turn the record into UI tokens, clone-render it back, score a render, and build
the real-vs-clone guessing game. The prosodi package is the single source of
truth; this module only shapes its output for the browser and orchestrates the
f5 backend. No prosody logic is re-implemented here.
"""

import json
from copy import deepcopy
from pathlib import Path

import numpy as np
import soundfile as sf

from prosodi.analyze import analyze_file
from prosodi.backends import F5Backend
from prosodi.config import DEFAULT
from prosodi.render import render_txt
from prosodi.verify import align_words, scorecard

REPO_ROOT = Path(__file__).resolve().parents[2]
PROFILE_PATH = REPO_ROOT / "speaker-profile.json"


def _load_profile() -> dict | None:
    if PROFILE_PATH.exists():
        return json.loads(PROFILE_PATH.read_text(encoding="utf-8"))
    return None


def analyze(wav16k: Path, transcript: str | None = None,
            use_profile: bool = True) -> dict:
    """Run the full prosodi analysis on a 16 kHz wav, return the raw record."""
    profile = _load_profile() if use_profile else None
    return analyze_file(str(wav16k), DEFAULT, reference_transcript=transcript,
                        profile=profile)


def transcribe_text(wav16k: Path) -> str:
    """The plain transcript of a clip (for a user-picked reference window)."""
    from prosodi.transcribe import transcribe_words
    return transcribe_words(str(wav16k), DEFAULT)["text"]


def record_to_view(record: dict) -> dict:
    """Shape a record for the browser: header stats, inline marker tokens, notation.

    The token walk mirrors prosodi.render/console exactly (word, then a pause
    token when one is rendered after it) so the web rendering and the CLI agree
    on what shows where.
    """
    u = record["utterance"]
    g = record.get("global")
    pause_after = {p["after_word"]: p for p in record["pauses"] if p["rendered"]}

    tokens: list[dict] = []
    for i, w in enumerate(record["words"]):
        a = w["annotation"]
        tokens.append({
            "type": "word",
            "text": w["text"],
            "emphasized": bool(a["emphasized"]),
            "stretched": a["stretched"],
            "boundary": a["boundary"],
            "tempo": a["tempo"],
            "start": w.get("start"),
            "end": w.get("end"),
            "f0": w.get("f0_median_hz"),
        })
        if i in pause_after:
            tokens.append({"type": "pause",
                           "seconds": round(pause_after[i]["silence_overlap_s"], 1)})

    header = {
        "duration_s": u["duration_s"],
        "n_words": u["n_words"],
        "language": record.get("language"),
        "f0_median_hz": u["f0_median_hz"],
        "f0_range_st": u["f0_range_p5_p95_st"],
        "speech_rate_wps": u["speech_rate_wps"],
        "pause_count": u["pause_count"],
        "pause_total_s": u["pause_total_s"],
    }
    glob = None
    if g and g.get("marker"):
        glob = {
            "marker": g["marker"],
            "rate_wps": g.get("rate_wps"),
            "speaker_rate_wps": g.get("speaker_rate_wps"),
            "rate_dev_pct": g.get("rate_dev_pct"),
            "f0_dev_st": g.get("f0_dev_st"),
        }
    return {"header": header, "tokens": tokens, "global": glob,
            "notation": render_txt(record)}


# --- cloning -------------------------------------------------------------

def _slice_wav(src: Path, dst: Path, t0: float, t1: float) -> Path:
    """Write src[t0:t1] to dst, preserving sample rate."""
    audio, sr = sf.read(str(src))
    if audio.ndim > 1:
        audio = audio.mean(axis=1)
    a, b = int(t0 * sr), int(t1 * sr)
    sf.write(str(dst), audio[a:b], sr, subtype="PCM_16")
    return dst


def slice_to(src: Path, dst: Path, t0: float, t1: float) -> Path:
    """Public slice: write src[t0:t1] to dst (a user-picked reference region)."""
    return _slice_wav(src, dst, t0, t1)


def pick_ref_clip(wav16k: Path, record: dict, out: Path,
                  min_s: float = 3.0, max_s: float = 10.0) -> Path:
    """Carve a clean 3-10 s reference window from a recording for f5 to clone.

    Picks the densest speech run (most words, least pause) so the clone learns
    timbre from continuous voice rather than a hesitation. Falls back to the
    head of the file when word timing is thin.
    """
    words = [w for w in record["words"] if w.get("start") is not None]
    if len(words) >= 4:
        best, best_score = None, -1.0
        for i in range(len(words)):
            t0 = words[i]["start"]
            j = i
            while j + 1 < len(words) and words[j + 1]["end"] - t0 <= max_s:
                j += 1
            span = words[j]["end"] - t0
            if span >= min_s:
                score = (j - i + 1) / span  # words per second over the window
                if score > best_score:
                    best, best_score = (t0, words[j]["end"]), score
        if best:
            return _slice_wav(wav16k, out, best[0], best[1])
    dur = sf.info(str(wav16k)).duration
    return _slice_wav(wav16k, out, 0.0, min(max_s, dur))


def clone_render(record: dict, ref_clip: Path, out_wav: Path, *,
                 condition: str = "prosody", fit_tempo: bool = True,
                 trim_seams: bool = True, clause_min_pause_s: float = 0.4,
                 ref_text: str | None = None) -> Path:
    """Render a record back to audio in the cloned reference voice.

    ref_text is the reference clip's transcript. A saved voice carries it, so
    passing it skips re-running whisper on the reference."""
    backend = F5Backend(ref_audio=ref_clip, ref_text=ref_text, fit_tempo=fit_tempo,
                        trim_seams=trim_seams, clause_min_pause_s=clause_min_pause_s)
    backend.render(record, out_wav, condition)
    return out_wav


def best_ref_window(record: dict, min_s: float = 8.0,
                    max_s: float = 12.0) -> tuple[float, float, str] | None:
    """The densest run of speech in the whole recording, for an f5 reference.

    Scans every start word for the window up to max_s with the most words per
    second (continuous voice, least pause), so the clone learns timbre from a
    clean stretch. Returns (t0, t1, transcript) or None when word timing is thin.
    f5 timbre saturates around 10 s, so max_s past ~12 buys little.
    """
    words = [w for w in record["words"] if w.get("start") is not None]
    if len(words) < 4:
        return None
    best: tuple[int, int] | None = None
    best_score = -1.0
    for i in range(len(words)):
        t0 = words[i]["start"]
        j = i
        while j + 1 < len(words) and words[j + 1]["end"] - t0 <= max_s:
            j += 1
        span = words[j]["end"] - t0
        if span >= min_s:
            score = (j - i + 1) / span
            if score > best_score:
                best, best_score = (i, j), score
    if best is None:
        return None
    i, j = best
    text = " ".join(w["text"] for w in words[i:j + 1])
    return words[i]["start"], words[j]["end"], text


def build_voice_ref(record: dict, hq_source: Path, out_ref: Path) -> tuple[Path, str]:
    """Carve the best reference clip from a recording and return (path, transcript).

    Uses the whole recording to find the cleanest window, then slices it from the
    high-quality source so the saved voice is not band-limited."""
    import soundfile as sf
    win = best_ref_window(record)
    if win is None:
        dur = sf.info(str(hq_source)).duration
        t0, t1 = 0.0, min(12.0, dur)
        text = " ".join(w["text"] for w in record["words"][:30])
    else:
        t0, t1, text = win
    _slice_wav(hq_source, out_ref, t0, t1)
    return out_ref, text


def verify(orig_record: dict, render_wav: Path, orig_wav: Path) -> dict:
    """Score a render against the original record (re-analyzes the render)."""
    rend_record = analyze(render_wav)
    return scorecard(orig_record, rend_record, orig_wav, render_wav)


# --- the guessing game ---------------------------------------------------

def slice_record(record: dict, t_end: float) -> dict:
    """A sub-record covering only words that start before t_end.

    Enough for F5Backend (words[].speech_pieces/text, pauses, utterance), so a
    short target segment can be cloned without re-analyzing audio.
    """
    sub = deepcopy(record)
    keep = [i for i, w in enumerate(record["words"])
            if w.get("start") is not None and w["start"] < t_end]
    if not keep:
        keep = list(range(min(len(record["words"]), 1)))
    last = keep[-1]
    sub["words"] = record["words"][:last + 1]
    sub["pauses"] = [p for p in record["pauses"] if p["after_word"] <= last]
    sub["tempo_spans"] = [s for s in record.get("tempo_spans", [])
                          if s["last_word"] <= last]
    return sub


def target_window(record: dict, max_s: float = 14.0,
                  min_words: int = 5) -> tuple[float, str]:
    """The end time and text of the game's shared target segment."""
    words = [w for w in record["words"] if w.get("start") is not None]
    if not words:
        return 0.0, ""
    chosen = [w for w in words if w["start"] < max_s]
    if len(chosen) < min_words:
        chosen = words[:min_words]
    t_end = chosen[-1]["end"]
    text = " ".join(w["text"] for w in chosen)
    return t_end, text


def clean_window(record: dict, want_s: float = 12.0, *, intro_min_s: float = 2.0,
                 gap_s: float = 0.55, tail_s: float = 0.3) -> tuple[float, float]:
    """A clean content window past any spoken intro, on word boundaries.

    LibriVox readings open with "Title, by Author, read by Reader". The content
    starts after the first real pause that follows a few seconds of that intro.
    Returns (t0, t1), at most want_s long, ending on a word.
    """
    words = record["words"]
    if not words:
        return 0.0, want_s
    pauses = sorted((p for p in record["pauses"] if p["rendered"]),
                    key=lambda p: p["after_word"])
    start_i = 0
    for p in pauses:
        aw = p["after_word"]
        if 0 <= aw < len(words) - 1 and (words[aw].get("end") or 0.0) >= intro_min_s \
                and p["silence_overlap_s"] >= gap_s:
            start_i = aw + 1
            break
    t0 = words[start_i].get("start") or 0.0
    end_i = start_i
    for i in range(start_i, len(words)):
        e = words[i].get("end")
        if e is None:
            continue
        if e - t0 <= want_s:
            end_i = i
        else:
            break
    t1 = (words[end_i].get("end") or t0) + tail_s
    return round(t0, 3), round(t1, 3)


def _equalize_lengths(items: list[dict]) -> None:
    """Make every game item the same length so length is not a tell.

    Each item's edge silence is trimmed, then the clones are time-stretched to
    the human take's exact duration. The human take is only trimmed, never
    stretched, so it stays a real recording.
    """
    import librosa
    import numpy as np

    trimmed: dict[int, tuple] = {}
    for it in items:
        w, sr = sf.read(str(it["file"]))
        if w.ndim > 1:
            w = w.mean(axis=1)
        w = w.astype(np.float32)
        wt, _ = librosa.effects.trim(w, top_db=30.0)
        trimmed[id(it)] = (wt if wt.size else w, sr)
    real = next((it for it in items if it["is_real"]), items[0])
    rw, rsr = trimmed[id(real)]
    target_s = rw.size / rsr
    for it in items:
        w, sr = trimmed[id(it)]
        if it["is_real"] or target_s <= 0:
            out = w
        else:
            rate = min(max((w.size / sr) / target_s, 0.5), 2.0)
            out = librosa.effects.time_stretch(w, rate=rate) if abs(rate - 1.0) > 0.02 else w
        sf.write(str(it["file"]), out, sr, subtype="PCM_16")


def build_game(wav16k: Path, record: dict, out_dir: Path, *,
               n_clones: int = 4, hq_source: Path | None = None,
               progress=None) -> dict:
    """Build a real-vs-clone set: the real human segment plus n synthetic clones.

    The real item is the speaker's own audio of a short target segment (sliced
    from hq_source when given, so its fidelity matches the 24 kHz clones). The
    clones are f5 renders of the same words, varied (fit on/off, prosody vs
    control) so they differ subtly. Every item is then trimmed and length-matched
    so neither length nor leading silence gives the human away.
    """
    out_dir.mkdir(parents=True, exist_ok=True)
    t_end, text = target_window(record)
    sub = slice_record(record, t_end)

    ref_clip = pick_ref_clip(wav16k, record, out_dir / "_ref.wav")

    items: list[dict] = []
    # the real human take (from the high-quality source when supplied)
    real_wav = out_dir / "real.wav"
    _slice_wav(hq_source or wav16k, real_wav, 0.0, t_end)
    items.append({"file": real_wav, "is_real": True, "label": "human"})

    # the clones: vary the recipe so they are not identical renders. The prosody
    # recipes split clauses at 0.3 s to match the notation's own pause threshold
    # (render_min_pause_s), so the clone reproduces every pause the original has,
    # not only the long ones.
    recipes = [
        {"fit_tempo": True, "trim_seams": True, "condition": "prosody", "clause_min_pause_s": 0.30},
        {"fit_tempo": False, "trim_seams": True, "condition": "prosody", "clause_min_pause_s": 0.30},
        {"fit_tempo": True, "trim_seams": True, "condition": "control", "clause_min_pause_s": 0.40},
        {"fit_tempo": False, "trim_seams": False, "condition": "control", "clause_min_pause_s": 0.40},
    ]
    for k in range(n_clones):
        if progress:
            progress.set(0.15 + 0.8 * k / max(1, n_clones),
                         f"rendering clone {k + 1}/{n_clones}")
        r = recipes[k % len(recipes)]
        clone_wav = out_dir / f"clone_{k}.wav"
        clone_render(sub, ref_clip, clone_wav, condition=r["condition"],
                     fit_tempo=r["fit_tempo"], trim_seams=r["trim_seams"],
                     clause_min_pause_s=r["clause_min_pause_s"])
        items.append({"file": clone_wav, "is_real": False, "label": "clone"})

    if progress:
        progress.set(0.96, "trimming and matching lengths")
    _equalize_lengths(items)
    return {"target_text": text, "target_end_s": round(t_end, 2),
            "items": items, "view": record_to_view(sub)}

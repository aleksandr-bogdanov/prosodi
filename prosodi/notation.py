"""Parse the readable prosodi notation back into an analysis record.

The inverse of render.render_txt. Takes notation text - typed by hand or carried
from a capture - and builds the record dict the backends consume, so Reconstruct
can run from notation as well as from a recording. The notation is the interchange
format between the two modules.

Word timing is synthesized from a default speaking rate, lengthened by
<stretched Nx>, with <pause Xs> inserted as gaps between words. That is enough for
f5's structural render, which only reads clause durations + pauses (via
split_clauses). Emphasis, boundary and tempo markers are recorded on each word so
the measured view round-trips, but f5 does not act on them.

Supported markers (same syntax render.py emits):

    <pause 0.8s>          gap after the preceding word
    *word*                emphasized
    word<stretched 2.1x>  lengthened word
    word <rise> / <fall>  pitch boundary on that word
    <faster>...</faster>  tempo span
    <slower>...</slower>
    # ... lines            header/comment lines, ignored
"""

import re

DEFAULT_CPS = 14.0      # chars per second, a neutral speaking rate
MIN_WORD_S = 0.16       # floor so one-letter words still take time

_PAUSE = re.compile(r"<pause\s+([0-9.]+)s>")
_TEMPO_OPEN = re.compile(r"<(faster|slower)>")
_TEMPO_CLOSE = re.compile(r"</(faster|slower)>")
_BOUNDARY = re.compile(r"<(rise|fall)>")
_STRETCH = re.compile(r"<stretched\s+([0-9.]+)x>")

# one scanner token: a marker, or a word (optional *emph*, optional trailing stretch)
_TOKEN = re.compile(
    r"<pause\s+[0-9.]+s>"
    r"|</?(?:faster|slower)>"
    r"|<(?:rise|fall)>"
    r"|<[^>]+>"                                      # any other marker (global etc): ignored
    r"|\*?[^\s*<>]+\*?(?:<stretched\s+[0-9.]+x>)?"   # a word, maybe emphasized / stretched
)


def _clean_word(tok: str) -> tuple[str, bool, float | None]:
    """Strip markers off a word token, return (text, emphasized, stretch)."""
    stretch = None
    m = _STRETCH.search(tok)
    if m:
        stretch = float(m.group(1))
        tok = _STRETCH.sub("", tok)
    emphasized = tok.startswith("*") and tok.endswith("*") and len(tok) > 1
    tok = tok.strip("*")
    return tok, emphasized, stretch


def has_timing_markers(text: str) -> bool:
    """True when the notation carries pauses or stretches worth imposing.

    Plain text with none of these is rendered at the model's natural tempo
    (control condition) rather than an imposed, guessed one."""
    return bool(_PAUSE.search(text) or _STRETCH.search(text))


def parse_notation(text: str, *, default_cps: float = DEFAULT_CPS,
                   language: str = "en") -> dict:
    """Notation text -> analysis record (the inverse of render.render_txt)."""
    body = " ".join(ln for ln in text.splitlines() if not ln.strip().startswith("#"))
    words: list[dict] = []
    pauses: list[dict] = []
    open_tempo: str | None = None
    t = 0.0

    for tok in _TOKEN.findall(body):
        mp = _PAUSE.fullmatch(tok)
        if mp:
            if words:  # a gap after the most recent word
                pauses.append({"after_word": len(words) - 1, "rendered": True,
                               "silence_overlap_s": round(float(mp.group(1)), 3)})
                t += float(mp.group(1))
            continue
        if _TEMPO_OPEN.fullmatch(tok):
            open_tempo = _TEMPO_OPEN.fullmatch(tok).group(1)
            continue
        if _TEMPO_CLOSE.fullmatch(tok):
            open_tempo = None
            continue
        mb = _BOUNDARY.fullmatch(tok)
        if mb:
            if words:
                words[-1]["annotation"]["boundary"] = mb.group(1)
            continue
        if tok.startswith("<"):
            continue  # any other marker: ignore
        wtext, emph, stretch = _clean_word(tok)
        if not wtext:
            continue
        dur = max(MIN_WORD_S, len(wtext) / default_cps) * (stretch or 1.0)
        words.append({
            "text": wtext,
            "speech_pieces": [[round(t, 3), round(t + dur, 3)]],
            "annotation": {"emphasized": emph, "stretched": stretch,
                           "boundary": None, "tempo": open_tempo},
        })
        t += dur

    speech = sum(w["speech_pieces"][-1][1] - w["speech_pieces"][0][0] for w in words)
    return {
        "file": "typed-notation",
        "language": language,
        "words": words,
        "pauses": pauses,
        "tempo_spans": [],  # synthesized record carries no measured tempo spans
        "stretch_spans": [],
        "utterance": {
            "duration_s": round(t, 3),
            "n_words": len(words),
            "speech_rate_wps": round(len(words) / speech, 2) if speech else 0.0,
            "pause_count": len(pauses),
            "pause_total_s": round(sum(p["silence_overlap_s"] for p in pauses), 3),
            "f0_median_hz": None,
            "f0_range_p5_p95_st": None,
            "chars_per_s": default_cps,
        },
    }

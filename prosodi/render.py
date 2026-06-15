"""Render the analysis record as an annotated transcript.

All marker syntax lives in this one module so the notation (v0, provisional)
can be swapped without touching the analysis. Current notation:

    <pause 0.8s>          silence between words
    *word*                emphasized (F0 or intensity peak vs utterance baseline)
    word<stretched 2.1x>  lengthened word (after excluding contained pauses)
    <rise> / <fall>       pitch movement on the clause-final word
    <faster>...</faster>  tempo span notably off the utterance's own rate
    <slower>...</slower>
"""

import textwrap


def render_word(w: dict) -> str:
    ann = w["annotation"]
    out = w["text"]
    if ann["emphasized"]:
        out = f"*{out}*"
    if ann["stretched"] is not None:
        out = f"{out}<stretched {ann['stretched']:.1f}x>"
    if ann["boundary"] is not None:
        out = f"{out} <{ann['boundary']}>"
    return out


def render_txt(record: dict, width: int = 100) -> str:
    words = record["words"]
    pause_after = {p["after_word"]: p for p in record["pauses"] if p["rendered"]}

    tokens: list[str] = []
    open_tempo: str | None = None
    for i, w in enumerate(words):
        tempo = w["annotation"]["tempo"]
        if tempo != open_tempo:
            if open_tempo is not None:
                tokens.append(f"</{open_tempo}>")
            if tempo is not None:
                tokens.append(f"<{tempo}>")
            open_tempo = tempo
        tokens.append(render_word(w))
        if i in pause_after:
            p = pause_after[i]
            # A tempo span never crosses a pause in the rendering.
            if open_tempo is not None and i + 1 < len(words) \
                    and words[i + 1]["annotation"]["tempo"] == open_tempo:
                tokens.append(f"</{open_tempo}>")
                tokens.append(f"<pause {p['silence_overlap_s']:.1f}s>")
                tokens.append(f"<{open_tempo}>")
            else:
                tokens.append(f"<pause {p['silence_overlap_s']:.1f}s>")
    if open_tempo is not None:
        tokens.append(f"</{open_tempo}>")

    g = record.get("global")
    if g and g.get("marker"):
        # Document-level deviation vs the speaker profile, e.g.
        # <agitated rate +49%>. Measured form only, never an emotion label.
        tokens.insert(0, f"<{g['marker']}>")

    body = textwrap.fill(" ".join(tokens), width=width) if tokens else "(no words recognized)"

    u = record["utterance"]
    f0_med = f"{u['f0_median_hz']} Hz" if u["f0_median_hz"] else "n/a (no voiced frames)"
    f0_rng = f"{u['f0_range_p5_p95_st']} st" if u["f0_range_p5_p95_st"] else "n/a"
    header_lines = [
        f"# {record['file'].rsplit('/', 1)[-1]}",
        f"# duration {u['duration_s']}s | words {u['n_words']} | lang {record['language']}",
        f"# F0 median {f0_med} | F0 range (p5-p95) {f0_rng}",
        f"# rate {u['speech_rate_wps']} w/s speaking | pauses {u['pause_count']} "
        f"({u['pause_total_s']}s total)",
    ]
    if g:
        header_lines.append(_global_header(g))
    header = "\n".join(header_lines)
    return f"{header}\n\n{body}\n"


def _global_header(g: dict) -> str:
    """One header line comparing this recording's baseline to the speaker profile."""
    parts = []
    if g["rate_wps"] is not None and g["speaker_rate_wps"] is not None:
        parts.append(f"rate {g['rate_wps']} wps vs speaker {g['speaker_rate_wps']} wps "
                     f"({g['rate_dev_pct']:+d}%)")
    if g["f0_median_hz"] is not None and g["speaker_f0_median_hz"] is not None:
        parts.append(f"F0 {g['f0_median_hz']} Hz vs speaker {g['speaker_f0_median_hz']} Hz "
                     f"({g['f0_dev_st']:+.1f} st)")
    if not parts:
        parts.append("no comparable stats")
    return "# vs speaker profile: " + " | ".join(parts)

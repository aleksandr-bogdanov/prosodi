"""Compile a .prosodi.json record into macOS `say` input with embedded speech commands.

This is the WRITE half of the round trip: the prosody record drives the
synthesizer. The control condition is the same words with no commands at all.

Mapping (prosodi record -> say embedded command):

    utterance speech rate    [[rate W]] at start      W = speech_rate_wps * 60 (wpm over speaking time)
    pause (rendered)         [[slnc N]]               N = silence_overlap_s * 1000, ms
    tempo span faster/slower [[rate W*r]] ... [[rate W]]   r = geometric mean tempo_ratio over the span
    stretched word           [[rate cur/s]] word [[rate cur]]   s = the annotated stretch factor
    emphasized word          [[emph +]] word          (emph applies to the next word only)
    <rise> on word           [[pbas +k]] word [[pbas -k]]   k = |f0_delta_st| clamped to 2..6   (pitch=True only)
    <fall> on word           [[pbas -k]] word [[pbas +k]]                                       (pitch=True only)

Pitch hints are OFF by default: listening agreed with the measurements (the F0
contour transfer was a wash), and the per-word pbas steps produce distracting
semitone jumps. Pass pitch=True (CLI: --pitch) to re-enable them.

`say` rates are clamped to [90, 400] wpm. All values are hints: the probe runs showed
say quantizes them (a 2x rate request rendered as 1.75x, pbas shifts land attenuated).
"""

import math

RATE_MIN, RATE_MAX = 90, 400
PBAS_MIN, PBAS_MAX = 2, 6


def _clamp_rate(wpm: float) -> int:
    return int(round(min(RATE_MAX, max(RATE_MIN, wpm))))


def _geomean(xs: list[float]) -> float | None:
    xs = [x for x in xs if x and x > 0]
    if not xs:
        return None
    return math.exp(sum(math.log(x) for x in xs) / len(xs))


def span_ratio(record: dict, span: dict) -> float | None:
    words = record["words"][span["first_word"]: span["last_word"] + 1]
    return _geomean([w.get("tempo_ratio") for w in words])


def compile_prosody(record: dict, pitch: bool = False) -> str:
    """The prosody condition: words plus embedded commands.

    pitch=False (the default) emits no pbas commands. The boundary rise/fall
    stays in the record and the notation, it just does not drive the voice.
    """
    words = record["words"]
    base = _clamp_rate(record["utterance"]["speech_rate_wps"] * 60)
    pause_after = {p["after_word"]: p for p in record["pauses"] if p["rendered"]}
    span_start = {s["first_word"]: s for s in record["tempo_spans"]}
    span_end = {s["last_word"] for s in record["tempo_spans"]}

    tokens: list[str] = [f"[[rate {base}]]"]
    cur = base
    for i, w in enumerate(words):
        if i in span_start:
            r = span_ratio(record, span_start[i])
            if r:
                cur = _clamp_rate(base * r)
                tokens.append(f"[[rate {cur}]]")

        ann = w["annotation"]
        pre, post = [], []
        if ann["emphasized"]:
            pre.append("[[emph +]]")
        if ann["stretched"] is not None:
            slow = _clamp_rate(cur / ann["stretched"])
            pre.append(f"[[rate {slow}]]")
            post.append(f"[[rate {cur}]]")
        if pitch and ann["boundary"] is not None:
            delta = w.get("f0_delta_st") or 3.0
            k = int(round(min(PBAS_MAX, max(PBAS_MIN, abs(delta)))))
            sign = "+" if ann["boundary"] == "rise" else "-"
            anti = "-" if ann["boundary"] == "rise" else "+"
            pre.append(f"[[pbas {sign}{k}]]")
            post.append(f"[[pbas {anti}{k}]]")

        tokens.extend(pre)
        tokens.append(w["text"])
        tokens.extend(post)

        if i in span_end:
            cur = base
            tokens.append(f"[[rate {base}]]")
        if i in pause_after:
            ms = int(round(pause_after[i]["silence_overlap_s"] * 1000))
            tokens.append(f"[[slnc {ms}]]")

    return " ".join(tokens)


def compile_control(record: dict) -> str:
    """The control condition: the same words, no commands, default settings."""
    return " ".join(w["text"] for w in record["words"])

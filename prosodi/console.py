"""Rich console rendering of an analysis record.

The notation renderer (prosodi/render.py) owns the .prosodi.txt FILE format and
never changes here. This module owns how the same record looks in a TERMINAL:
color and arrows instead of marker syntax. Nothing from this module ever lands
in a file.

Console mapping (notation -> terminal):

    <pause 0.8s>          dim cyan
    *word*                bold yellow word, asterisks dropped
    word<stretched 2.1x>  magenta word + dim magenta factor
    <rise> / <fall>       dim arrow after the word
    <faster>...</faster>  green span
    <slower>...</slower>  blue span
    <agitated ...>        red banner line
    <subdued ...>         cyan banner line

Use console rendering only when stdout is a tty and --plain was not passed,
the file notation is the pipe-safe form.
"""

import sys

from rich.console import Console
from rich.panel import Panel
from rich.table import Table
from rich.text import Text

_console = Console(highlight=False, soft_wrap=False)


def use_console(plain_flag: bool) -> bool:
    """Console rendering is opt-out: --plain or a non-tty stdout disables it."""
    return not plain_flag and sys.stdout.isatty()


def print_header(record: dict) -> None:
    """The header block as a compact panel: file, duration, words, lang, F0, rate, pauses."""
    u = record["utterance"]
    f0_med = f"{u['f0_median_hz']} Hz" if u["f0_median_hz"] else "n/a (no voiced frames)"
    f0_rng = f"{u['f0_range_p5_p95_st']} st" if u["f0_range_p5_p95_st"] else "n/a"

    body = Text()
    body.append(f"duration {u['duration_s']}s   words {u['n_words']}   "
                f"lang {record['language']}\n")
    body.append(f"F0 median {f0_med}   range (p5-p95) {f0_rng}\n")
    body.append(f"rate {u['speech_rate_wps']} w/s speaking   "
                f"pauses {u['pause_count']} ({u['pause_total_s']}s total)")
    g = record.get("global")
    if g:
        parts = []
        if g["rate_wps"] is not None and g["speaker_rate_wps"] is not None:
            parts.append(f"rate {g['rate_wps']} vs speaker {g['speaker_rate_wps']} wps "
                         f"({g['rate_dev_pct']:+d}%)")
        if g["f0_median_hz"] is not None and g["speaker_f0_median_hz"] is not None:
            parts.append(f"F0 {g['f0_median_hz']} vs speaker {g['speaker_f0_median_hz']} Hz "
                         f"({g['f0_dev_st']:+.1f} st)")
        if parts:
            body.append("\nvs profile: " + "   ".join(parts), style="dim")

    name = record["file"].rsplit("/", 1)[-1]
    _console.print(Panel(body, title=name, title_align="left", border_style="dim",
                         padding=(0, 1), expand=False))


def _word_text(w: dict, span_style: str) -> Text:
    """One word with its annotations as color, never as marker syntax."""
    ann = w["annotation"]
    t = Text()
    if ann["emphasized"]:
        t.append(w["text"], style="bold yellow")
    elif ann["stretched"] is not None:
        t.append(w["text"], style="magenta")
    else:
        t.append(w["text"], style=span_style)
    if ann["stretched"] is not None:
        t.append(f" {ann['stretched']:.1f}x", style="dim magenta")
    if ann["boundary"] is not None:
        arrow = "↗" if ann["boundary"] == "rise" else "↘"
        t.append(f" {arrow}", style="dim")
    return t


def render_console(record: dict) -> Text:
    """The annotated transcript as colorized rich Text (same walk as render_txt)."""
    words = record["words"]
    if not words:
        return Text("(no words recognized)", style="dim")
    pause_after = {p["after_word"]: p for p in record["pauses"] if p["rendered"]}

    out = Text()
    g = record.get("global")
    if g and g.get("marker"):
        style = "bold red" if g["marker"].startswith("agitated") else "bold cyan"
        out.append(f"--- {g['marker']} ---\n", style=style)

    for i, w in enumerate(words):
        if i > 0:
            out.append(" ")
        tempo = w["annotation"]["tempo"]
        span_style = {"faster": "green", "slower": "blue"}.get(tempo, "")
        out.append_text(_word_text(w, span_style))
        if i in pause_after:
            p = pause_after[i]
            out.append(f" <pause {p['silence_overlap_s']:.1f}s>", style="dim cyan")
    return out


def print_transcript(record: dict) -> None:
    _console.print(render_console(record), end="\n\n")


def roundtrip_table(rows: list[dict]) -> Table:
    """The batch summary: one row per sample."""
    t = Table(title="round-trip summary", title_style="bold", border_style="dim")
    t.add_column("sample")
    t.add_column("dur (s)", justify="right")
    t.add_column("words", justify="right")
    t.add_column("pauses", justify="right")
    t.add_column("emph", justify="right")
    t.add_column("stretch", justify="right")
    t.add_column("rise/fall", justify="right")
    t.add_column("spans", justify="right")
    t.add_column("output")
    for r in rows:
        t.add_row(r["sample"], f"{r['duration_s']}", str(r["words"]), str(r["pauses"]),
                  str(r["emphasized"]), str(r["stretched"]), str(r["boundaries"]),
                  str(r["tempo_spans"]), r["path"])
    return t


def print_roundtrip_summary(rows: list[dict]) -> None:
    _console.print(roundtrip_table(rows))

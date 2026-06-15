"""Score a rendered wav against the original it was synthesized from.

The notation's whole point is that it carries measurable values, so any
synthesis backend can be checked against it: analyze both wavs with the same
instrument (mlx-whisper word timestamps + parselmouth acoustics), align the
words by normalized text (difflib, fuzzy because whisper can hear the
synthetic voice slightly differently), then score per marker class:

    pauses        recall of the spec'd pauses + mean abs duration error
    tempo spans   direction agreement + magnitude ratio (log space)
    stretch       realization ratio (log space) on the spec'd stretched words
    speech rate   rendered wps / original wps
    F0            utterance median offset (st) + word-level contour
                  correlation (each side relative to its own median, so the
                  voices' absolute registers cancel)

F0 is always reported, even for backends with no pitch control at all: the
scorecard's job is to show what each backend drops, never to hide it. The
exit code is always 0, this is a measurement, never a gate.

Records are cached: an up-to-date <stem>.prosodi.json next to a wav is reused
instead of re-running whisper, and a fresh analysis is written back there.
"""

import json
import math
import sys
from difflib import SequenceMatcher
from pathlib import Path

from .analyze import analyze_file
from .config import DEFAULT

# A gap in the rendered record counts as a detected pause from this much
# silence overlap on. Lower than the render threshold (0.30 s) so a spec'd
# 0.3 s pause that came out at 0.25 s still counts, with its error reported.
DETECT_MIN_S = 0.15
# An inserted pause (precision side) must be a real one.
INSERT_MIN_S = 0.30


def _norm(t: str) -> str:
    return "".join(c for c in t.lower() if c.isalnum())


def _st(hz: float, ref: float) -> float:
    return 12.0 * math.log2(hz / ref)


def _pearson(xs: list[float], ys: list[float]) -> float | None:
    n = len(xs)
    if n < 3:
        return None
    mx, my = sum(xs) / n, sum(ys) / n
    sxy = sum((x - mx) * (y - my) for x, y in zip(xs, ys))
    sxx = sum((x - mx) ** 2 for x in xs)
    syy = sum((y - my) ** 2 for y in ys)
    if sxx == 0 or syy == 0:
        return None
    return sxy / math.sqrt(sxx * syy)


def _geomean(xs: list) -> float | None:
    xs = [x for x in xs if x and x > 0]
    if not xs:
        return None
    return math.exp(sum(math.log(x) for x in xs) / len(xs))


def load_record(wav: Path) -> dict:
    """Analyze a wav, reusing an up-to-date cached record next to it."""
    cache = wav.parent / f"{wav.stem}.prosodi.json"
    if cache.exists() and cache.stat().st_mtime >= wav.stat().st_mtime:
        return json.loads(cache.read_text(encoding="utf-8"))
    record = analyze_file(str(wav), DEFAULT)
    cache.write_text(json.dumps(record, ensure_ascii=False, indent=1), encoding="utf-8")
    return record


def align_words(orig_words: list[dict], rend_words: list[dict]) -> dict[int, int]:
    a = [_norm(w["text"]) for w in orig_words]
    b = [_norm(w["text"]) for w in rend_words]
    sm = SequenceMatcher(a=a, b=b, autojunk=False)
    mapping: dict[int, int] = {}
    for blk in sm.get_matching_blocks():
        for k in range(blk.size):
            mapping[blk.a + k] = blk.b + k
    return mapping


def _pause_score(orig: dict, rend: dict, mapping: dict[int, int]) -> dict:
    spec = [p for p in orig["pauses"] if p["rendered"]]
    rend_pauses = {p["after_word"]: p for p in rend["pauses"]
                   if p["silence_overlap_s"] >= DETECT_MIN_S}
    errors = []
    for p in spec:
        j = mapping.get(p["after_word"])
        hit = rend_pauses.get(j) if j is not None else None
        if hit is not None:
            errors.append(hit["silence_overlap_s"] - p["silence_overlap_s"])
    spec_positions = {mapping.get(p["after_word"]) for p in spec}
    inserted = sum(1 for j, p in rend_pauses.items()
                   if j not in spec_positions and p["silence_overlap_s"] >= INSERT_MIN_S)
    return {
        "spec": len(spec),
        "matched": len(errors),
        "recall": round(len(errors) / len(spec), 3) if spec else None,
        "mean_abs_err_s": round(sum(abs(e) for e in errors) / len(errors), 3) if errors else None,
        "mean_signed_err_s": round(sum(errors) / len(errors), 3) if errors else None,
        "inserted": inserted,
    }


def _tempo_score(orig: dict, rend: dict, mapping: dict[int, int]) -> dict:
    spans, scored, agree, mags = [], 0, 0, []
    for s in orig["tempo_spans"]:
        idxs = range(s["first_word"], s["last_word"] + 1)
        o = _geomean([orig["words"][i].get("tempo_ratio") for i in idxs])
        r = _geomean([rend["words"][mapping[i]].get("tempo_ratio")
                      for i in idxs if i in mapping])
        spans.append({"kind": s["kind"], "orig_ratio": round(o, 2) if o else None,
                      "rend_ratio": round(r, 2) if r else None})
        if not o or not r or abs(math.log(o)) < 1e-6:
            continue
        scored += 1
        if (o - 1.0) * (r - 1.0) > 0:
            agree += 1
        mags.append(math.log(r) / math.log(o))
    return {
        "spec": len(orig["tempo_spans"]),
        "scored": scored,
        "direction_agree": agree,
        "magnitude_ratio": round(sum(mags) / len(mags), 2) if mags else None,
        "spans": spans,
    }


def _stretch_score(orig: dict, rend: dict, mapping: dict[int, int]) -> dict:
    words, ratios = [], []
    for i, w in enumerate(orig["words"]):
        s = w["annotation"]["stretched"]
        if s is None or i not in mapping:
            continue
        r = rend["words"][mapping[i]].get("stretch_factor")
        words.append({"word": w["text"], "orig": s, "rend": r})
        if r and r > 0 and s > 1.0:
            ratios.append(math.log(r) / math.log(s))
    return {
        "spec": sum(1 for w in orig["words"] if w["annotation"]["stretched"] is not None),
        "scored": len(ratios),
        "realization_ratio": round(sum(ratios) / len(ratios), 2) if ratios else None,
        "words": words,
    }


def _rate_score(orig: dict, rend: dict) -> dict:
    o = orig["utterance"]["speech_rate_wps"]
    r = rend["utterance"]["speech_rate_wps"]
    return {
        "orig_wps": o,
        "rend_wps": r,
        "ratio": round(r / o, 2) if o and r else None,
    }


def _f0_score(orig: dict, rend: dict, mapping: dict[int, int]) -> dict:
    om = orig["utterance"]["f0_median_hz"]
    rm = rend["utterance"]["f0_median_hz"]
    xs, ys = [], []
    if om and rm:
        for i, j in mapping.items():
            fo = orig["words"][i].get("f0_median_hz")
            fr = rend["words"][j].get("f0_median_hz")
            if fo and fr:
                xs.append(_st(fo, om))
                ys.append(_st(fr, rm))
    r = _pearson(xs, ys)
    rmse = math.sqrt(sum((x - y) ** 2 for x, y in zip(xs, ys)) / len(xs)) if xs else None
    return {
        "median_offset_st": round(_st(rm, om), 2) if om and rm else None,
        "contour_r": round(r, 3) if r is not None else None,
        "contour_rmse_st": round(rmse, 2) if rmse is not None else None,
        "n_words": len(xs),
    }


def scorecard(orig: dict, rend: dict, original: Path, render: Path) -> dict:
    mapping = align_words(orig["words"], rend["words"])
    return {
        "original": str(original),
        "render": str(render),
        "words": {"orig": len(orig["words"]), "rend": len(rend["words"]),
                  "aligned": len(mapping)},
        "pauses": _pause_score(orig, rend, mapping),
        "tempo_spans": _tempo_score(orig, rend, mapping),
        "stretch": _stretch_score(orig, rend, mapping),
        "speech_rate": _rate_score(orig, rend),
        "f0": _f0_score(orig, rend, mapping),
    }


def _fmt(v, suffix: str = "") -> str:
    return "-" if v is None else f"{v}{suffix}"


def print_scorecard(card: dict) -> None:
    from rich.console import Console
    from rich.table import Table

    p, t, st, ra, f0 = (card["pauses"], card["tempo_spans"], card["stretch"],
                        card["speech_rate"], card["f0"])
    w = card["words"]
    table = Table(title=f"verify: {Path(card['render']).name} vs "
                        f"{Path(card['original']).name}   "
                        f"(aligned {w['aligned']}/{w['orig']} words)",
                  title_style="bold", border_style="dim")
    table.add_column("marker class")
    table.add_column("spec", justify="right")
    table.add_column("result")
    table.add_row("pauses", str(p["spec"]),
                  f"recall {_fmt(p['recall'])}, |err| {_fmt(p['mean_abs_err_s'], ' s')}, "
                  f"inserted {p['inserted']}")
    table.add_row("tempo spans", str(t["spec"]),
                  f"direction {t['direction_agree']}/{t['scored']}, "
                  f"magnitude x{_fmt(t['magnitude_ratio'])}")
    table.add_row("stretch", str(st["spec"]),
                  f"realization x{_fmt(st['realization_ratio'])} over {st['scored']} words")
    table.add_row("speech rate", "-",
                  f"render/orig x{_fmt(ra['ratio'])} "
                  f"({_fmt(ra['rend_wps'])} vs {_fmt(ra['orig_wps'])} wps)")
    table.add_row("F0 median", "-", f"offset {_fmt(f0['median_offset_st'], ' st')}")
    table.add_row("F0 contour", "-",
                  f"r {_fmt(f0['contour_r'])} over {f0['n_words']} words, "
                  f"rmse {_fmt(f0['contour_rmse_st'], ' st')}")
    Console(highlight=False).print(table)


def run_verify(args) -> int:
    for wav in (args.original, args.render):
        if not wav.exists():
            print(f"no such file: {wav}", file=sys.stderr)
            return 1
    orig = load_record(args.original)
    rend = load_record(args.render)
    card = scorecard(orig, rend, args.original, args.render)
    if args.as_json:
        print(json.dumps(card, ensure_ascii=False, indent=1))
    else:
        print_scorecard(card)
    return 0

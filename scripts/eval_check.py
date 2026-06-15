"""Eval cross-checks over batch output: pause recall vs parselmouth silences,
stretched-word plausibility, annotation density. Feeds EVAL.md."""

import json
import sys
from pathlib import Path

out = Path(sys.argv[1] if len(sys.argv) > 1 else "out")

rows = []
for jpath in sorted(out.glob("*.prosodi.json")):
    r = json.loads(jpath.read_text())
    u = r["utterance"]
    words = r["words"]
    silences = r["silences"]
    rendered = [p for p in r["pauses"] if p["rendered"]]

    # Every internal silence should surface as a rendered pause. A silence with
    # no rendered pause overlapping it was swallowed (usually inside a word span).
    def covered(sil):
        return any(max(0, min(sil[1], p["end"]) - max(sil[0], p["start"])) > 0.05
                   for p in rendered)
    missed = [s for s in silences if not covered(s)]

    stretched = [w for w in words if w["annotation"]["stretched"]]
    stretched_suspect = [w for w in stretched if w["absorbed_speech_s"] > 0.1]
    emph = [w for w in words if w["annotation"]["emphasized"]]
    bounds = [w for w in words if w["annotation"]["boundary"]]
    tempo_words = [w for w in words if w["annotation"]["tempo"]]
    low_prob = [w for w in words if w["probability"] < 0.3]
    no_f0 = [w for w in words if w["f0_median_hz"] is None]
    not_in_speech = [w for w in words if not w["in_speech"]]

    rows.append({
        "id": jpath.stem.split("-")[0],
        "dur": u["duration_s"], "words": u["n_words"], "lang": r["language"],
        "silences": len(silences), "pauses_rendered": len(rendered),
        "silences_missed": len(missed),
        "missed_durs": [round(s[1] - s[0], 2) for s in missed][:6],
        "emph": len(emph), "stretch": len(stretched),
        "stretch_suspect": len(stretched_suspect),
        "bounds": len(bounds), "tempo": len(tempo_words),
        "low_prob": len(low_prob), "no_f0": len(no_f0),
        "quiet_words": len(not_in_speech),
        "f0_med": u["f0_median_hz"], "rate": u["speech_rate_wps"],
        "stretch_list": [(w["text"], w["annotation"]["stretched"],
                          w["absorbed_speech_s"]) for w in stretched][:8],
        "emph_list": [w["text"] for w in emph][:12],
    })

hdr = ("id", "dur", "words", "lang", "silences", "pauses_rendered", "silences_missed",
       "emph", "stretch", "stretch_suspect", "bounds", "tempo", "low_prob", "no_f0",
       "quiet_words", "f0_med", "rate")
print("\t".join(hdr))
for r in rows:
    print("\t".join(str(r[k]) for k in hdr))

tot = {k: sum(r[k] for r in rows) for k in
       ("words", "silences", "pauses_rendered", "silences_missed", "emph",
        "stretch", "stretch_suspect", "bounds", "tempo")}
recall = 100.0 * (tot["silences"] - tot["silences_missed"]) / tot["silences"] \
    if tot["silences"] else 0.0
print(f"TOTAL\twords={tot['words']} silences={tot['silences']} "
      f"missed={tot['silences_missed']} pause_recall={recall:.1f}% "
      f"emph={tot['emph']} ({100.0 * tot['emph'] / tot['words']:.1f}% of words) "
      f"stretch={tot['stretch']} suspect={tot['stretch_suspect']} "
      f"bounds={tot['bounds']} tempo={tot['tempo']}")
print()
for r in rows:
    print(f"{r['id']}: missed_sil={r['missed_durs']} stretched={r['stretch_list']}")
    print(f"  emph={r['emph_list']}")

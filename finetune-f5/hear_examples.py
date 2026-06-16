"""Render a batch of varied lines through the fine-tuned f5, to ear-test the voice.

Loads the fine-tuned model once and renders several lines (question, casual, long,
short, plus one line at a fast and a slow target duration to hear the pacing handle).

    REF_WAV=data/ref/ref.wav REF_TEXT="..." .env/bin/python hear_examples.py
"""

import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent))
import f5_sidecar as sc  # noqa: E402

LINES = [
    ("question", "How will you survive your family at Christmas?", None),
    ("casual", "I genuinely don't know what to tell you about that one.", None),
    ("long", "The numbers went up, then down, then up again, and nobody could quite "
             "explain why it kept happening.", None),
    ("short", "Wait. Say that again?", None),
    ("paced_fast", "Here is the same sentence at two different speeds.", 2.0),
    ("paced_slow", "Here is the same sentence at two different speeds.", 3.6),
]


def main():
    import soundfile as sf
    sc.STATE = sc.load_model()
    out = Path(__file__).resolve().parent / "data" / "out" / "examples"
    out.mkdir(parents=True, exist_ok=True)
    print(f"\nrendering {len(LINES)} lines...\n", flush=True)
    for name, text, dur in LINES:
        wav, srate = sc.render_one(text, dur, 1.0)
        p = out / f"{name}.wav"
        sf.write(str(p), wav, srate)
        tag = f" [target {dur}s]" if dur else ""
        print(f"  {p.name}: {len(wav) / srate:.2f}s{tag}  '{text[:42]}'", flush=True)
    print(f"\nexamples in {out}")


if __name__ == "__main__":
    main()

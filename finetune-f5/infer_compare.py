"""Phase 3: A/B the fine-tuned f5 against zero-shot f5, and verify duration control.

Mirrors finetune/infer_compare.py. Same text, same reference clip, two voices:
  - fine-tuned: the checkpoint train.py just produced
  - zero-shot:  the stock F5TTS_v1_Base (what prosodi runs today)
Writes data/out/finetuned.wav and data/out/zeroshot.wav so you can listen. The
fine-tune should sound more like the speaker.

    .env/bin/python infer_compare.py "Some sentence to read."
    .env/bin/python infer_compare.py --verify "Some sentence to read."

--verify FIRST: renders the line at two target durations (2.0 s and 4.0 s of generated
speech) through the fine-tuned model and prints the output lengths. If fix_duration
survived the fine-tune, the two clips differ in length by ~2 s. If they come out the
same, f5's duration handle did NOT survive - a blocking finding, log it (HANDOFF.md).
"""

import os
import sys
from pathlib import Path

HERE = Path(__file__).resolve().parent
OUTDIR = HERE / "data" / "out"
OUTDIR.mkdir(parents=True, exist_ok=True)

# reuse the sidecar's locators so both agree on ckpt/vocab/reference
sys.path.insert(0, str(HERE))
import f5_sidecar as sc  # noqa: E402

MIN_CLAUSE_S = sc.MIN_CLAUSE_S


def load_finetuned():
    from f5_tts.api import F5TTS
    dev = sc.pick_device()
    ckpt = sc.find_finetuned_ckpt()
    vocab = sc.find_vocab()
    print(f"fine-tuned ckpt: {ckpt}\nvocab: {vocab}\ndevice: {dev}", flush=True)
    try:
        return F5TTS(model="F5TTS_v1_Base", ckpt_file=str(ckpt),
                     vocab_file=str(vocab), device=dev)
    except TypeError:
        return F5TTS(model_type="F5TTS_v1_Base", ckpt_file=str(ckpt),
                     vocab_file=str(vocab), device=dev)


def load_zeroshot():
    from f5_tts.api import F5TTS
    dev = sc.pick_device()
    print("zero-shot: stock F5TTS_v1_Base", flush=True)
    try:
        return F5TTS(model="F5TTS_v1_Base", device=dev)
    except TypeError:
        return F5TTS(model_type="F5TTS_v1_Base", device=dev)


def render(model, ref_file, ref_text, text, fix_duration=None):
    import numpy as np
    wav, sr, _ = model.infer(
        ref_file=ref_file, ref_text=ref_text, gen_text=text,
        fix_duration=fix_duration, speed=1.0, nfe_step=32,
        remove_silence=False, show_info=lambda *a, **k: None,
    )
    return np.asarray(wav, dtype=np.float32), sr


def main():
    import soundfile as sf

    args = sys.argv[1:]
    verify = "--verify" in args
    args = [a for a in args if a != "--verify"]
    text = args[0] if args else "How will you survive your family at Christmas?"

    ref_file, ref_text = sc.pick_reference()
    ref_seconds = sf.info(ref_file).duration
    print(f"reference: {Path(ref_file).name} ({ref_seconds:.1f}s)\ntext: {text!r}\n", flush=True)

    ft = load_finetuned()

    if verify:
        # The whole point: does the duration handle survive the fine-tune?
        print("\n=== duration-control verification (fine-tuned model) ===", flush=True)
        rows = []
        for target in (2.0, 4.0):
            wav, sr = render(ft, ref_file, ref_text, text,
                             fix_duration=ref_seconds + max(target, MIN_CLAUSE_S))
            got = len(wav) / sr
            p = OUTDIR / f"verify_{target:.0f}s.wav"
            sf.write(str(p), wav, sr)
            rows.append((target, got, p))
            print(f"  target gen {target:.1f}s -> output {got:.2f}s   ({p.name})", flush=True)
        spread = abs(rows[1][1] - rows[0][1])
        print(f"\n  length spread between the two targets: {spread:.2f}s")
        if spread >= 1.0:
            print("  PASS: fix_duration is honored - duration control SURVIVED the fine-tune.")
        else:
            print("  FAIL: outputs are ~same length - duration control did NOT survive. "
                  "Blocking finding, log it per HANDOFF.md.")
        print()

    # A/B render: fine-tuned vs zero-shot, natural duration, same ref + text
    wav, sr = render(ft, ref_file, ref_text, text)
    sf.write(str(OUTDIR / "finetuned.wav"), wav, sr)
    print("wrote finetuned.wav", flush=True)

    del ft
    import torch
    if torch.cuda.is_available():
        torch.cuda.empty_cache()

    zs = load_zeroshot()
    wav, sr = render(zs, ref_file, ref_text, text)
    sf.write(str(OUTDIR / "zeroshot.wav"), wav, sr)
    print("wrote zeroshot.wav", flush=True)

    print(f"\nA/B: {OUTDIR/'finetuned.wav'}  vs  {OUTDIR/'zeroshot.wav'}")


if __name__ == "__main__":
    main()

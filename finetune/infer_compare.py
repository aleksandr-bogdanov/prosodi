"""Phase 3: render the same line through the fine-tuned model and zero-shot XTTS.

Writes data/out/finetuned.wav and data/out/zeroshot.wav so you can A/B whether the
fine-tune actually beats zero-shot. Same text, same reference clip, both voices.

    finetune/.env/bin/python finetune/infer_compare.py "Some sentence to read."

The fine-tuned checkpoint + config + vocab come from the training run dir. The
exact file names are coqui-version-specific, so this searches for them and prints
what it found. If it cannot find them, read data/train_result.txt (train.py saved
the paths train_gpt returned) and point CKPT/CONFIG/VOCAB at them.
"""

import os
import sys
from pathlib import Path

os.environ.setdefault("COQUI_TOS_AGREED", "1")
os.environ.setdefault("PYTORCH_ENABLE_MPS_FALLBACK", "1")

HERE = Path(__file__).resolve().parent
RUN = HERE / "data" / "run"
DATASET = HERE / "data" / "dataset"
OUTDIR = HERE / "data" / "out"
OUTDIR.mkdir(parents=True, exist_ok=True)

TEXT = sys.argv[1] if len(sys.argv) > 1 else "How will you survive your family at Christmas?"


def find(pattern: str) -> Path | None:
    hits = sorted(RUN.rglob(pattern), key=lambda p: p.stat().st_mtime, reverse=True)
    return hits[0] if hits else None


def main() -> None:
    import torch
    from TTS.tts.configs.xtts_config import XttsConfig
    from TTS.tts.models.xtts import Xtts
    import soundfile as sf

    ckpt = os.environ.get("CKPT") or find("best_model.pth") or find("*.pth")
    config = os.environ.get("CONFIG") or find("config.json")
    vocab = os.environ.get("VOCAB") or find("vocab.json")
    ref = next(iter(sorted((DATASET / "wavs").glob("*.wav"))), None)
    if not (ckpt and config and vocab and ref):
        print("could not locate model files. found:",
              {"ckpt": ckpt, "config": config, "vocab": vocab, "ref": ref})
        print("check data/train_result.txt and set CKPT/CONFIG/VOCAB env vars.")
        sys.exit(1)
    print(f"fine-tuned ckpt: {ckpt}\nconfig: {config}\nvocab: {vocab}\nref: {ref}")

    # fine-tuned render
    cfg = XttsConfig()
    cfg.load_json(str(config))
    model = Xtts.init_from_config(cfg)
    model.load_checkpoint(cfg, checkpoint_path=str(ckpt), vocab_path=str(vocab),
                          use_deepspeed=False)
    gpt_lat, spk = model.get_conditioning_latents(audio_path=[str(ref)])
    out = model.inference(TEXT, "en", gpt_lat, spk, temperature=0.7)
    sf.write(str(OUTDIR / "finetuned.wav"), out["wav"], 24000)
    print("wrote finetuned.wav")

    # zero-shot render (the baseline)
    from TTS.api import TTS
    zs = TTS("tts_models/multilingual/multi-dataset/xtts_v2").to("cpu")
    zs.tts_to_file(text=TEXT, speaker_wav=str(ref), language="en",
                   file_path=str(OUTDIR / "zeroshot.wav"))
    print("wrote zeroshot.wav")
    print("\nA/B: data/out/finetuned.wav vs data/out/zeroshot.wav")


if __name__ == "__main__":
    main()

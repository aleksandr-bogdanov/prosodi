"""XTTS render sidecar.

The fine-tuned XTTS is torch-based and heavy, so it stays out of the MLX core.
This script runs in finetune/.env (torch + coqui), loads the model ONCE, and
renders a batch of clause texts in the speaker's voice. The prosodi XTTSBackend
shells out to it and does the trim/fit/assembly itself in the main env.

Usage (the backend calls this, you rarely do by hand):
    finetune/.env/bin/python finetune/xtts_sidecar.py <request.json>

request.json: {"ckpt","config","vocab","ref","texts":[...],"out_dir"}
Writes out_dir/clip_0.wav ... clip_N.wav (raw 24 kHz, natural pace - the backend
shapes them to the measured clause durations).
"""

import json
import os
import sys
from pathlib import Path

os.environ.setdefault("COQUI_TOS_AGREED", "1")
os.environ.setdefault("PYTORCH_ENABLE_MPS_FALLBACK", "1")


def main() -> None:
    req = json.loads(Path(sys.argv[1]).read_text(encoding="utf-8"))
    from TTS.tts.configs.xtts_config import XttsConfig
    from TTS.tts.models.xtts import Xtts
    import soundfile as sf

    cfg = XttsConfig()
    cfg.load_json(req["config"])
    model = Xtts.init_from_config(cfg)
    model.load_checkpoint(cfg, checkpoint_path=req["ckpt"], vocab_path=req["vocab"],
                          use_deepspeed=False)
    gpt_lat, speaker = model.get_conditioning_latents(audio_path=[req["ref"]])

    out_dir = Path(req["out_dir"])
    out_dir.mkdir(parents=True, exist_ok=True)
    for i, text in enumerate(req["texts"]):
        out = model.inference(text, "en", gpt_lat, speaker, temperature=0.7)
        sf.write(str(out_dir / f"clip_{i}.wav"), out["wav"], 24000)
    print(f"xtts sidecar: rendered {len(req['texts'])} clip(s) to {out_dir}")


if __name__ == "__main__":
    main()

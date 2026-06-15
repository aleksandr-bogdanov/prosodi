"""Phase 2: fine-tune XTTS on the prepared dataset.

The first thing that matters is SPEED. Without CUDA the coqui trainer runs on MPS
(workable) or CPU (slow), and we do not yet know which the M5 gives or how fast.
So watch the first dozen steps: the trainer prints step time. If a step is a few
seconds, a fine-tune is hours and worth it. If a step is tens of seconds, this is
a CPU fallback and the real run belongs on a cloud GPU.

    finetune/.env/bin/python finetune/train.py        # defaults: 6 epochs, batch 3
    EPOCHS=2 BATCH=2 finetune/.env/bin/python finetune/train.py   # a quick gauge run

train_gpt returns the paths the inference step needs (config, vocab, the
fine-tuned checkpoint, a speaker reference). They are saved to data/train_result.txt.
"""

import json
import os
import time
from pathlib import Path

os.environ.setdefault("COQUI_TOS_AGREED", "1")
os.environ.setdefault("PYTORCH_ENABLE_MPS_FALLBACK", "1")  # let unsupported ops fall to CPU

HERE = Path(__file__).resolve().parent
DATASET = HERE / "data" / "dataset"
OUT = HERE / "data" / "run"
OUT.mkdir(parents=True, exist_ok=True)


def main() -> None:
    from TTS.demos.xtts_ft_demo.utils.gpt_train import train_gpt

    cfg = dict(
        language="en",
        num_epochs=int(os.environ.get("EPOCHS", "6")),
        batch_size=int(os.environ.get("BATCH", "3")),
        grad_acumm=int(os.environ.get("GRAD", "4")),
        train_csv=str(DATASET / "metadata_train.csv"),
        eval_csv=str(DATASET / "metadata_eval.csv"),
        output_path=str(OUT),
    )
    print(">>> training config:", cfg, flush=True)
    print(">>> WATCH THE FIRST STEPS for step time (see this file's docstring).", flush=True)
    t0 = time.time()
    result = train_gpt(**cfg)
    secs = round(time.time() - t0)
    print(f"\nTRAIN DONE in {secs}s")
    # result is a tuple of paths (order is coqui-version-specific); save them all
    paths = [str(x) for x in result] if isinstance(result, (list, tuple)) else [str(result)]
    (HERE / "data" / "train_result.txt").write_text("\n".join(paths), encoding="utf-8")
    print(">>> paths the inference step needs:")
    for p in paths:
        print("   ", p)


if __name__ == "__main__":
    main()

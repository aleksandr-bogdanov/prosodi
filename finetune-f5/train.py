"""Phase 2: fine-tune F5-TTS on the prepared dataset.

The CLI name and flags drift between F5-TTS releases. VERIFY with
`f5-tts_finetune-cli --help` (and the gradio finetune for reference) and adjust the
flags below before trusting them. The values are a small-dataset starting point
(SWivid discussion #769): low learning rate, frame-based batching, a few thousand
updates for ~1 hr of audio.

As with the XTTS run: watch the first ~20 steps for step time and decide hours vs
cloud before committing.

    finetune-f5/.env/bin/python finetune-f5/train.py
"""

import os
import subprocess
import sys
import time
from pathlib import Path

os.environ.setdefault("PYTORCH_ENABLE_MPS_FALLBACK", "1")

HERE = Path(__file__).resolve().parent
# The name prepare.py registered the dataset under (verify against where
# prepare_csv_wavs actually wrote it / how finetune-cli expects --dataset_name).
DATASET = os.environ.get("DATASET_NAME", "prosodi_speaker")
FINETUNE_CLI = HERE / ".env" / "bin" / "f5-tts_finetune-cli"


def main() -> None:
    if not FINETUNE_CLI.exists():
        print(f"{FINETUNE_CLI} not found. Check the f5-tts entry points: "
              f"`ls finetune-f5/.env/bin | grep f5`", file=sys.stderr)
        sys.exit(1)
    cmd = [str(FINETUNE_CLI), "--finetune",
           "--dataset_name", DATASET,
           "--learning_rate", os.environ.get("LR", "1e-5"),
           "--epochs", os.environ.get("EPOCHS", "10"),
           "--batch_size_per_gpu", os.environ.get("BATCH", "3200"),
           "--batch_size_type", "frame",
           "--num_warmup_updates", "100",
           "--save_per_updates", "500"]
    print(">>> verify these flags with `f5-tts_finetune-cli --help` first", flush=True)
    print(">>> running:", " ".join(cmd), flush=True)
    print(">>> WATCH THE FIRST ~20 STEPS for step time, then decide local vs cloud.",
          flush=True)
    t0 = time.time()
    subprocess.run(cmd, check=True)
    print(f"\nTRAIN DONE in {round(time.time() - t0)}s")
    print(">>> find the fine-tuned checkpoint under the f5-tts ckpts dir for "
          f"'{DATASET}' and note its path for the sidecar (it is the .pt to load).")


if __name__ == "__main__":
    main()

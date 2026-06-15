# XTTS voice fine-tune - handoff for the M5

The goal: fine-tune XTTS on one speaker (65 min of public YouTube audio, the
English talker in `sources.txt`) and check whether the fine-tune beats zero-shot
cloning. We proved on a 16GB Mac that zero-shot f5 and zero-shot XTTS are both
"good but catchable." Fine-tuning is the next jump. It needs RAM and disk the
other machine did not have. The M5 (32GB, real disk) is where it gets a fair shot.

## The one prompt (paste into Claude Code on the M5, from the repo root)

> Pick up the prosodi voice fine-tune. Read `finetune/HANDOFF.md` and run it end to
> end: `cd finetune && ./setup.sh && ./run.sh`. The kit downloads the speaker audio,
> builds the training set, fine-tunes XTTS, and renders fine-tuned vs zero-shot for
> an A/B. FIRST, in phase 2, report the per-step time after ~20 steps and stop to
> tell me whether a full run is hours (worth it) or impractical (CPU fallback, needs
> cloud). Debug any dependency or API mismatch yourself using the notes in this file.
> Do not let the pinned versions float.

## What it does, phase by phase

1. `setup.sh` - builds `finetune/.env` with the versions that actually work together
   on Apple Silicon. The pins are load-bearing, do not bump them:
   - `torch==2.6.0` (2.9+ demands torchcodec and breaks coqui)
   - `transformers>=4.43,<5` (5.x removed `isin_mps_friendly`, which XTTS imports)
   - `coqui-tts`, `faster-whisper`, `pandas`, `yt-dlp`
2. `prepare.py` - downloads the `sources.txt` videos (audio only) and segments them
   into per-sentence clips with transcripts. Whisper is forced to int8/CPU because
   the coqui formatter hardcodes large-v2/float16, which dies off-CUDA.
3. `train.py` - the fine-tune. `COQUI_TOS_AGREED=1` and `PYTORCH_ENABLE_MPS_FALLBACK=1`
   are set. Config via env: `EPOCHS` (6), `BATCH` (3), `GRAD` (4). For a quick gauge:
   `EPOCHS=2 BATCH=2 .env/bin/python train.py`.
4. `infer_compare.py` - renders the same line through the fine-tuned model and
   zero-shot XTTS into `data/out/`. The A/B that answers the whole question.

## The decision point (do this before committing to a long run)

XTTS training is CUDA-first. On the M5 it runs on MPS (workable) or falls back to
CPU (slow). We never measured which, because the 16GB box ran out of disk first. So:
watch the first ~20 training steps. The trainer prints step time.
- A few seconds per step: a fine-tune is a few hours. Worth it, let it run.
- Tens of seconds per step: this is a CPU fallback. Stop. The real run belongs on a
  rented cloud GPU (the same scripts, a CUDA box, ~30 min and a few dollars).

## Known gotchas (so you do not rediscover them)

- coqui-tts does NOT pull torch on its own here, hence setup installs torch first.
- The formatter (`TTS/demos/xtts_ft_demo/utils/formatter.py`) needs `pandas` and
  uses `large-v2` float16 - patched to int8/CPU in `prepare.py`.
- `train_gpt`'s return tuple order is version-specific. `train.py` saves it to
  `data/train_result.txt`. `infer_compare.py` searches the run dir for
  `best_model.pth` / `config.json` / `vocab.json`; if it misfinds, set `CKPT`,
  `CONFIG`, `VOCAB` env vars from `train_result.txt`.
- ~65 min of audio transcribes slowly on CPU. To gauge faster, trim `sources.txt`
  to 1-2 ids for the first run.

## If the fine-tune wins

Fold it back into the app: add an `XTTSBackend` to `prosodi/backends.py` that loads
this checkpoint (it stays a separate, heavy, torch-based backend - keep it out of the
MLX core, invoke it as a sidecar). Then `web` Reconstruct can render f5 vs the
fine-tuned XTTS side by side. That is the multi-model comparison Alex asked for, now
with a model that is actually his speaker.

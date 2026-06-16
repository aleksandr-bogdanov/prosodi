# prosodi finetune-f5 session handoff

Repo: `github.com/aleksandr-bogdanov/prosodi` (local mirror at `~/IdeaProjects/prosodi`)

---

## What this is

Fine-tuning F5-TTS on one speaker so prosodi's default engine gets a speaker-specific voice while
keeping its per-clause duration control. F5 has a real `fix_duration` arg that XTTS lacks, so the
fine-tune doesn't cost us prosody control - that's the whole reason to use it over XTTS.

Full context: `finetune-f5/HANDOFF.md` in the repo.

---

## What was done on the M5 (this session)

### 1. Setup

```bash
cd ~/IdeaProjects/prosodi/finetune-f5
bash setup.sh
```

Installed successfully:
- Python 3.12 venv at `finetune-f5/.env`
- torch 2.6.0, torchaudio 2.6.0 (MPS available)
- f5-tts 1.1.20, faster-whisper, yt-dlp, soundfile, pandas

`torchcodec` got pulled in by f5-tts but torch stayed at 2.6.0 (safe).

### 2. Bugs found and fixed in the repo scripts

**prepare.py - three bugs fixed:**

1. CSV needed an `audio_file|text` header row - the installed `prepare_csv_wavs` strictly requires it
   and raises `ValueError: CSV header must be: audio_file|text` without it.

2. Wav paths in the CSV must be absolute. Was writing relative `wavs/clip_XXXXXX.wav`,
   `prepare_csv_wavs` raises `ValueError: audio_file must be an absolute path`. Fixed to
   `str(clip.resolve())`.

3. `build_dataset()` was passing the clips directory as the first arg to `prepare_csv_wavs` but it
   expects the CSV file path. Fixed to pass `str(meta)` (the CSV file).

4. `out_dir` for `prepare_csv_wavs` must match where `load_dataset("prosodi_speaker")` looks at
   train time: `<f5_tts package>/../../data/prosodi_speaker_pinyin/`. This resolves to
   `.env/lib/python3.12/data/prosodi_speaker_pinyin/` (note: NOT `site-packages/data/`). Fixed to
   compute it from `pkg_files("f5_tts").joinpath("../../data/prosodi_speaker_pinyin")`.

**Extra: missing vocab file**

`prepare_csv_wavs` asserts `Emilia_ZH_EN_pinyin/vocab.txt` exists before building a finetune
dataset. This file is NOT in the pip install. Fix: copy it from the bundled examples:

```bash
mkdir -p .env/lib/python3.12/data/Emilia_ZH_EN_pinyin
cp .env/lib/python3.12/site-packages/f5_tts/infer/examples/vocab.txt \
   .env/lib/python3.12/data/Emilia_ZH_EN_pinyin/vocab.txt
```

**train.py - two fixes:**

1. Added `--exp_name F5TTS_v1_Base` explicitly (the default but important to be precise - other
   options are `F5TTS_Base` and `E2TTS_Base` which download different checkpoints).

2. Added `--keep_last_n_checkpoints 3` (default is -1 = keep all, which fills disk).

3. `--logger None` does NOT work - argparse choices are `{None, wandb, tensorboard}` where `None` is
   Python None, not the string `"None"`. Just omit the flag entirely; the default is no logger.

### 3. Data preparation - DONE

All 6 YouTube videos from `sources.txt` downloaded and transcribed:

```
finetune-f5/data/audio/   - 6 WAV files (~65 min total)
finetune-f5/data/clips/   - 691 sentence clips + metadata.csv
```

Arrow dataset built and ready at:
```
.env/lib/python3.12/data/prosodi_speaker_pinyin/
  raw.arrow
  duration.json
  vocab.txt
```

Stats: 691 clips, 0.92 hours, 67 unique vocab tokens (English only).

### 4. Training - KILLED, go cloud

Started training and watched the first 11 steps. Step times:

| Step | Actual time |
|------|-------------|
| 1    | 19s         |
| 2    | 8s          |
| 3    | 3s          |
| 4    | 4s          |
| 5    | 4s          |
| 6    | 41s (spike) |
| 7    | 55s         |
| 8    | 51s         |
| 9    | 85s         |
| 10   | 8s          |
| 11   | 6s          |

Rolling average at step 11: ~28s/update. Some op in the flow matching / attention path hits CPU
fallback every few batches on MPS - the pattern is a few fast steps, then a multi-minute spike.
The tqdm ETA projected ~52 min/epoch x 10 epochs = ~9 hours. That's the "go cloud" zone per
HANDOFF.md ("a few seconds per step = worth it, tens = CPU fallback, go cloud").

The base F5TTS_v1_Base checkpoint was downloaded from HF during the brief run and is cached at
`~/.cache/cached_path/` on the M5.

---

## How to resume on a cloud instance (Linux/CUDA)

### What to transfer from the M5

The audio files and Arrow dataset are the expensive parts. The venv rebuilds fast on cloud.

```bash
# From the M5, rsync the data to the cloud box
rsync -av ~/IdeaProjects/prosodi/finetune-f5/data/ <cloud>:~/prosodi/finetune-f5/data/
rsync -av ~/IdeaProjects/prosodi/finetune-f5/.env/lib/python3.12/data/ \
      <cloud>:~/prosodi/finetune-f5/.env-data/
```

Or just re-run `prepare.py` on cloud - it's idempotent (skips already-downloaded audio), and
Whisper on a GPU is much faster than CPU int8 on M5.

### Cloud setup

```bash
git clone https://github.com/aleksandr-bogdanov/prosodi.git
cd prosodi/finetune-f5
bash setup.sh   # builds .env with torch + f5-tts
```

Then fix the vocab file (same step as above):
```bash
mkdir -p .env/lib/python3.12/data/Emilia_ZH_EN_pinyin
cp .env/lib/python3.12/site-packages/f5_tts/infer/examples/vocab.txt \
   .env/lib/python3.12/data/Emilia_ZH_EN_pinyin/vocab.txt
```

If you synced the dataset from M5, put it at:
```
.env/lib/python3.12/data/prosodi_speaker_pinyin/
```

If re-running prepare.py on cloud, it will land there automatically.

### Run training

```bash
.env/bin/python prepare.py    # skip if you synced the dataset
.env/bin/python train.py
```

Watch the first ~20 steps. On an A10G or better, expect 1-3s/step. The full 10 epochs
(~1110 updates) should finish in under an hour.

The base checkpoint auto-downloads from HuggingFace on first run:
`hf://SWivid/F5-TTS/F5TTS_v1_Base/model_1250000.safetensors`

Fine-tuned checkpoints write to:
`.env/lib/python3.12/ckpts/prosodi_speaker/`

---

## What's left after training

Per HANDOFF.md:

1. **Verify duration control before declaring success.** Render the same text at two target durations
   and check the output audio lengths actually differ. If `fix_duration` doesn't survive the
   fine-tune, that's a blocking finding.

2. **Build `f5_sidecar.py`** - a warm torch process (loads the fine-tuned .pt checkpoint once,
   renders clause texts at target durations via the PyTorch F5-TTS inference API). Mirror the
   pattern from `finetune/xtts_server.py`. The sidecar must honor duration - that's what makes
   prosodi's tempo control work.

3. **Build `infer_compare.py`** - A/B render: fine-tuned-f5 vs zero-shot-f5 (MLX) on a held-out
   clip. Listen: should sound more like the speaker while keeping pauses and tempo.

4. If the A/B wins: add `F5FinetunedBackend` to `prosodi/backends.py` mirroring `XTTSBackend`,
   wire it into the web Reconstruct UI for side-by-side comparison.

---

## Key paths (all relative to `finetune-f5/`)

```
.env/                                          python venv
data/audio/                                    source WAVs (6 files)
data/clips/wavs/                               691 sentence clips
data/clips/metadata.csv                        audio_file|text CSV
.env/lib/python3.12/data/prosodi_speaker_pinyin/  Arrow dataset (training input)
.env/lib/python3.12/data/Emilia_ZH_EN_pinyin/vocab.txt  required vocab
.env/lib/python3.12/ckpts/prosodi_speaker/     training checkpoints (after training)
```

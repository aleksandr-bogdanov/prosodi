# f5 voice fine-tune - handoff for the M5

The goal: fine-tune F5-TTS on one speaker so prosodi's default engine keeps its
strong prosody control AND gets a voice that sounds like the person. This is the
sequel to the XTTS run. Read `finetune/RESULTS.md` and the bake-off writeup
(`../bogdanov-wtf/docs/drafts/2026-06-12-prosodi-voice-to-text-and-back/finetune-bakeoff.md`)
for why we are fine-tuning f5 and not XTTS: f5 has a real duration handle, so unlike
XTTS the fine-tune does not cost us prosody control.

Same speaker as the XTTS run (`sources.txt`, ~65 min of public YouTube audio). The
XTTS kit (`../finetune/`) is the proven template; this mirrors it with F5-TTS in
place of coqui.

## UPDATE: the M5 already ran this (see RESULTS-M5.md)

A first run happened on the M5. The data prep works (691 clips, 0.92 h, Arrow
dataset built) and the script bugs it found are now fixed in `prepare.py` and
`train.py` (CSV header + absolute paths + the f5 data-dir location + the Emilia
vocab copy + the right base checkpoint). What it learned: F5-TTS training on the M5
is ~28 s/update with MPS CPU-fallback spikes (a few fast steps, then a multi-minute
spike), projecting ~9 hours. That is the go-cloud zone. So the run belongs on a
cloud GPU. `RESULTS-M5.md` has the exact step times and a cloud-resume recipe
(rsync the dataset over, or just re-run `prepare.py` on the box). On an A10G or
better, the full run should finish in under an hour.

## The one prompt (paste into Claude Code on the M5, from the repo root)

> Pick up the prosodi f5 voice fine-tune. Read `finetune-f5/HANDOFF.md` and run it
> end to end: `cd finetune-f5 && ./setup.sh && ./run.sh`. It downloads the speaker
> audio, builds an F5-TTS dataset, fine-tunes f5, and renders fine-tuned-f5 vs
> zero-shot-f5 for an A/B. F5-TTS's Python API and CLI flags shift between versions,
> so verify the exact dataset-prep and finetune-cli calls against the installed
> package and adjust the scripts. In training, report the per-step time after ~20
> steps and stop to tell me hours-vs-impractical. The crucial integration piece is
> `f5_sidecar.py`: it must render each clause with a TARGET DURATION (f5 supports
> this - it is what makes prosodi's tempo control work), so confirm the duration arg
> is honored before declaring success.

## Why a torch sidecar, not an MLX conversion

prosodi runs the MLX port of f5 (`f5-tts-mlx`) for fast zero-shot cloning. The
fine-tune produces a PyTorch checkpoint. Rather than convert weights (fragile, the
state-dict names differ), run the fine-tuned f5 as a torch sidecar, the same warm-
process pattern the XTTS comparison already uses (`finetune/xtts_server.py`). The
one thing that must carry over: per-clause duration control. The MLX `F5Backend`
calls the model with a frame budget per clause; the PyTorch F5-TTS model exposes the
same (a `fix_duration` / duration argument on its sample/infer path). If the sidecar
honors duration, the fine-tuned f5 keeps prosodi's pause and tempo fidelity, which is
the entire reason to prefer f5. Verify this first.

## Phases

1. `setup.sh` - build `finetune-f5/.env`. F5-TTS is heavy (torch). Likely pins, to
   confirm on the M5 (the XTTS run showed torch 2.6 + transformers <5 worked on
   Apple Silicon; F5-TTS may want its own range):
   - `f5-tts` (the SWivid package; provides `f5-tts_finetune-cli`, `f5-tts_infer-cli`,
     `prepare_csv_wavs`, and the `f5_tts.api.F5TTS` class)
   - `torch` / `torchaudio` (start at 2.6, bump only if F5-TTS demands it)
   - `yt-dlp`, `soundfile`, `pandas`
   PYTORCH_ENABLE_MPS_FALLBACK=1 for the unsupported ops, as with XTTS.
2. `prepare.py` - download `sources.txt`, segment + transcribe into the F5-TTS
   dataset layout (`wavs/` + `metadata.csv` of `audio|text`), then run
   `prepare_csv_wavs` to build the Arrow dataset under a dataset name. The XTTS kit's
   int8-CPU whisper trick applies for the transcription.
3. `train.py` - `f5-tts_finetune-cli --finetune --dataset_name <name> ...` from the
   downloaded base F5-TTS checkpoint. Small-dataset guidance (SWivid discussion #769):
   modest learning rate, a few thousand updates for ~1 hr of audio, watch eval.
4. `f5_sidecar.py` + `infer_compare.py` - the warm torch sidecar (loads the fine-tuned
   ckpt once, renders clause texts at target durations) and an A/B that renders
   fine-tuned-f5 vs zero-shot-f5 (the MLX one, or zero-shot torch f5) on a held-out
   clip. Listen: the fine-tune should sound more like the speaker while keeping the
   pauses and tempo on point.

## The integration, once it wins

Add an `F5FinetunedBackend` to `prosodi/backends.py` that talks to `f5_sidecar.py`
(mirror `XTTSBackend`, but the sidecar honors per-clause duration so NO post-hoc
time-stretch lurching). Then `web` Reconstruct shows zero-shot f5 vs fine-tuned f5
side by side - the comparison that should finally clear the "catchable" bar, because
both have the prosody right and only the voice differs.

## Known unknowns (the M5 agent should expect to debug)

- F5-TTS entry-point names and CLI flags drift across releases. Check
  `f5-tts_finetune-cli --help` and the installed `f5_tts` package before trusting the
  script flags.
- The base-checkpoint download path and the fine-tuned-checkpoint output path are
  version-specific. `train.py` should print where it wrote the checkpoint.
- Confirm the duration argument on the inference path is actually honored (render the
  same text at two target durations, check the output lengths differ). If f5's
  duration control does not survive the fine-tune, that is a real finding, log it.
- Apple Silicon: training on MPS, same step-time gauge as XTTS (a few seconds per
  step = worth it, tens = CPU fallback, go cloud).

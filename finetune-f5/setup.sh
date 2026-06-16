#!/usr/bin/env bash
# Build the isolated F5-TTS fine-tune environment.
#
# Pins are a starting point from the XTTS run (torch 2.6 + the transformers <5 range
# worked on Apple Silicon). F5-TTS may pull its own versions; if the import check
# fails, read the error and adjust, but do not let torch float up to 2.9+ (it demands
# torchcodec and breaks the audio stack, the XTTS lesson).
set -euo pipefail
HERE="$(cd "$(dirname "$0")" && pwd)"
ENV="${HERE}/.env"

command -v ffmpeg >/dev/null 2>&1 || { echo "ffmpeg missing: brew install ffmpeg"; exit 1; }

echo ">>> creating env at ${ENV}"
uv venv "${ENV}" --python 3.12

echo ">>> installing torch first, then F5-TTS"
uv pip install --python "${ENV}" "torch==2.6.0" "torchaudio==2.6.0"
uv pip install --python "${ENV}" f5-tts faster-whisper pandas yt-dlp soundfile

echo ">>> sanity check"
"${ENV}/bin/python" - <<'PY'
import torch
from f5_tts.api import F5TTS  # noqa: F401
print("torch", torch.__version__, "| mps:", torch.backends.mps.is_available())
print("f5-tts import OK")
PY
echo ">>> setup done. next: ./run.sh   (verify f5-tts_finetune-cli --help first)"

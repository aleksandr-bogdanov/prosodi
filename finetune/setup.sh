#!/usr/bin/env bash
# Build the isolated XTTS fine-tune environment. These versions are the ones that
# actually work together on Apple Silicon as of 2026-06; do not let them float.
#
# The pins matter (learned the hard way):
#   torch 2.6        - newer torch (2.9+) demands torchcodec for audio IO, breaks coqui
#   transformers <5  - 5.x removed isin_mps_friendly, which XTTS imports
#   coqui-tts        - the maintained Coqui fork (provides the `TTS` module + XTTS)
#   faster-whisper   - the dataset formatter transcribes with it
#   pandas           - the formatter writes the metadata CSVs with it
set -euo pipefail
HERE="$(cd "$(dirname "$0")" && pwd)"
ENV="${HERE}/.env"

echo ">>> creating env at ${ENV}"
uv venv "${ENV}" --python 3.12

echo ">>> installing pinned deps (torch first, so coqui does not pull a too-new one)"
uv pip install --python "${ENV}" "torch==2.6.0" "torchaudio==2.6.0"
uv pip install --python "${ENV}" "transformers>=4.43,<5"
uv pip install --python "${ENV}" coqui-tts faster-whisper pandas yt-dlp

echo ">>> sanity check"
"${ENV}/bin/python" - <<'PY'
import torch
from TTS.api import TTS  # noqa: F401
print("torch", torch.__version__, "| mps:", torch.backends.mps.is_available())
print("coqui-tts import OK")
PY
echo ">>> setup done. next: ./run.sh"

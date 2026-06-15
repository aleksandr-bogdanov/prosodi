#!/usr/bin/env bash
# Run the three phases end to end. Setup must have run first (./setup.sh).
set -euo pipefail
HERE="$(cd "$(dirname "$0")" && pwd)"
PY="${HERE}/.env/bin/python"
[ -x "${PY}" ] || { echo "run ./setup.sh first (no env at ${HERE}/.env)"; exit 1; }

echo ">>> phase 1: download + dataset"
"${PY}" "${HERE}/prepare.py"
echo ">>> phase 2: fine-tune  (WATCH THE FIRST STEPS for step time)"
"${PY}" "${HERE}/train.py"
echo ">>> phase 3: compare fine-tuned vs zero-shot"
"${PY}" "${HERE}/infer_compare.py"
echo ">>> done. A/B: finetune/data/out/finetuned.wav vs zeroshot.wav"

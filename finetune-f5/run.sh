#!/usr/bin/env bash
# Phases 1-2 end to end. Setup must have run first (./setup.sh).
# Phase 3 (the f5 torch sidecar + the A/B) is built on the M5 once training works,
# per HANDOFF.md - it needs the F5-TTS inference API verified against the install.
set -euo pipefail
HERE="$(cd "$(dirname "$0")" && pwd)"
PY="${HERE}/.env/bin/python"
[ -x "${PY}" ] || { echo "run ./setup.sh first (no env at ${HERE}/.env)"; exit 1; }

echo ">>> phase 1: download + dataset"
"${PY}" "${HERE}/prepare.py"
echo ">>> phase 2: fine-tune  (WATCH THE FIRST STEPS for step time)"
"${PY}" "${HERE}/train.py"
echo ">>> training done. Next, per HANDOFF.md: build f5_sidecar.py (warm torch f5,"
echo "    honoring per-clause target duration) + infer_compare.py, then A/B"
echo "    fine-tuned-f5 vs zero-shot-f5 and listen."

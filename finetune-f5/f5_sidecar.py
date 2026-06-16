"""Warm F5-TTS sidecar: load the fine-tuned checkpoint ONCE, serve renders over localhost.

Mirrors finetune/xtts_server.py. The fine-tuned f5 checkpoint loads in a few seconds;
this keeps it hot in a long-running process so the web app renders clauses in real time.

The whole reason prosodi prefers f5 over XTTS is per-clause DURATION control. The torch
F5TTS.infer() exposes fix_duration (total seconds = reference audio + generated speech),
the same handle the MLX F5Backend drives as `duration` frames. So a clause rendered with
a target duration comes out at that length - that is what makes prosodi's tempo/pause
fidelity survive the fine-tune. Verify it (see infer_compare.py --verify) before trusting it.

    finetune-f5/.env/bin/python finetune-f5/f5_sidecar.py [port]   # default 8798

GET  /  -> {"ok": true} once the model is loaded (health)
POST / {texts:[...], durations:[...|null], out_dir, speed?} -> {"clips": [paths]}
        durations[i] (seconds) imposes clause i's generated speech length; null = natural.
"""

import json
import os
import sys
from http.server import BaseHTTPRequestHandler, HTTPServer
from pathlib import Path

HERE = Path(__file__).resolve().parent
SAMPLE_RATE = 24_000
MIN_CLAUSE_S = 0.4           # same floor the MLX F5Backend imposes

STATE = None  # (model, ref_file, ref_text, ref_seconds) once loaded


def _venv_root() -> Path:
    # .env/lib/pythonX.Y -> the dirs prepare.py wrote the dataset + ckpts under
    import f5_tts
    return Path(list(f5_tts.__path__)[0]).resolve().parent.parent


def find_finetuned_ckpt() -> Path:
    """Newest fine-tuned checkpoint, skipping the copied base (pretrained_*)."""
    root = Path(os.environ.get("CKPT_DIR") or (_venv_root() / "ckpts" / "prosodi_speaker"))
    cands = [p for p in root.rglob("model_*.pt") if "pretrained" not in p.name]
    if not cands:
        cands = [p for p in root.rglob("*.safetensors") if "pretrained" not in p.name]
    if not cands:
        raise SystemExit(f"no fine-tuned checkpoint under {root} (set CKPT_DIR)")
    # model_last.pt wins if present, else newest by mtime
    last = [p for p in cands if p.name == "model_last.pt"]
    return last[0] if last else max(cands, key=lambda p: p.stat().st_mtime)


def find_vocab() -> Path:
    v = os.environ.get("VOCAB_FILE")
    if v:
        return Path(v)
    # the 2545-token pinyin vocab the finetune trained against
    return _venv_root() / "data" / "prosodi_speaker_pinyin" / "vocab.txt"


def pick_reference() -> tuple[str, str]:
    """A clean 4-10 s speaker clip + its transcript, from the dataset metadata."""
    import csv
    import soundfile as sf
    if os.environ.get("REF_WAV") and os.environ.get("REF_TEXT"):
        return os.environ["REF_WAV"], os.environ["REF_TEXT"]
    meta = HERE / "data" / "clips" / "metadata.csv"
    best = None  # (dur, wav, text)
    with meta.open(encoding="utf-8") as f:
        r = csv.reader(f, delimiter="|")
        next(r, None)  # header
        for row in r:
            if len(row) < 2:
                continue
            wav, text = row[0], row[1]
            try:
                d = sf.info(wav).duration
            except Exception:
                continue
            if 4.0 <= d <= 10.0 and (best is None or d > best[0]):
                best = (d, wav, text)
    if best is None:
        raise SystemExit("no 4-10 s reference clip found in data/clips/metadata.csv")
    return best[1], best[2]


def load_model():
    import soundfile as sf
    from f5_tts.api import F5TTS

    ckpt = find_finetuned_ckpt()
    vocab = find_vocab()
    ref_file, ref_text = pick_reference()
    ref_seconds = sf.info(ref_file).duration
    print(f"f5 sidecar: ckpt {ckpt}", flush=True)
    print(f"f5 sidecar: vocab {vocab}", flush=True)
    print(f"f5 sidecar: ref {Path(ref_file).name} ({ref_seconds:.1f}s) '{ref_text[:50]}'",
          flush=True)
    try:
        model = F5TTS(model="F5TTS_v1_Base", ckpt_file=str(ckpt),
                      vocab_file=str(vocab), device="cuda")
    except TypeError:
        # older f5-tts used model_type= instead of model=
        model = F5TTS(model_type="F5TTS_v1_Base", ckpt_file=str(ckpt),
                      vocab_file=str(vocab), device="cuda")
    return model, ref_file, ref_text, ref_seconds


def render_one(text: str, duration_s, speed: float):
    """Render text in the fine-tuned voice. duration_s (s) imposes the generated
    length via fix_duration (total = ref + gen); None lets f5 pick a natural tempo."""
    import numpy as np
    model, ref_file, ref_text, ref_seconds = STATE
    fix_duration = None
    if duration_s is not None:
        fix_duration = ref_seconds + max(float(duration_s), MIN_CLAUSE_S)
    wav, sr, _ = model.infer(
        ref_file=ref_file, ref_text=ref_text, gen_text=text,
        fix_duration=fix_duration, speed=speed, nfe_step=32,
        remove_silence=False, show_info=lambda *a, **k: None,
    )
    return np.asarray(wav, dtype=np.float32), sr


class Handler(BaseHTTPRequestHandler):
    def log_message(self, *a):
        pass

    def _json(self, code, obj):
        body = json.dumps(obj).encode()
        self.send_response(code)
        self.send_header("Content-Type", "application/json")
        self.send_header("Content-Length", str(len(body)))
        self.end_headers()
        self.wfile.write(body)

    def do_GET(self):
        self._json(200 if STATE else 503, {"ok": STATE is not None})

    def do_POST(self):
        import soundfile as sf
        n = int(self.headers.get("Content-Length", 0))
        req = json.loads(self.rfile.read(n))
        out_dir = Path(req["out_dir"])
        out_dir.mkdir(parents=True, exist_ok=True)
        speed = float(req.get("speed", 1.0))
        texts = req["texts"]
        durations = req.get("durations") or [None] * len(texts)
        clips = []
        for i, text in enumerate(texts):
            wav, sr = render_one(text, durations[i], speed)
            p = out_dir / f"clip_{i}.wav"
            sf.write(str(p), wav, sr)
            clips.append(str(p))
        self._json(200, {"clips": clips})


def main():
    global STATE
    port = int(sys.argv[1]) if len(sys.argv) > 1 else 8798
    print("f5 sidecar: loading fine-tuned model...", flush=True)
    STATE = load_model()
    print(f"f5 sidecar: ready on 127.0.0.1:{port}", flush=True)
    HTTPServer(("127.0.0.1", port), Handler).serve_forever()


if __name__ == "__main__":
    main()

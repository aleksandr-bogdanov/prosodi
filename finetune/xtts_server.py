"""Warm XTTS sidecar: load the fine-tuned model ONCE, serve renders over localhost.

The fine-tuned checkpoint is ~5GB and takes ~60s to load. Reloading it per render
(the one-shot sidecar) is what made the web reconstruct feel like it hung. This
keeps the model hot in a long-running process and answers render requests in
seconds. Localhost-bind only.

    finetune/.env/bin/python finetune/xtts_server.py [port]   # default 8799

GET  /            -> {"ok": true} once the model is loaded (health)
POST / {texts:[...], out_dir} -> {"clips": [paths]}  renders each text to out_dir
"""

import json
import os
import sys
from http.server import BaseHTTPRequestHandler, HTTPServer
from pathlib import Path

os.environ.setdefault("COQUI_TOS_AGREED", "1")
os.environ.setdefault("PYTORCH_ENABLE_MPS_FALLBACK", "1")

HERE = Path(__file__).resolve().parent
MODEL = HERE / "restored-model"
REF = HERE / "data" / "dataset" / "wavs" / "reference.wav"

STATE = None  # (model, gpt_latent, speaker_embedding) once loaded


def load_model():
    from TTS.tts.configs.xtts_config import XttsConfig
    from TTS.tts.models.xtts import Xtts
    cfg = XttsConfig()
    cfg.load_json(str(MODEL / "config.json"))
    model = Xtts.init_from_config(cfg)
    model.load_checkpoint(cfg, checkpoint_path=str(MODEL / "best_model.pth"),
                          vocab_path=str(MODEL / "vocab.json"), use_deepspeed=False)
    lat, spk = model.get_conditioning_latents(audio_path=[str(REF)])
    return model, lat, spk


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
        model, lat, spk = STATE
        out_dir = Path(req["out_dir"])
        out_dir.mkdir(parents=True, exist_ok=True)
        speed = float(req.get("speed", 1.0))
        clips = []
        for i, text in enumerate(req["texts"]):
            out = model.inference(text, "en", lat, spk, temperature=0.7, speed=speed)
            p = out_dir / f"clip_{i}.wav"
            sf.write(str(p), out["wav"], 24000)
            clips.append(str(p))
        self._json(200, {"clips": clips})


def main():
    global STATE
    port = int(sys.argv[1]) if len(sys.argv) > 1 else 8799
    print("xtts server: loading model (~60s)...", flush=True)
    STATE = load_model()
    print(f"xtts server: ready on 127.0.0.1:{port}", flush=True)
    HTTPServer(("127.0.0.1", port), Handler).serve_forever()


if __name__ == "__main__":
    main()

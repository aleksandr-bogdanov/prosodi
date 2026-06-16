"""prosodi web server.

A local FastAPI app that drives the prosodi pipeline from a browser: analyze a
recording, hear it cloned back, and play the real-vs-clone guessing game. The
CLI lives underneath; the user never types it. Everything heavy runs as a job
(jobs.py) so the UI stays responsive while whisper/praat/f5 work.

Run:  uv run --group web --group synth python -m web.server.app
      (or: uv run prosodi serve)
"""

import json
import os
import shutil
import uuid
from datetime import datetime, timezone
from pathlib import Path

from fastapi import FastAPI, File, Form, HTTPException, UploadFile
from fastapi.middleware.cors import CORSMiddleware
from fastapi.staticfiles import StaticFiles

from . import pipeline, voices
from .audio import to_wav, to_wav16k
from .jobs import REGISTRY

WEB_ROOT = Path(__file__).resolve().parents[1]
WORK = WEB_ROOT / ".work"
EXAMPLES = WEB_ROOT / "data" / "examples"
DIST = WEB_ROOT / "app" / "dist"
WORK.mkdir(parents=True, exist_ok=True)

# In-memory stores (single-user local app, lost on restart, which is fine).
SESSIONS: dict[str, dict] = {}   # session_id -> {wav16k, record}
GAMES: dict[str, dict] = {}      # game_id -> {truth: {item_id: is_real}}

app = FastAPI(title="prosodi")
app.add_middleware(
    CORSMiddleware,
    allow_origins=["http://localhost:5173", "http://127.0.0.1:5173"],
    allow_methods=["*"], allow_headers=["*"],
)


def _save_upload(upload: UploadFile, dest_dir: Path) -> Path:
    dest_dir.mkdir(parents=True, exist_ok=True)
    raw = dest_dir / ("upload" + Path(upload.filename or "audio").suffix)
    with raw.open("wb") as f:
        shutil.copyfileobj(upload.file, f)
    return raw


def _media_url(path: Path) -> str:
    return "/media/" + str(path.relative_to(WORK))


# --- analyze -------------------------------------------------------------

@app.post("/api/analyze")
async def api_analyze(file: UploadFile = File(...),
                      use_profile: bool = Form(True)):
    sid = uuid.uuid4().hex[:12]
    sdir = WORK / sid
    raw = _save_upload(file, sdir)
    wav16k = to_wav16k(raw, sdir / "input.wav")

    def body(prog):
        prog.set(0.2, "transcribing + measuring acoustics")
        record = pipeline.analyze(wav16k, use_profile=use_profile)
        SESSIONS[sid] = {"wav16k": wav16k, "record": record}
        prog.set(0.95, "building the annotation")
        view = pipeline.record_to_view(record)
        return {"session_id": sid, "view": view,
                "audio_url": _media_url(wav16k)}

    job_id = REGISTRY.submit("analyze", body)
    return {"job_id": job_id}


# --- roundtrip (hear it back) -------------------------------------------

@app.post("/api/roundtrip")
async def api_roundtrip(session_id: str = Form(...),
                        fit_tempo: bool = Form(True),
                        clause_min_pause_s: float = Form(0.4)):
    sess = SESSIONS.get(session_id)
    if not sess:
        raise HTTPException(404, "unknown session (analyze first)")
    sdir = WORK / session_id
    record, wav16k = sess["record"], sess["wav16k"]

    def body(prog):
        prog.set(0.1, "carving a reference voice clip")
        ref = pipeline.pick_ref_clip(wav16k, record, sdir / "ref.wav")
        prog.set(0.25, "cloning your voice (f5)")
        render = pipeline.clone_render(record, ref, sdir / "clone-prosody.wav",
                                       condition="prosody", fit_tempo=fit_tempo,
                                       clause_min_pause_s=clause_min_pause_s)
        prog.set(0.8, "scoring the render against the original")
        card = pipeline.verify(record, render, wav16k)
        return {"render_url": _media_url(render),
                "original_url": _media_url(wav16k),
                "scorecard": card}

    job_id = REGISTRY.submit("roundtrip", body)
    return {"job_id": job_id}


# --- the guessing game ---------------------------------------------------

@app.post("/api/game")
async def api_game(file: UploadFile | None = File(None),
                   session_id: str | None = Form(None),
                   n_clones: int = Form(4)):
    if session_id and session_id in SESSIONS:
        sess = SESSIONS[session_id]
        wav16k, record = sess["wav16k"], sess["record"]
        sdir = WORK / session_id
    elif file is not None:
        sid = uuid.uuid4().hex[:12]
        sdir = WORK / sid
        raw = _save_upload(file, sdir)
        wav16k = to_wav16k(raw, sdir / "input.wav")
        record = None
    else:
        raise HTTPException(400, "pass an uploaded file or a known session_id")

    def body(prog):
        nonlocal record
        if record is None:
            prog.set(0.05, "analyzing your read")
            record = pipeline.analyze(wav16k)
        gdir = sdir / "game"
        game = pipeline.build_game(wav16k, record, gdir,
                                   n_clones=n_clones, progress=prog)
        # Assign opaque ids first, then order by id so the human's slot is not
        # predictable (the id is random; the real item never lands in a fixed
        # position). The truth stays server-side until /reveal.
        items = game["items"]
        tagged = [(uuid.uuid4().hex[:8], it) for it in items]
        tagged.sort(key=lambda t: t[0])
        gid = uuid.uuid4().hex[:12]
        truth, public_items = {}, []
        for pos, (item_id, it) in enumerate(tagged):
            truth[item_id] = {"is_real": it["is_real"], "label": it["label"]}
            public_items.append({"id": item_id, "url": _media_url(it["file"]),
                                 "position": pos})
        GAMES[gid] = {"truth": truth}
        return {"game_id": gid, "items": public_items,
                "target_text": game["target_text"], "view": game["view"]}

    job_id = REGISTRY.submit("game", body)
    return {"job_id": job_id}


@app.get("/api/game/{game_id}/reveal")
async def api_reveal(game_id: str):
    g = GAMES.get(game_id)
    if not g:
        raise HTTPException(404, "unknown game")
    return {"truth": g["truth"]}


# --- voices (persisted) + reconstruct ------------------------------------

def _now() -> str:
    return datetime.now(timezone.utc).isoformat(timespec="seconds")


def _voice_public(v: dict) -> dict:
    return {**v, "ref_url": f"/voices/{v['id']}/ref.wav"}


@app.post("/api/voices")
async def api_create_voice(file: UploadFile = File(...), name: str = Form(""),
                          ref_start: float = Form(-1.0), ref_end: float = Form(-1.0)):
    """Train a voice. With a [ref_start, ref_end] region the user scrubbed, slice
    exactly that. Otherwise pull the best reference from the whole file."""
    tmp = WORK / ("voice-src-" + uuid.uuid4().hex[:8])
    raw = _save_upload(file, tmp)
    label = name or Path(file.filename or "voice").stem
    region = ref_end > ref_start >= 0

    def body(prog):
        prog.set(0.2, "reading the audio")
        hq = to_wav(raw, tmp / "full24.wav", 24000)
        if region:
            prog.set(0.4, "cutting your selection")
            ref = tmp / "ref.wav"
            pipeline.slice_to(hq, ref, ref_start, ref_end)
            ref_text = pipeline.transcribe_text(ref)
        else:
            prog.set(0.45, "finding the cleanest reference")
            wav16 = to_wav(raw, tmp / "full16.wav", 16000)
            record = pipeline.analyze(wav16, use_profile=False)
            ref, ref_text = pipeline.build_voice_ref(record, hq, tmp / "ref.wav")
        prog.set(0.85, "saving the voice")
        meta = voices.save_voice(label, ref, ref_text, file.filename or "", _now())
        shutil.rmtree(tmp, ignore_errors=True)
        return _voice_public(meta)

    return {"job_id": REGISTRY.submit("voice", body)}


@app.get("/api/voices")
async def api_list_voices():
    return {"voices": [_voice_public(v) for v in voices.list_voices()]}


@app.delete("/api/voices/{voice_id}")
async def api_delete_voice(voice_id: str):
    return {"deleted": voices.delete_voice(voice_id)}


@app.post("/api/reconstruct")
async def api_reconstruct(file: UploadFile = File(...), voice_id: str = Form(...),
                          fit_tempo: bool = Form(True),
                          clause_min_pause_s: float = Form(0.3)):
    """Annotate a clip and rebuild it in a saved voice, original vs reconstructed."""
    v = voices.get_voice(voice_id)
    if not v:
        raise HTTPException(404, "unknown voice (create one first)")
    sid = uuid.uuid4().hex[:12]
    sdir = WORK / sid
    raw = _save_upload(file, sdir)

    def body(prog):
        prog.set(0.15, "measuring the prosody")
        wav16 = to_wav(raw, sdir / "input16.wav", 16000)
        orig24 = to_wav(raw, sdir / "original.wav", 24000)
        record = pipeline.analyze(wav16, use_profile=False)
        models = []

        prog.set(0.35, f"f5 zero-shot clone in {v['name']}'s voice")
        f5 = pipeline.clone_render(
            record, voices.ref_path(voice_id), sdir / "f5.wav",
            condition="prosody", fit_tempo=fit_tempo,
            clause_min_pause_s=clause_min_pause_s, ref_text=v["ref_text"])
        models.append({"name": f"f5 zero-shot · {v['name']}",
                       "render_url": _media_url(f5),
                       "scorecard": pipeline.verify(record, f5, orig24)})

        # the fine-tuned XTTS is dropped from the default comparison: it learned the
        # voice but cannot be paced to the prosody (see the bake-off writeup). Kept
        # behind a flag for reference, and the f5 fine-tune will take its slot.
        if os.environ.get("PROSODI_COMPARE_XTTS") and pipeline.xtts_available():
            prog.set(0.6, "fine-tuned XTTS (torch sidecar, loads a 5GB model)")
            xt = pipeline.xtts_render(record, sdir / "xtts.wav", fit_tempo=fit_tempo,
                                      clause_min_pause_s=clause_min_pause_s)
            models.append({"name": "fine-tuned XTTS",
                           "render_url": _media_url(xt),
                           "scorecard": pipeline.verify(record, xt, orig24)})

        prog.set(0.92, "done")
        return {"original_url": _media_url(orig24),
                "view": pipeline.record_to_view(record),
                "models": models, "voice": _voice_public(v)}

    return {"job_id": REGISTRY.submit("reconstruct", body)}


# --- jobs + examples -----------------------------------------------------

@app.get("/api/jobs/{job_id}")
async def api_job(job_id: str):
    job = REGISTRY.get(job_id)
    if not job:
        raise HTTPException(404, "unknown job")
    return job.public()


@app.get("/api/examples")
async def api_examples():
    manifest = EXAMPLES / "manifest.json"
    if not manifest.exists():
        return {"galleries": [], "game": None}
    return json.loads(manifest.read_text(encoding="utf-8"))


@app.get("/api/health")
async def api_health():
    from .audio import FFMPEG
    return {"ok": True, "ffmpeg": FFMPEG is not None}


# --- static --------------------------------------------------------------

voices.VOICES_DIR.mkdir(parents=True, exist_ok=True)
app.mount("/media", StaticFiles(directory=WORK), name="media")
app.mount("/voices", StaticFiles(directory=voices.VOICES_DIR), name="voices")
if EXAMPLES.exists():
    app.mount("/examples", StaticFiles(directory=EXAMPLES), name="examples")
if DIST.exists():
    app.mount("/", StaticFiles(directory=DIST, html=True), name="app")


def main() -> None:
    import uvicorn
    uvicorn.run(app, host="127.0.0.1", port=8000, log_level="info")


if __name__ == "__main__":
    main()

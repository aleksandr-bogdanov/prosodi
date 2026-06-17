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
        prog.set(0.95, "building the annotation")
        view = pipeline.record_to_view(record)
        # keep the notation too: Reconstruct uses the precise record when the
        # notation comes back unedited, and parses it when the user has edited it.
        SESSIONS[sid] = {"wav16k": wav16k, "record": record,
                         "notation": view.get("notation", "")}
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
    # cache-bust ref_url by the file's mtime so a re-cut reference actually reloads
    # in the browser (the path is unchanged, only the bytes are).
    ref = voices.ref_path(v["id"])
    rev = int(ref.stat().st_mtime) if ref.exists() else 0
    d = {**v, "ref_url": f"/voices/{v['id']}/ref.wav?t={rev}"}
    if voices.source_path(v["id"]).exists():
        d["source_url"] = f"/voices/{v['id']}/source.wav"
    return d


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
        meta = voices.save_voice(label, ref, ref_text, file.filename or "", _now(),
                                 source_audio=hq)
        shutil.rmtree(tmp, ignore_errors=True)
        return _voice_public(meta)

    return {"job_id": REGISTRY.submit("voice", body)}


@app.post("/api/voices/{voice_id}/reref")
async def api_reref(voice_id: str, ref_start: float = Form(...),
                    ref_end: float = Form(...)):
    """Re-cut a saved voice's reference from its stored source (the scrubber)."""
    v = voices.get_voice(voice_id)
    if not v:
        raise HTTPException(404, "unknown voice")
    src = voices.source_path(voice_id)
    if not src.exists():
        raise HTTPException(400, "this voice has no stored source to re-cut from "
                                 "(re-create it to enable editing the reference)")

    def body(prog):
        tmp = WORK / ("reref-" + uuid.uuid4().hex[:8])
        tmp.mkdir(parents=True, exist_ok=True)
        prog.set(0.3, "cutting the new reference")
        ref = tmp / "ref.wav"
        pipeline.slice_to(src, ref, ref_start, ref_end)
        prog.set(0.65, "transcribing the reference")
        ref_text = pipeline.transcribe_text(ref)
        meta = voices.set_reference(voice_id, ref, ref_text)
        shutil.rmtree(tmp, ignore_errors=True)
        return _voice_public(meta)

    return {"job_id": REGISTRY.submit("reref", body)}


@app.get("/api/voices")
async def api_list_voices():
    return {"voices": [_voice_public(v) for v in voices.list_voices()]}


@app.delete("/api/voices/{voice_id}")
async def api_delete_voice(voice_id: str):
    return {"deleted": voices.delete_voice(voice_id)}


@app.post("/api/reconstruct")
async def api_reconstruct(notation: str = Form(...), voice_id: str = Form(...),
                          session_id: str | None = Form(None),
                          fit_tempo: bool = Form(True),
                          clause_min_pause_s: float = Form(0.4),
                          pitch_st: float = Form(0.0),
                          render_zeroshot: bool = Form(True),
                          render_finetuned: bool = Form(False)):
    """Render prosodi notation in a saved voice.

    The notation may be typed by hand or carried (and optionally edited) from a
    Capture. When it is the unedited notation of a capture session, the precise
    measured record is rendered; an edit or typed text is parsed from the notation
    (synthesized timing). With a session, each render is scored against the captured
    original; typed-only renders have no original, so no scorecard.
    """
    from prosodi.notation import has_timing_markers, parse_notation
    v = voices.get_voice(voice_id)
    if not v:
        raise HTTPException(404, "unknown voice (create one first)")
    sess = SESSIONS.get(session_id) if session_id else None
    sid = uuid.uuid4().hex[:12]
    sdir = WORK / sid

    def body(prog):
        prog.set(0.12, "reading the notation")
        if sess and notation.strip() == (sess.get("notation") or "").strip():
            record, condition = sess["record"], "prosody"   # unedited: precise record
            orig = sess["wav16k"]                            # score against the capture
        else:
            record = parse_notation(notation)
            condition = "prosody" if has_timing_markers(notation) else "control"
            # a parsed/edited spec has no measured acoustics, so it cannot be scored
            # against the original (verify needs the measured tempo/f0 fields).
            orig = None
        sdir.mkdir(parents=True, exist_ok=True)
        models = []

        def finalize(rendered):
            # score the prosody realization BEFORE transposing, then shift the base
            # pitch for playback (duration, and so the timing, is preserved)
            card = pipeline.verify(record, rendered, orig) if orig else None
            pipeline.shift_pitch(rendered, pitch_st)
            return card

        if render_zeroshot:
            prog.set(0.3, f"f5 zero-shot in {v['name']}'s voice")
            f5 = pipeline.clone_render(
                record, voices.ref_path(voice_id), sdir / "f5.wav",
                condition=condition, fit_tempo=fit_tempo,
                clause_min_pause_s=clause_min_pause_s, ref_text=v["ref_text"])
            models.append({"name": f"f5 zero-shot · {v['name']}",
                           "render_url": _media_url(f5), "scorecard": finalize(f5)})

        # The fine-tuned f5 is opt-in (checkbox, default off): the public-YouTube fine-tune
        # proved a voice tune keeps f5's duration handle but is lo-fi from lossy training
        # data and loses to zero-shot. Kept for the clean-data run; checking it loads a
        # second model, so leaving it off keeps render memory to one model.
        if render_finetuned and pipeline.f5ft_available():
            prog.set(0.6, f"fine-tuned f5 in {v['name']}'s voice")
            f5ft = pipeline.f5ft_render(
                record, sdir / "f5ft.wav", voices.ref_path(voice_id), v["ref_text"],
                condition=condition, fit_tempo=fit_tempo,
                clause_min_pause_s=clause_min_pause_s)
            models.append({"name": f"f5 fine-tuned · {v['name']}",
                           "render_url": _media_url(f5ft), "scorecard": finalize(f5ft)})

        prog.set(0.92, "done")
        return {"original_url": _media_url(orig) if orig else None,
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
    return {"ok": True, "ffmpeg": FFMPEG is not None,
            "f5ft": pipeline.f5ft_available()}


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

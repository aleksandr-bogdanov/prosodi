"""Persisted voices.

A voice is a saved reference clip plus its transcript and a name. f5 is zero-shot,
so this IS the "trained model": the best ~12 s of clean speech pulled from a source
file, which f5 clones from. Saved under web/.voices/<id>/ so it survives restarts
and is reused across clips by the same person without re-reading.

Layout per voice:
    .voices/<id>/ref.wav     the reference clip (24 kHz, what f5 clones)
    .voices/<id>/meta.json   {id, name, ref_text, source, created, ref_s}
"""

import json
import uuid
from pathlib import Path

WEB_ROOT = Path(__file__).resolve().parents[1]
VOICES_DIR = WEB_ROOT / ".voices"


def _meta_path(vid: str) -> Path:
    return VOICES_DIR / vid / "meta.json"


def list_voices() -> list[dict]:
    """Every saved voice's metadata, newest first."""
    if not VOICES_DIR.exists():
        return []
    out = []
    for d in VOICES_DIR.iterdir():
        m = d / "meta.json"
        if m.is_file():
            out.append(json.loads(m.read_text(encoding="utf-8")))
    out.sort(key=lambda v: v.get("created", ""), reverse=True)
    return out


def get_voice(vid: str) -> dict | None:
    m = _meta_path(vid)
    if not m.is_file():
        return None
    return json.loads(m.read_text(encoding="utf-8"))


def ref_path(vid: str) -> Path:
    return VOICES_DIR / vid / "ref.wav"


def save_voice(name: str, ref_wav: Path, ref_text: str, source: str,
               created: str) -> dict:
    """Persist a reference clip as a named voice. created is an ISO stamp the
    caller supplies (the script layer cannot read the clock)."""
    import shutil
    import soundfile as sf

    vid = uuid.uuid4().hex[:12]
    d = VOICES_DIR / vid
    d.mkdir(parents=True, exist_ok=True)
    dst = d / "ref.wav"
    shutil.copy(ref_wav, dst)
    meta = {
        "id": vid,
        "name": name.strip() or "untitled voice",
        "ref_text": ref_text,
        "source": source,
        "created": created,
        "ref_s": round(sf.info(str(dst)).duration, 2),
    }
    _meta_path(vid).write_text(json.dumps(meta, ensure_ascii=False, indent=1),
                               encoding="utf-8")
    return meta


def delete_voice(vid: str) -> bool:
    import shutil
    d = VOICES_DIR / vid
    if d.is_dir():
        shutil.rmtree(d)
        return True
    return False

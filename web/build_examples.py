"""Build the showcase: clean public-domain voices, cloned and scored.

Takes a handful of public-domain clips, finds a clean content window past the
spoken intro, runs the prosodi pipeline, clones the voice through f5, scores the
render, and writes web/data/examples/manifest.json plus a pre-baked guessing
game whose items are all the same length. The showcase page reads that manifest.

Run:  uv run --group web --group synth python web/build_examples.py
Sources are public-domain LibriVox readings (Short Poetry Collection 073).
"""

import json
import shutil
import subprocess
import sys
import uuid
from pathlib import Path

WEB = Path(__file__).resolve().parent
sys.path.insert(0, str(WEB.parent))

from web.server import pipeline  # noqa: E402

EXAMPLES = WEB / "data" / "examples"
SRC = Path("/tmp/pd")

GALLERIES = [
    {"id": "donne-dream", "title": "John Donne — The Dream",
     "source": "LibriVox · public domain", "file": "dream_donne_cc.mp3", "want_s": 15.0,
     "blurb": "A studio-clean reading. With clean input the clone lands close: "
              "register, pauses and the line-end falls all carry."},
    {"id": "lovecraft-city", "title": "H. P. Lovecraft — The City",
     "source": "LibriVox · public domain", "file": "city_lovecraft_kp.mp3", "want_s": 15.0,
     "blurb": "A different reader, a different voice. The notation is the same "
              "deterministic measure; only the speaker baseline changes."},
    {"id": "herbert-avarice", "title": "George Herbert — Avarice",
     "source": "LibriVox · public domain", "file": "avarice_herbert_mtd.mp3", "want_s": 14.0,
     "blurb": "Short and measured. Watch the stretch marks land on the drawled "
              "words and the pauses on the line breaks."},
]
GAME_FILE = "dream_donne_cc.mp3"
GAME_WANT_S = 11.0
GAME_N_CLONES = 4


def transcode(mp3: Path, sr: int, dst: Path,
              ss: float | None = None, dur: float | None = None) -> Path:
    """ffmpeg transcode to mono PCM wav at sr, optionally a [ss, ss+dur] window."""
    dst.parent.mkdir(parents=True, exist_ok=True)
    cmd = ["ffmpeg", "-y"]
    if ss is not None:
        cmd += ["-ss", str(ss)]
    if dur is not None:
        cmd += ["-t", str(dur)]
    cmd += ["-i", str(mp3), "-ac", "1", "-ar", str(sr), "-c:a", "pcm_s16le", str(dst)]
    subprocess.run(cmd, check=True, capture_output=True)
    return dst


def _clean_window_of(mp3: Path, work: Path, want_s: float) -> tuple[float, float]:
    """Transcode the full file, analyze it, and return a clean (t0, t1) window."""
    full = transcode(mp3, 16000, work / "_full.wav")
    rec = pipeline.analyze(full, use_profile=False)
    t0, t1 = pipeline.clean_window(rec, want_s=want_s)
    full.unlink(missing_ok=True)
    return t0, t1


def build_gallery(g: dict) -> dict:
    d = EXAMPLES / g["id"]
    if d.exists():
        shutil.rmtree(d)
    d.mkdir(parents=True)
    print(f"[{g['id']}] clean window", file=sys.stderr)
    t0, t1 = _clean_window_of(SRC / g["file"], d, g["want_s"])

    original = transcode(SRC / g["file"], 24000, d / "original.wav", ss=t0, dur=t1 - t0)
    win16k = transcode(SRC / g["file"], 16000, d / "_win.wav", ss=t0, dur=t1 - t0)
    print(f"[{g['id']}] analyze + clone", file=sys.stderr)
    record = pipeline.analyze(win16k, use_profile=False)
    ref = pipeline.pick_ref_clip(win16k, record, d / "_ref.wav")
    # split at 0.3 s (the notation's own pause threshold) so the clone reproduces
    # every pause the original has, not only those over 0.4 s.
    prosody = pipeline.clone_render(record, ref, d / "prosody.wav",
                                    condition="prosody", clause_min_pause_s=0.30)
    print(f"[{g['id']}] verify", file=sys.stderr)
    card = pipeline.verify(record, prosody, original)
    for tmp in ("_win.wav", "_ref.wav", "prosody.clauses.txt"):
        (d / tmp).unlink(missing_ok=True)
    return {
        "id": g["id"], "title": g["title"], "blurb": g["blurb"], "source": g["source"],
        "original_url": f"/examples/{g['id']}/original.wav",
        "prosody_url": f"/examples/{g['id']}/prosody.wav",
        "view": pipeline.record_to_view(record),
        "scorecard": card,
    }


def build_game() -> dict:
    d = EXAMPLES / "game"
    if d.exists():
        shutil.rmtree(d)
    d.mkdir(parents=True)
    print("[game] clean window", file=sys.stderr)
    t0, t1 = _clean_window_of(SRC / GAME_FILE, d, GAME_WANT_S)
    win16k = transcode(SRC / GAME_FILE, 16000, d / "_win.wav", ss=t0, dur=t1 - t0)
    hq = transcode(SRC / GAME_FILE, 24000, d / "_hq.wav", ss=t0, dur=t1 - t0)
    record = pipeline.analyze(win16k, use_profile=False)
    print("[game] render clones + equalize", file=sys.stderr)
    game = pipeline.build_game(win16k, record, d / "_build",
                               n_clones=GAME_N_CLONES, hq_source=hq)

    items, truth = [], {}
    tagged = [(uuid.uuid4().hex[:8], it) for it in game["items"]]
    tagged.sort(key=lambda t: t[0])
    for pos, (item_id, it) in enumerate(tagged):
        shutil.copy(it["file"], d / f"item_{pos}.wav")
        items.append({"id": item_id, "url": f"/examples/game/item_{pos}.wav", "position": pos})
        truth[item_id] = {"is_real": it["is_real"], "label": it["label"]}
    (d / "truth.json").write_text(json.dumps({"truth": truth}, indent=1), encoding="utf-8")
    for tmp in ("_win.wav", "_hq.wav"):
        (d / tmp).unlink(missing_ok=True)
    shutil.rmtree(d / "_build", ignore_errors=True)
    return {"items": items, "truth_url": "/examples/game/truth.json",
            "target_text": game["target_text"]}


def main() -> None:
    EXAMPLES.mkdir(parents=True, exist_ok=True)
    galleries = [build_gallery(g) for g in GALLERIES]
    game = build_game()
    manifest = {"galleries": galleries, "game": game}
    (EXAMPLES / "manifest.json").write_text(
        json.dumps(manifest, ensure_ascii=False, indent=1), encoding="utf-8")
    print(f"wrote {EXAMPLES / 'manifest.json'} "
          f"({len(galleries)} galleries + game)", file=sys.stderr)


if __name__ == "__main__":
    main()

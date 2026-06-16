"""Phase 1: download the speaker audio and build the XTTS training set.

Downloads each video id in sources.txt (audio only), then segments every file
into per-sentence clips with transcripts (the XTTS training format), writing
data/dataset/metadata_train.csv, metadata_eval.csv and wavs/.

The whisper model is forced to int8 on CPU. The coqui demo formatter hardcodes
large-v2 + float16, which fails on a CPU/Apple-Silicon box. Run inside the env:
    finetune/.env/bin/python finetune/prepare.py
"""

import subprocess
import sys
from pathlib import Path

HERE = Path(__file__).resolve().parent
AUDIO = HERE / "data" / "audio"
DATASET = HERE / "data" / "dataset"
AUDIO.mkdir(parents=True, exist_ok=True)


def video_ids() -> list[str]:
    lines = (HERE / "sources.txt").read_text(encoding="utf-8").splitlines()
    return [x.strip() for x in lines if x.strip() and not x.startswith("#")]


def download() -> list[str]:
    wavs = []
    for vid in video_ids():
        out = AUDIO / f"{vid}.wav"
        if not out.exists():
            print(f">>> downloading {vid}", flush=True)
            # invoke yt-dlp as a module via this interpreter, so it works whether or
            # not the env's bin is on PATH (running through .env/bin/python does not
            # put .env/bin on PATH). yt-dlp still needs ffmpeg on PATH for the wav
            # extraction - see setup.sh for the brew install.
            subprocess.run(
                [sys.executable, "-m", "yt_dlp",
                 "-x", "--audio-format", "wav", "--no-playlist",
                 "-o", str(AUDIO / f"{vid}.%(ext)s"),
                 f"https://www.youtube.com/watch?v={vid}"],
                check=True,
            )
        wavs.append(str(out))
    return wavs


def build_dataset(wavs: list[str]) -> None:
    # force CPU int8 whisper inside the coqui formatter
    from TTS.demos.xtts_ft_demo.utils import formatter as F
    _orig = F.WhisperModel
    F.WhisperModel = lambda *a, **k: _orig("large-v2", device="cpu", compute_type="int8")
    train_csv, eval_csv, total = F.format_audio_list(
        wavs, target_language="en", out_path=str(DATASET), speaker_name="speaker")
    print(f"\nDATASET READY")
    print(f"  train: {train_csv}")
    print(f"  eval:  {eval_csv}")
    print(f"  total audio: {round(total, 1)}s across {len(wavs)} files")


if __name__ == "__main__":
    wavs = download()
    print(f">>> {len(wavs)} source files ready, building dataset (this transcribes "
          f"~65 min, slow on CPU)...", flush=True)
    build_dataset(wavs)

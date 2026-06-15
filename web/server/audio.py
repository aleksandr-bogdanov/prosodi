"""Audio I/O helpers for the web server.

The browser records WebM/Opus and users drop wav/mp3/m4a; the prosodi pipeline
wants 16 kHz mono PCM wav. ffmpeg does every conversion. Renders come back at
24 kHz and are served as-is (browsers play wav fine).
"""

import shutil
import subprocess
from pathlib import Path

FFMPEG = shutil.which("ffmpeg")


class FFmpegMissing(RuntimeError):
    pass


def to_wav(src: Path, dst: Path, sr: int = 16000) -> Path:
    """Transcode any audio or video container to mono PCM wav at sr."""
    if FFMPEG is None:
        raise FFmpegMissing("ffmpeg is not installed (brew install ffmpeg)")
    dst.parent.mkdir(parents=True, exist_ok=True)
    subprocess.run(
        [FFMPEG, "-y", "-i", str(src), "-ac", "1", "-ar", str(sr),
         "-c:a", "pcm_s16le", str(dst)],
        check=True, capture_output=True,
    )
    return dst


def to_wav16k(src: Path, dst: Path) -> Path:
    """Transcode any audio container to 16 kHz mono PCM wav for the pipeline."""
    return to_wav(src, dst, 16000)


def duration_s(src: Path) -> float:
    """Seconds of audio, via ffprobe; 0.0 when it cannot be read."""
    probe = shutil.which("ffprobe")
    if probe is None:
        return 0.0
    try:
        out = subprocess.run(
            [probe, "-v", "error", "-show_entries", "format=duration",
             "-of", "default=noprint_wrappers=1:nokey=1", str(src)],
            check=True, capture_output=True, text=True,
        )
        return float(out.stdout.strip())
    except (subprocess.CalledProcessError, ValueError):
        return 0.0

"""Phase 1: download the speaker audio and build an F5-TTS dataset.

Downloads each id in sources.txt, segments every file into per-sentence clips with
transcripts, writes wavs/ + metadata.csv (path|transcript), then hands it to F5-TTS's
prepare_csv_wavs to build the training dataset.

F5-TTS's dataset tooling and the exact metadata column format drift between releases.
VERIFY against the installed package: check `prepare_csv_wavs --help` (or
f5_tts.train.datasets.prepare_csv_wavs) and adjust the metadata format below if needed.

    finetune-f5/.env/bin/python finetune-f5/prepare.py
"""

import subprocess
import sys
from pathlib import Path

HERE = Path(__file__).resolve().parent
AUDIO = HERE / "data" / "audio"
CLIPS = HERE / "data" / "clips"
WAVS = CLIPS / "wavs"
AUDIO.mkdir(parents=True, exist_ok=True)
WAVS.mkdir(parents=True, exist_ok=True)


def video_ids() -> list[str]:
    lines = (HERE / "sources.txt").read_text(encoding="utf-8").splitlines()
    return [x.strip() for x in lines if x.strip() and not x.startswith("#")]


def download() -> list[Path]:
    out = []
    for vid in video_ids():
        wav = AUDIO / f"{vid}.wav"
        if not wav.exists():
            print(f">>> downloading {vid}", flush=True)
            subprocess.run([sys.executable, "-m", "yt_dlp", "-x", "--audio-format", "wav",
                            "--no-playlist", "-o", str(AUDIO / f"{vid}.%(ext)s"),
                            f"https://www.youtube.com/watch?v={vid}"], check=True)
        out.append(wav)
    return out


def segment_and_transcribe(wavs: list[Path]) -> Path:
    """Per-sentence clips + metadata.csv (audio_path|transcript). int8 CPU whisper."""
    import csv
    import soundfile as sf
    from faster_whisper import WhisperModel

    asr = WhisperModel("large-v2", device="cpu", compute_type="int8")
    meta = CLIPS / "metadata.csv"
    n = 0
    with meta.open("w", newline="", encoding="utf-8") as f:
        w = csv.writer(f, delimiter="|")
        w.writerow(["audio_file", "text"])  # prepare_csv_wavs requires this exact header
        for wav in wavs:
            print(f">>> transcribing {wav.name}", flush=True)
            audio, sr = sf.read(str(wav))
            if audio.ndim > 1:
                audio = audio.mean(axis=1)
            segments, _ = asr.transcribe(str(wav), word_timestamps=True, language="en")
            buf, start = "", None
            for seg in segments:
                for word in seg.words:
                    if start is None:
                        start = word.start
                    buf += word.word
                    if word.word.strip().endswith((".", "!", "?")):
                        a, b = int(start * sr), int(word.end * sr)
                        clip = WAVS / f"clip_{n:06d}.wav"
                        sf.write(str(clip), audio[a:b], sr, subtype="PCM_16")
                        w.writerow([str(clip.resolve()), buf.strip()])  # must be absolute
                        n += 1
                        buf, start = "", None
    print(f">>> {n} clips, metadata at {meta}", flush=True)
    return meta


DATASET_NAME = "prosodi_speaker"


def f5_data_dir() -> Path:
    """Where F5-TTS looks for a named dataset at train time.

    load_dataset("<name>") reads <f5_tts pkg>/../../data/<name>_pinyin, which on a
    venv resolves to .env/lib/pythonX.Y/data/ (NOT site-packages/data). The dataset
    has to land there or training cannot find it. (Found by the M5 run.)
    """
    import f5_tts
    return Path(f5_tts.__file__).resolve().parent.parent.parent / "data"


def build_dataset(meta: Path) -> None:
    """Hand the metadata CSV to F5-TTS prepare_csv_wavs, writing to f5's data dir.

    Two M5-found requirements: prepare_csv_wavs takes the CSV FILE (not the dir),
    and a finetune build asserts the Emilia vocab exists, which the pip install does
    not ship - copy it from the bundled inference examples.
    """
    import shutil
    import f5_tts

    data_root = f5_data_dir()
    out = data_root / f"{DATASET_NAME}_pinyin"
    f5_pkg = Path(f5_tts.__file__).resolve().parent

    emilia = data_root / "Emilia_ZH_EN_pinyin"
    emilia.mkdir(parents=True, exist_ok=True)
    vocab_src = f5_pkg / "infer" / "examples" / "vocab.txt"
    if vocab_src.exists() and not (emilia / "vocab.txt").exists():
        shutil.copy(vocab_src, emilia / "vocab.txt")

    print(f">>> building dataset '{DATASET_NAME}' -> {out}", flush=True)
    subprocess.run([sys.executable, "-m", "f5_tts.train.datasets.prepare_csv_wavs",
                    str(meta), str(out)], check=True)
    print(f">>> dataset ready at {out}")


if __name__ == "__main__":
    wavs = download()
    meta = segment_and_transcribe(wavs)
    build_dataset(meta)

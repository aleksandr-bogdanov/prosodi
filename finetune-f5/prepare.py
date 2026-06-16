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
                        w.writerow([f"wavs/{clip.name}", buf.strip()])
                        n += 1
                        buf, start = "", None
    print(f">>> {n} clips, metadata at {meta}", flush=True)
    return meta


def build_dataset(meta: Path) -> None:
    """Hand the clips to F5-TTS. The CLI name/flags are version-specific: verify."""
    print(">>> building the F5-TTS dataset (verify the prepare-csv-wavs invocation)",
          flush=True)
    # Common form: prepare_csv_wavs <input_dir_with_metadata.csv> <output_dataset_dir>
    out = HERE / "data" / "dataset"
    try:
        subprocess.run([sys.executable, "-m", "f5_tts.train.datasets.prepare_csv_wavs",
                        str(CLIPS), str(out)], check=True)
    except Exception as e:
        print(f"prepare_csv_wavs call failed ({e}). Check the installed F5-TTS data "
              f"tooling and run it by hand on {CLIPS} -> {out}.", file=sys.stderr)


if __name__ == "__main__":
    wavs = download()
    meta = segment_and_transcribe(wavs)
    build_dataset(meta)

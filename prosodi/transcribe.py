"""mlx-whisper word-timestamp transcription."""

from .config import Config


def transcribe_words(wav_path: str, cfg: Config) -> dict:
    """Return {"language": str, "text": str, "words": [{"text", "start", "end", "probability"}]}.

    mlx_whisper caches the loaded model per repo path, so batch runs in one
    process pay the model load once.
    """
    import mlx_whisper  # lazy, the import alone takes seconds

    res = mlx_whisper.transcribe(wav_path, path_or_hf_repo=cfg.model, word_timestamps=True)
    words = []
    for seg in res["segments"]:
        for w in seg.get("words", []):
            text = w["word"].strip()
            if not text:
                continue
            words.append({
                "text": text,
                "start": float(w["start"]),
                "end": float(w["end"]),
                "probability": float(w.get("probability", 1.0)),
            })
    return {
        "language": res.get("language", ""),
        "text": res["text"].strip(),
        "words": words,
    }

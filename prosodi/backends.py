"""Synthesis backends for the round trip.

A backend turns a .prosodi.json record into audio for one of two conditions:

    prosody   the record drives the synthesis (markup or clause timing)
    control   the same words with none of the record's prosody imposed

The protocol is deliberately small so targets stay pluggable: a name plus
render(record, out_wav, condition). A backend may write side files next to the
wav (say keeps its exact input text there, f5 its clause plan), always derived
from the wav's stem so one sample dir can hold several targets side by side.
"""

import os
import re
import subprocess
import sys
import warnings
from pathlib import Path
from typing import Protocol

from .compile_say import compile_control, compile_prosody

CONDITIONS = ("prosody", "control")

# Default pool for the f5 reference voice clip (read only, never written).
# Set PROSODI_REF_DIR to point it at any directory of wavs. The fallback is
# this machine's dictation sample dir (the prosody-research snapshot in the
# owner's vault), kept so local runs need no env setup.
DEFAULT_REF_DIR = Path(os.environ.get(
    "PROSODI_REF_DIR",
    "/Users/abogdanov/imprint-vault/raw/adhoc/prosody-research/samples"))


class Backend(Protocol):
    name: str

    def render(self, record: dict, out_wav: Path, condition: str) -> None:
        """Synthesize the record into out_wav under the given condition."""
        ...


class SayBackend:
    """macOS `say` with embedded speech commands (the v0 target).

    The prosody condition compiles the record into [[slnc]]/[[rate]]/[[emph]]
    commands (compile_say.py), the control condition is the bare words. Pitch
    hints ([[pbas]]) stay opt-in, they produce audible semitone jumps.
    """

    name = "say"

    # Eddy sits at ~123.6 Hz untuned, matching the speaker's 123.3 Hz corpus
    # median (voice-target probe, 2026-06-12). Samantha was +6.3 st off.
    DEFAULT_VOICE = "Eddy"
    DATA_FORMAT = "LEI16@22050"

    def __init__(self, voice: str = DEFAULT_VOICE, pitch: bool = False):
        self.voice = voice
        self.pitch = pitch

    def render(self, record: dict, out_wav: Path, condition: str) -> None:
        if condition == "prosody":
            text = compile_prosody(record, pitch=self.pitch)
        else:
            text = compile_control(record)
        txt_path = out_wav.with_suffix(".say.txt")
        txt_path.write_text(text + "\n", encoding="utf-8")
        subprocess.run(
            ["say", "-v", self.voice, "-o", str(out_wav),
             f"--data-format={self.DATA_FORMAT}", "-f", str(txt_path)],
            check=True,
        )


def split_clauses(record: dict, min_pause_s: float = 0.4) -> list[dict]:
    """Split the record's words at rendered pauses of at least min_pause_s.

    Returns one dict per clause: first_word/last_word indices, the clause text,
    the measured speech duration (speech-trimmed edge to edge, so leading and
    trailing silence never inflate the tempo target), and gap_after_s, the
    silence to insert after the clause (None on the last one).

    gap_after_s is the FULL gap to the next clause (its first sound minus this
    clause's last sound), not just the detected-silence slice. Reproducing the
    whole gap keeps the clone on the original's timeline. Using only the silence
    overlap dropped the rest of each pause and made the clone rush between
    phrases.
    """
    words = record["words"]
    break_at = {p["after_word"]
                for p in record["pauses"]
                if p["rendered"] and p["silence_overlap_s"] >= min_pause_s}
    clauses, start = [], 0
    for i in range(len(words)):
        if i in break_at or i == len(words) - 1:
            seg = words[start:i + 1]
            t0 = seg[0]["speech_pieces"][0][0]
            t1 = seg[-1]["speech_pieces"][-1][1]
            gap = None
            if i in break_at and i + 1 < len(words):
                next_start = words[i + 1]["speech_pieces"][0][0]
                gap = round(max(0.0, next_start - t1), 3)
            clauses.append({
                "first_word": start,
                "last_word": i,
                "text": " ".join(w["text"] for w in seg),
                "duration_s": round(max(0.0, t1 - t0), 3),
                "gap_after_s": gap,
            })
            start = i + 1
    return clauses


class F5Backend:
    """f5-tts-mlx voice cloning, driven clause by clause.

    f5 has no inline markup, so the prosody condition is structural: the
    record is split at rendered pauses of at least 0.4 s, each clause is
    rendered separately with its measured speech duration imposed (f5's
    duration argument doubles as tempo control), and the clauses are
    concatenated with the measured silences between them. The control
    condition renders the whole text in one go with no imposed timing
    (chunked at sentence boundaries only when the model's 4096-frame
    sequence ceiling forces it).

    The reference voice clip comes from --ref-audio, then <repo>/voice-ref.wav
    when present (record one deliberately, a clean mic beats any dictation
    clip), then the longest 3-12 s wav in DEFAULT_REF_DIR (PROSODI_REF_DIR,
    read only). Its transcript is taken from mlx-whisper at first use.
    Requires the synth dependency group: uv sync --group synth.

    Clause shaping (prosody condition only, renderer-side, never in the record):
    f5 does not honor the duration argument as a tempo target. It speaks at its
    own fast clip rate and pads the rest of the frame budget with silence, so a
    cloned clause comes out both fast and bracketed by f5's own silence. Two
    fixes: trim_seams removes that bracketing silence (so the only gap between
    clauses is the measured one), and fit_tempo time-stretches the trimmed
    speech to the clause's measured duration (so the clone inherits the
    original's tempo). Both default on, both can be disabled to reproduce the
    raw clip-rate clone.
    """

    name = "f5"

    SAMPLE_RATE = 24_000
    HOP_LENGTH = 256
    FRAMES_PER_SEC = SAMPLE_RATE / HOP_LENGTH
    MAX_FRAMES = 4096          # the model's sequence ceiling (ref + generation)
    TARGET_RMS = 0.1           # f5's own reference normalization level
    MIN_CLAUSE_S = 0.4         # floor on an imposed clause duration
    REF_MIN_S, REF_MAX_S = 3.0, 12.0
    CONTROL_CHUNK_EST_S = 25.0  # estimated speech per control chunk, ceiling margin
    TRIM_TOP_DB = 30.0          # quieter than 30 dB below the clause peak is edge silence
    FIT_RATE_CLAMP = (0.66, 1.5)  # cap the time-stretch so the phase vocoder stays clean

    def __init__(self, ref_audio: Path | None = None,
                 trim_seams: bool = True, fit_tempo: bool = True,
                 clause_min_pause_s: float = 0.4, ref_text: str | None = None):
        self._ref_path = ref_audio
        # A saved voice carries its transcript, so reuse skips whisper on the ref.
        self._ref_text_override = ref_text
        self.trim_seams = trim_seams
        self.fit_tempo = fit_tempo
        # Pauses at least this long split the record into separately-rendered
        # clauses. Lower it (e.g. 0.25) to reproduce more of the original's
        # micro-hesitations as real silences, at the cost of more f5 calls.
        self.clause_min_pause_s = clause_min_pause_s
        self._model = None
        self._ref = None  # (mx.array audio @24k, ref_text, ref_seconds)
        try:
            with warnings.catch_warnings():
                warnings.simplefilter("ignore")  # jieba import is noisy
                from f5_tts_mlx.cfm import F5TTS  # noqa: F401
        except ImportError as e:
            raise RuntimeError(
                "the f5 target needs f5-tts-mlx, run: uv sync --group synth") from e

    # --- reference voice ---

    def _pick_default_ref(self) -> Path:
        import soundfile as sf
        # A deliberately recorded reference (studio mic) beats any dictation clip.
        # Drop one at <repo>/voice-ref.wav and it wins without any flag.
        studio = Path(__file__).resolve().parent.parent / "voice-ref.wav"
        if studio.exists():
            return studio
        best: tuple[Path, float] | None = None
        for wav in sorted(DEFAULT_REF_DIR.glob("*.wav")):
            dur = sf.info(str(wav)).duration
            if self.REF_MIN_S <= dur <= self.REF_MAX_S and (best is None or dur > best[1]):
                best = (wav, dur)
        if best is None:
            raise RuntimeError(
                f"no {self.REF_MIN_S:.0f}-{self.REF_MAX_S:.0f} s wav in {DEFAULT_REF_DIR}, "
                "pass --ref-audio")
        return best[0]

    def _ensure_ready(self) -> None:
        if self._model is not None:
            return
        import mlx.core as mx
        import numpy as np
        import soundfile as sf
        with warnings.catch_warnings():
            warnings.simplefilter("ignore")
            from f5_tts_mlx.cfm import F5TTS

        ref_path = self._ref_path if self._ref_path else self._pick_default_ref()
        audio, sr = sf.read(str(ref_path))
        if audio.ndim > 1:
            audio = audio.mean(axis=1)
        if sr != self.SAMPLE_RATE:
            n = int(round(len(audio) * self.SAMPLE_RATE / sr))
            audio = np.interp(np.linspace(0.0, 1.0, n, endpoint=False),
                              np.linspace(0.0, 1.0, len(audio), endpoint=False), audio)
        rms = float(np.sqrt(np.mean(np.square(audio))))
        if 0 < rms < self.TARGET_RMS:
            audio = audio * (self.TARGET_RMS / rms)

        if self._ref_text_override is not None:
            ref_text = self._ref_text_override
        else:
            from .config import DEFAULT
            from .transcribe import transcribe_words
            ref_text = transcribe_words(str(ref_path), DEFAULT)["text"]
        print(f"f5: reference {ref_path.name} ({len(audio) / self.SAMPLE_RATE:.1f} s), "
              f"loading model...", file=sys.stderr)
        self._model = F5TTS.from_pretrained("lucasnewman/f5-tts-mlx")
        # Cap the MLX buffer cache so a long clause-by-clause render (or a server
        # rendering several clones) does not accumulate Metal memory and OOM.
        mx.set_cache_limit(384 * 1024 * 1024)
        self._ref = (mx.array(audio), ref_text, len(audio) / self.SAMPLE_RATE)

    # --- generation ---

    def _generate(self, text: str, duration_s: float | None):
        """Render one piece of text in the reference voice, return float numpy @24k.

        duration_s imposes the generated speech length (tempo control). None
        lets the model's duration predictor pick a natural tempo.
        """
        import mlx.core as mx
        import numpy as np
        from f5_tts_mlx.utils import convert_char_to_pinyin

        ref_audio, ref_text, ref_s = self._ref
        frames = None
        if duration_s is not None:
            total_s = ref_s + max(duration_s, self.MIN_CLAUSE_S)
            frames = min(int(round(total_s * self.FRAMES_PER_SEC)), self.MAX_FRAMES)
        pinyin = convert_char_to_pinyin([ref_text + " " + text])
        wave, _ = self._model.sample(
            mx.expand_dims(ref_audio, axis=0), text=pinyin, duration=frames)
        wave = wave[ref_audio.shape[0]:]
        mx.eval(wave)
        result = np.array(wave)
        mx.clear_cache()  # release Metal buffers between clauses, bound memory
        return result

    def _fit_clause(self, wave, target_s: float):
        """Trim f5's edge silence, then time-stretch the speech to target_s.

        Renderer-side tempo control. Returns the wave unchanged when both
        fixes are off or the clause is all silence (better to keep a too-fast
        clause than to drop it).
        """
        import numpy as np
        if not (self.trim_seams or self.fit_tempo) or wave.size == 0:
            return wave
        import librosa
        w = wave.astype(np.float32)
        if self.trim_seams:
            trimmed, _ = librosa.effects.trim(w, top_db=self.TRIM_TOP_DB)
            if trimmed.size == 0:
                return wave
            w = trimmed
        if self.fit_tempo and target_s and target_s > 0:
            cur_s = w.size / self.SAMPLE_RATE
            if cur_s > 0:
                lo, hi = self.FIT_RATE_CLAMP
                raw = cur_s / target_s
                rate = min(max(raw, lo), hi)
                if os.environ.get("PROSODI_FIT_DEBUG"):
                    clamped = "CLAMPED" if rate != raw else ""
                    print(f"  fit: cur {cur_s:.2f}s target {target_s:.2f}s "
                          f"raw_rate {raw:.2f} -> {rate:.2f} {clamped}", file=sys.stderr)
                if abs(rate - 1.0) > 0.02:  # skip a stretch that would not be heard
                    w = librosa.effects.time_stretch(w, rate=rate)
        return w

    def _control_chunks(self, record: dict) -> list[str]:
        """The whole text, split at sentence ends only when the model's
        sequence ceiling forces it. Chunks are concatenated with no silence."""
        text = " ".join(w["text"] for w in record["words"])
        cps = record["utterance"]["chars_per_s"] or 12.0
        if len(text) / cps <= self.CONTROL_CHUNK_EST_S:
            return [text]
        sentences = [s for s in re.split(r"(?<=[.!?;:])\s+", text) if s]
        chunks, cur = [], ""
        for s in sentences:
            cand = f"{cur} {s}".strip()
            if cur and len(cand) / cps > self.CONTROL_CHUNK_EST_S:
                chunks.append(cur)
                cur = s
            else:
                cur = cand
        if cur:
            chunks.append(cur)
        return chunks

    def render(self, record: dict, out_wav: Path, condition: str) -> None:
        import numpy as np
        import soundfile as sf

        self._ensure_ready()
        pieces: list = []
        plan: list[str] = []
        if condition == "prosody":
            clauses = split_clauses(record, self.clause_min_pause_s)
            for c in clauses:
                gen = self._generate(c["text"], c["duration_s"])
                pieces.append(self._fit_clause(gen, c["duration_s"]))
                plan.append(f"[{c['duration_s']:.2f}s] {c['text']}")
                if c["gap_after_s"] is not None:
                    pieces.append(np.zeros(int(round(c["gap_after_s"] * self.SAMPLE_RATE))))
                    plan.append(f"<silence {c['gap_after_s']:.2f}s>")
        else:
            for chunk in self._control_chunks(record):
                pieces.append(self._generate(chunk, None))
                plan.append(f"[natural] {chunk}")

        wave = np.concatenate(pieces) if pieces else np.zeros(0)
        sf.write(str(out_wav), wave, self.SAMPLE_RATE, subtype="PCM_16")
        out_wav.with_suffix(".clauses.txt").write_text(
            "\n".join(plan) + "\n", encoding="utf-8")


class ElevenLabsBackend:
    """ElevenLabs cloud TTS. STUB: no network call is implemented.

    Planned mapping (prosodi record -> ElevenLabs request):

        rendered pause          <break time="X.Xs"/> in the text body
                                (documented up to 3 s per break, values are hints)
        utterance speech rate   voice_settings.speed (roughly 0.7-1.2)
        tempo span / stretch    no per-span control; v3 audio tags ([rushed],
                                [drawn out]) are categorical, never a measured
                                ratio, so magnitude cannot map
        emphasis                no reliable handle; caps or quotes only nudge
                                the model
        F0 (median, contour)    no mapping at all, pitch is owned by the voice
        voice                   a cloned voice id stands in for the f5 ref clip

    The constructor refuses to build unless ELEVENLABS_API_KEY is set and the
    elevenlabs package is importable, and render() is unimplemented either
    way, so this class can never reach the network by accident.
    """

    name = "elevenlabs"

    def __init__(self):
        import os
        if not os.environ.get("ELEVENLABS_API_KEY"):
            raise RuntimeError(
                "the elevenlabs target needs ELEVENLABS_API_KEY set and the "
                "elevenlabs package installed (uv add elevenlabs)")
        try:
            import elevenlabs  # noqa: F401
        except ImportError as e:
            raise RuntimeError(
                "the elevenlabs target needs ELEVENLABS_API_KEY set and the "
                "elevenlabs package installed (uv add elevenlabs)") from e

    def render(self, record: dict, out_wav: Path, condition: str) -> None:
        raise NotImplementedError(
            "the elevenlabs backend is a stub: the mapping is documented in "
            "its docstring, the API call is not wired yet")


def make_backends(spec: str, *, pitch: bool = False,
                  ref_audio: Path | None = None) -> list[Backend]:
    """Parse a comma-separated target spec ("say,f5") into backend instances.

    Raises ValueError on an unknown name and lets a backend's own constructor
    raise when its dependencies are missing, so a bad --target fails before
    any analysis work is spent.
    """
    backends: list[Backend] = []
    for name in [t.strip() for t in spec.split(",") if t.strip()]:
        if name == "say":
            backends.append(SayBackend(pitch=pitch))
        elif name == "f5":
            backends.append(F5Backend(ref_audio=ref_audio))
        elif name == "elevenlabs":
            backends.append(ElevenLabsBackend())
        else:
            raise ValueError(
                f"unknown synthesis target '{name}' (available: say, f5, elevenlabs)")
    if not backends:
        raise ValueError("no synthesis target given")
    return backends

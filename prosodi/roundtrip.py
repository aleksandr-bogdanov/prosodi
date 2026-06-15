"""Round-trip one or more recordings: analyze -> compile -> render -> listen.

For each input wav: run the analyze pipeline, then render a prosody and a
control wav per synthesis target (see prosodi/backends.py), and put everything
for that sample in its own directory:

    <out>/<sample>/original.wav              the input voice
    <out>/<sample>/original.prosodi.json     the record
    <out>/<sample>/original.prosodi.txt      the annotated transcript (notation)
    <out>/<sample>/<target>-prosody.wav      the record-driven render
    <out>/<sample>/<target>-control.wav      the same words, no prosody imposed
    <out>/<sample>/<target>-*.say.txt        say only: the exact input text
    <out>/<sample>/<target>-*.clauses.txt    f5 only: the clause plan

Inputs: nothing (the newest VoiceInk dictation), --n N (the N newest), a wav
path, or a directory of wavs. The VoiceInk store and Recordings dir are read
only, originals are copied out before anything touches them.
"""

import json
import re
import shutil
import sys
import tempfile
from dataclasses import dataclass
from pathlib import Path

from .analyze import analyze_file
from .backends import CONDITIONS, make_backends
from .config import DEFAULT
from .render import render_txt

_UUIDISH = re.compile(r"^[0-9A-Fa-f]{8}-[0-9A-Fa-f-]{27,}$")


@dataclass
class Sample:
    name: str           # the sample dir name under <out>/
    wav: Path           # the source wav (read only, gets copied)
    transcript: str | None  # reference text when the source is the VoiceInk store


def _short(stem: str) -> str:
    """VoiceInk wavs are named by UUID, the first block is enough for a dir name."""
    return stem.split("-")[0] if _UUIDISH.match(stem) else stem


def _gather(args) -> list[Sample]:
    if args.input is None:
        from .voiceink import VOICEINK_STORE, latest_dictations
        store = args.store if args.store else VOICEINK_STORE
        dictations = latest_dictations(store, args.n)
        samples = []
        for d in dictations:
            if d.wav is None or not d.wav.exists():
                print(f"skipping a dictation with no audio "
                      f"({'purged' if d.wav else 'no audio path'}): "
                      f"{d.text[:60]}...", file=sys.stderr)
                continue
            samples.append(Sample(_short(d.wav.stem), d.wav, d.text))
        return samples
    if args.input.is_dir():
        return [Sample(_short(w.stem), w, None) for w in sorted(args.input.glob("*.wav"))]
    return [Sample(_short(args.input.stem), args.input, None)]


def _marker_counts(record: dict) -> dict:
    anns = [w["annotation"] for w in record["words"]]
    return {
        "emphasized": sum(1 for a in anns if a["emphasized"]),
        "stretched": sum(1 for a in anns if a["stretched"] is not None),
        "boundaries": sum(1 for a in anns if a["boundary"] is not None),
        "tempo_spans": len(record["tempo_spans"]),
        "pauses": sum(1 for p in record["pauses"] if p["rendered"]),
    }


def run_roundtrip(args) -> int:
    try:
        samples = _gather(args)
    except Exception as e:
        print(f"could not list the inputs ({e})", file=sys.stderr)
        return 1
    if not samples:
        print("nothing to round-trip", file=sys.stderr)
        return 1

    # Build the backends before any analysis work, so an unknown target or a
    # missing synth dependency fails in the first second, never after whisper.
    try:
        backends = make_backends(args.target, pitch=args.pitch, ref_audio=args.ref_audio)
    except (ValueError, RuntimeError) as e:
        print(str(e), file=sys.stderr)
        return 1

    profile_path = (args.profile if args.profile
                    else Path(__file__).resolve().parent.parent / "speaker-profile.json")
    profile = None
    if profile_path.exists():
        profile = json.loads(profile_path.read_text(encoding="utf-8"))
    else:
        print(f"speaker profile not found at {profile_path}, baseline comparison off",
              file=sys.stderr)

    out_root = args.out if args.out else Path(tempfile.mkdtemp(prefix="prosodi-roundtrip-"))
    out_root.mkdir(parents=True, exist_ok=True)

    from .console import print_header, print_roundtrip_summary, print_transcript, use_console
    rich_mode = use_console(args.plain)

    rows, failures = [], 0
    for s in samples:
        sample_dir = out_root / s.name
        sample_dir.mkdir(parents=True, exist_ok=True)
        original = sample_dir / "original.wav"
        shutil.copy(s.wav, original)
        try:
            record = analyze_file(str(original), DEFAULT,
                                  reference_transcript=s.transcript, profile=profile)
        except Exception as e:
            failures += 1
            print(f"{s.name}: analysis failed ({e})", file=sys.stderr)
            continue
        notation = render_txt(record)
        (sample_dir / "original.prosodi.json").write_text(
            json.dumps(record, ensure_ascii=False, indent=1), encoding="utf-8")
        (sample_dir / "original.prosodi.txt").write_text(notation, encoding="utf-8")

        sample_ok = True
        for backend in backends:
            for condition in CONDITIONS:
                out_wav = sample_dir / f"{backend.name}-{condition}.wav"
                try:
                    backend.render(record, out_wav, condition)
                except Exception as e:
                    sample_ok = False
                    print(f"{s.name}: {backend.name} {condition} render failed ({e})",
                          file=sys.stderr)
        if not sample_ok:
            failures += 1

        if rich_mode:
            print_header(record)
            print_transcript(record)
        else:
            print(notation)

        counts = _marker_counts(record)
        rows.append({
            "sample": s.name,
            "duration_s": record["utterance"]["duration_s"],
            "words": record["utterance"]["n_words"],
            "path": str(sample_dir),
            **counts,
        })

    if rows:
        print_roundtrip_summary(rows)
        names = ", ".join(b.name for b in backends)
        print(f"\nlisten in each dir: original.wav -> <target>-prosody.wav -> "
              f"<target>-control.wav (targets: {names})", file=sys.stderr)
    return 1 if failures else 0

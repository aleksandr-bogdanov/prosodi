"""prosodi CLI: analyze one wav or a directory of them."""

import argparse
import csv
import json
import sqlite3
import sys
import tempfile
import time
from datetime import datetime
from pathlib import Path

from .analyze import analyze_file
from .config import DEFAULT
from .render import render_txt


def _out_paths(wav: Path, out_dir: Path | None) -> tuple[Path, Path]:
    base = out_dir if out_dir is not None else wav.parent
    base.mkdir(parents=True, exist_ok=True)
    return base / f"{wav.stem}.prosodi.json", base / f"{wav.stem}.prosodi.txt"


def _analyze_one(wav: Path, out_dir: Path | None, transcript: str | None,
                 profile: dict | None = None) -> dict:
    t0 = time.perf_counter()
    record = analyze_file(str(wav), DEFAULT, reference_transcript=transcript, profile=profile)
    elapsed = time.perf_counter() - t0
    jpath, tpath = _out_paths(wav, out_dir)
    jpath.write_text(json.dumps(record, ensure_ascii=False, indent=1), encoding="utf-8")
    tpath.write_text(render_txt(record), encoding="utf-8")
    print(f"{wav.name}: {record['utterance']['n_words']} words, "
          f"{record['utterance']['pause_count']} pauses, {elapsed:.1f}s -> {tpath}",
          file=sys.stderr)
    return record


def _show(record: dict, plain: bool) -> None:
    """Print one record to stdout: rich on a tty, the file notation otherwise."""
    from .console import print_header, print_transcript, use_console
    if use_console(plain):
        print_header(record)
        print_transcript(record)
    else:
        print(render_txt(record))


def _cmd_latest(args: argparse.Namespace) -> int:
    """Analyze the most recent VoiceInk dictation(s) and print the annotated transcripts."""
    from .voiceink import VOICEINK_STORE, latest_dictations

    store = args.store if args.store else VOICEINK_STORE
    if not store.exists():
        print(f"VoiceInk store not found: {store}", file=sys.stderr)
        return 1
    try:
        dictations = latest_dictations(store, args.n)
    except (sqlite3.Error, OSError) as e:
        print(f"could not read the VoiceInk store ({e})", file=sys.stderr)
        return 1
    if not dictations:
        print("no transcriptions in the VoiceInk store", file=sys.stderr)
        return 1

    profile_path = (args.profile if args.profile
                    else Path(__file__).resolve().parent.parent / "speaker-profile.json")
    profile = None
    if profile_path.exists():
        profile = json.loads(profile_path.read_text(encoding="utf-8"))
    else:
        print(f"speaker profile not found at {profile_path}, baseline comparison off",
              file=sys.stderr)
    out_dir = args.out if args.out else Path(tempfile.mkdtemp(prefix="prosodi-latest-"))

    wrote_any = False
    for d in dictations:
        stamp = datetime.fromtimestamp(d.timestamp).strftime("%Y-%m-%d %H:%M:%S")
        name = d.wav.name if d.wav else "(no audio path)"
        print(f"=== {stamp}  {name} ===")
        if d.wav is None or not d.wav.exists():
            print("[audio missing (VoiceInk purged it?), plain stored transcript follows]")
            print(d.text)
            print()
            continue
        try:
            record = analyze_file(str(d.wav), DEFAULT,
                                  reference_transcript=d.text, profile=profile)
        except Exception as e:  # zero-sample wav, unreadable audio: degrade to the stored text
            print(f"[audio analysis failed ({e}), plain stored transcript follows]")
            print(d.text)
            print()
            continue
        jpath, tpath = _out_paths(d.wav, out_dir)
        jpath.write_text(json.dumps(record, ensure_ascii=False, indent=1), encoding="utf-8")
        tpath.write_text(render_txt(record), encoding="utf-8")
        wrote_any = True
        _show(record, args.plain)
    if wrote_any:
        print(f"outputs in {out_dir}", file=sys.stderr)
    return 0


def _load_tsv(path: Path) -> dict[str, str]:
    out = {}
    with open(path, newline="", encoding="utf-8") as f:
        for row in csv.reader(f, delimiter="\t"):
            if len(row) >= 2:
                out[row[0]] = row[1]
    return out


def main(argv: list[str] | None = None) -> int:
    ap = argparse.ArgumentParser(prog="prosodi",
                                 description="Annotate dictation audio with prosody markers.")
    sub = ap.add_subparsers(dest="cmd", required=True)

    a = sub.add_parser("analyze", help="analyze one wav")
    a.add_argument("wav", type=Path)
    a.add_argument("--transcript", type=Path, default=None,
                   help="reference transcript txt, stored in the JSON for comparison")
    a.add_argument("--profile", type=Path, default=None,
                   help="speaker profile json (from prosodi profile) to compare against")
    a.add_argument("--out", type=Path, default=None, help="output dir (default: next to the wav)")
    a.add_argument("--plain", action="store_true",
                   help="plain notation output (the .prosodi.txt format), no color "
                        "(automatic when stdout is not a tty)")

    b = sub.add_parser("batch", help="analyze every wav in a dir")
    b.add_argument("dir", type=Path)
    b.add_argument("--transcripts-tsv", type=Path, default=None,
                   help="uuid TAB transcript file, matched by wav stem")
    b.add_argument("--profile", type=Path, default=None,
                   help="speaker profile json (from prosodi profile) to compare against")
    b.add_argument("--out", type=Path, default=None, help="output dir (default: next to the wavs)")

    L = sub.add_parser("latest", help="analyze the most recent VoiceInk dictation(s) "
                                      "(the store and the wavs are read only)")
    L.add_argument("--n", type=int, default=1, help="how many recent dictations (default 1)")
    L.add_argument("--store", type=Path, default=None,
                   help="VoiceInk default.store path (default: the app's data dir)")
    L.add_argument("--profile", type=Path, default=None,
                   help="speaker profile json (default: speaker-profile.json in the repo root)")
    L.add_argument("--out", type=Path, default=None,
                   help="output dir for .prosodi.json/.txt (default: a fresh temp dir, "
                        "never next to the original wavs)")
    L.add_argument("--plain", action="store_true",
                   help="plain notation output (the .prosodi.txt format), no color "
                        "(automatic when stdout is not a tty)")

    r = sub.add_parser("roundtrip", help="analyze, compile say markup, render: "
                                         "original + prosody + control wavs per sample")
    r.add_argument("input", type=Path, nargs="?", default=None,
                   help="a wav or a directory of wavs (default: the newest VoiceInk dictation)")
    r.add_argument("--n", type=int, default=1,
                   help="how many recent dictations when no input is given (default 1)")
    r.add_argument("--out", type=Path, default=None,
                   help="output root, one subdir per sample (default: a fresh temp dir)")
    r.add_argument("--target", default="f5",
                   help="synthesis target(s), comma-separated: f5, say, elevenlabs "
                        "(default: f5, the cloned voice. say is kept as the rhythm "
                        "yardstick). Each writes <target>-prosody.wav and "
                        "<target>-control.wav per sample")
    r.add_argument("--ref-audio", type=Path, default=None,
                   help="f5 only: reference voice clip to clone (default: "
                        "<repo>/voice-ref.wav when present, else the longest "
                        "3-12 s wav in PROSODI_REF_DIR)")
    r.add_argument("--pitch", action="store_true",
                   help="re-enable the pbas pitch hints (off by default, "
                        "they produce audible semitone jumps)")
    r.add_argument("--store", type=Path, default=None,
                   help="VoiceInk default.store path (default: the app's data dir)")
    r.add_argument("--profile", type=Path, default=None,
                   help="speaker profile json (default: speaker-profile.json in the repo root)")
    r.add_argument("--plain", action="store_true",
                   help="plain notation output (the .prosodi.txt format), no color "
                        "(automatic when stdout is not a tty)")

    v = sub.add_parser("verify", help="score a rendered wav against the original: "
                                      "what each marker class preserved (never a gate, "
                                      "always exits 0)")
    v.add_argument("original", type=Path, help="the original recording")
    v.add_argument("render", type=Path, help="the synthesized rendering to score")
    v.add_argument("--json", action="store_true", dest="as_json",
                   help="machine-readable scorecard on stdout instead of the table")

    s = sub.add_parser("serve", help="launch the local web app (browser UI over the "
                                     "pipeline; needs the web + synth dependency groups)")
    s.add_argument("--host", default="127.0.0.1", help="bind host (default 127.0.0.1)")
    s.add_argument("--port", type=int, default=8000, help="bind port (default 8000)")

    p = sub.add_parser("profile", help="build a speaker profile over every wav in a dir "
                                       "(parselmouth only, the dir is read only)")
    p.add_argument("dir", type=Path)
    p.add_argument("--transcripts-tsv", type=Path, default=None,
                   help="stem TAB transcript file, needed for the rate (wps/cps) stats")
    p.add_argument("--out", type=Path, default=Path("speaker-profile.json"))

    args = ap.parse_args(argv)

    if args.cmd == "latest":
        return _cmd_latest(args)

    if args.cmd == "roundtrip":
        from .roundtrip import run_roundtrip
        return run_roundtrip(args)

    if args.cmd == "verify":
        from .verify import run_verify
        return run_verify(args)

    if args.cmd == "serve":
        repo_root = str(Path(__file__).resolve().parent.parent)
        if repo_root not in sys.path:
            sys.path.insert(0, repo_root)
        try:
            import uvicorn
            from web.server.app import app
        except ImportError as e:
            print(f"the web app needs the web dependency group: "
                  f"uv sync --group web --group synth  ({e})", file=sys.stderr)
            return 1
        print(f"prosodi web app on http://{args.host}:{args.port}", file=sys.stderr)
        uvicorn.run(app, host=args.host, port=args.port, log_level="info")
        return 0

    if args.cmd == "profile":
        from .profile import build_profile
        refs = _load_tsv(args.transcripts_tsv) if args.transcripts_tsv else {}
        prof = build_profile(args.dir, refs, DEFAULT)
        args.out.write_text(json.dumps(prof, ensure_ascii=False, indent=1), encoding="utf-8")
        f = prof["files"]
        print(f"profile over {f['ok']}/{f['total']} files ({f['failed']} failed, "
              f"{f['with_transcript']} with transcript) -> {args.out}", file=sys.stderr)
        return 0

    profile = json.loads(args.profile.read_text(encoding="utf-8")) if args.profile else None

    if args.cmd == "analyze":
        transcript = args.transcript.read_text(encoding="utf-8").strip() if args.transcript else None
        record = _analyze_one(args.wav, args.out, transcript, profile)
        _show(record, args.plain)
        return 0

    refs = _load_tsv(args.transcripts_tsv) if args.transcripts_tsv else {}
    wavs = sorted(args.dir.glob("*.wav"))
    if not wavs:
        print(f"no wavs in {args.dir}", file=sys.stderr)
        return 1
    failures = 0
    for wav in wavs:
        try:
            _analyze_one(wav, args.out, refs.get(wav.stem), profile)
        except Exception as e:  # keep the batch going, report at the end
            failures += 1
            print(f"{wav.name}: FAILED ({e})", file=sys.stderr)
    if failures:
        print(f"{failures} file(s) failed", file=sys.stderr)
    return 1 if failures else 0


if __name__ == "__main__":
    sys.exit(main())

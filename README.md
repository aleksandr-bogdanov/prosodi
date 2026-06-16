# prosodi

**Speech to text, without losing the speech.**

When you talk to your computer and it writes down what you said, it keeps the words and throws
away how you said them. The long pause before you changed your mind. The word you leaned on. The
way your voice rose into a question, or dropped once you had decided. Read the transcript back later
and it all sounds flat and certain, even where you were really hesitating.

prosodi keeps that part. Give it a voice recording and it writes the words back with the delivery
marked in: where you paused and for how long, which words you stressed, where you slowed down or
sped up, where your pitch rose or fell. It can also clone your voice and read the result back, so
you can hear how close a copy gets to the real thing.

Everything runs on your own machine. No recording is ever uploaded anywhere.

## What you can do with it

prosodi is a small website you run on your own computer. Open it and there are three things to try.

- **Annotate.** Drop in a recording and see your delivery written into the transcript: the pauses
  as little markers, the stressed words in colour, the drawled words, the rises and falls. Then, if
  you want, let it clone your voice and read the same words back, with a scorecard showing how much
  of your delivery the copy kept.
- **Guess yourself.** Read a few short passages out loud. prosodi clones your voice and plays you a
  lineup of takes, all the same words: a few copies and the real you. See if you can pick yourself.
- **Showcase.** A handful of clean public-domain recordings, already cloned and scored, so you can
  hear the idea without recording anything yourself.

## Start it

You need a Mac with Apple Silicon. [uv](https://docs.astral.sh/uv/) runs the Python side and
[bun](https://bun.sh/) builds the web page.

```sh
uv sync --group web --group synth
cd web/app && bun install && bun run build && cd ../..
uv run prosodi serve
```

Then open <http://localhost:8000>. The first run downloads the speech models (a few hundred MB) and
takes a minute. You also need `ffmpeg` (`brew install ffmpeg`) for handling audio.

## How it works (the short version)

prosodi does not guess. It measures. It lines each word up with the exact moment you said it, then
measures the real sound around it: the silences, the pitch, the loudness, the speed. Every mark in
the transcript comes from those measurements, compared against your own ordinary voice, so the same
recording always reads the same way. There is no AI deciding what you "probably" felt.

The one part that does use a neural model is the voice cloning, and only when you ask to hear a
recording read back in a voice.

## What it can't do

- It only measures what is actually in the sound: timing, pitch, stress, speed. It does not read
  emotion or sarcasm, and it never judges what you meant. That is left to the reader.
- It leans on a transcription step to catch your words. Where that mishears you, the marks land on
  the wrong words.
- The voice clone is close but not perfect. It catches your pauses and the sound of your voice, but
  it still reads the words a little faster than you do.

## For developers

The web app is a FastAPI backend (`web/server`) wrapping the pipeline behind a job queue, and a
Vite + React + Tailwind v4 frontend (`web/app`). The command-line tool is the same pipeline without
the browser:

```sh
uv run prosodi analyze recording.wav            # annotated transcript + a JSON record
uv run prosodi verify original.wav render.wav   # score a render against the original
uv run prosodi serve                            # the web app
```

Develop the frontend with hot reload (it proxies the API to the running backend):

```sh
uv run prosodi serve                  # backend on :8000
cd web/app && bun run dev             # frontend on :5173
```

Rebuild the showcase assets (downloads public-domain clips, clones and scores them) with
`uv run --group web --group synth python web/build_examples.py`.

- `prosodi/config.py` holds every threshold, each one relative to the speaker's own baseline.
- `prosodi/render.py` owns the notation, `prosodi/backends.py` owns the voice synthesis.
- `EVAL.md` is the run over a public-domain corpus, and `web/app/HOUSE-STYLE.md` is the design
  system the app is built on.

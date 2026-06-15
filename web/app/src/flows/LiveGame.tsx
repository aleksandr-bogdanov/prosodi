import { useState } from "react";
import { motion } from "framer-motion";
import Recorder from "../components/Recorder";
import JobProgress from "../components/JobProgress";
import GuessGame from "../components/GuessGame";
import MarkerText from "../components/MarkerText";
import * as api from "../lib/api";
import type { GameResult } from "../lib/types";

// ~20s of voice is plenty: f5 needs about 12s for the reference, and this leaves a
// target to compare. The bold words cue where to lean in, so even a flat reader
// produces emphasis the notation can catch (and the clone can inherit).
const PASSAGES: React.ReactNode[] = [
  <>
    When the <strong>sunlight</strong> strikes raindrops in the air, they act as a{" "}
    <strong>prism</strong> and form a <strong>rainbow</strong>, a division of white light
    into <strong>many</strong> beautiful colors. It takes the shape of a long round arch,
    with its two ends apparently <strong>beyond</strong> the horizon.
  </>,
];

type Stage = "intro" | "processing" | "game";

export default function LiveGame() {
  const [stage, setStage] = useState<Stage>("intro");
  const [busy, setBusy] = useState<{ p: number; msg: string }>({ p: 0, msg: "" });
  const [game, setGame] = useState<GameResult | null>(null);
  const [err, setErr] = useState<string | null>(null);

  async function onRecorded(file: File) {
    setErr(null);
    setStage("processing");
    setBusy({ p: 0, msg: "uploading your read" });
    try {
      const res = await api.startGame({ file, nClones: 3 }, (p, msg) => setBusy({ p, msg }));
      setGame(res);
      setStage("game");
    } catch (e) {
      setErr(String(e));
      setStage("intro");
    }
  }

  return (
    <div className="space-y-8">
      {stage === "intro" && (
        <div className="card p-7">
          <div className="eyebrow mb-3">read this aloud</div>
          <div className="mb-7 space-y-4">
            {PASSAGES.map((p, i) => (
              <p key={i} className="text-lg leading-relaxed text-ink">{p}</p>
            ))}
          </div>
          <Recorder onComplete={onRecorded} minSeconds={18} />
          <p className="mt-6 text-center font-mono text-xs text-ink-faint">
            ~20s of clean voice. Lean on the <strong>bold</strong> words. Then we clone you
            and you pick yourself out of the copies.
          </p>
          {err && (
            <div className="mt-4 text-center text-sm" style={{ color: "var(--color-m-agitated)" }}>
              {err}
            </div>
          )}
        </div>
      )}

      {stage === "processing" && (
        <div className="card p-8">
          <JobProgress progress={busy.p} message={busy.msg} />
          <p className="mt-4 text-center text-sm text-ink-soft">
            Measuring your prosody and rendering the clones — about a minute.
          </p>
        </div>
      )}

      {stage === "game" && game && (
        <motion.div initial={{ opacity: 0, y: 12 }} animate={{ opacity: 1, y: 0 }} className="space-y-8">
          <div className="card p-7">
            <div className="eyebrow mb-4">which one is really you?</div>
            <GuessGame
              items={game.items}
              targetText={game.target_text}
              onReveal={async () => (await api.revealGame(game.game_id)).truth}
            />
          </div>
          <div className="card p-6">
            <div className="eyebrow mb-4">what we measured in your read</div>
            <MarkerText view={game.view} />
          </div>
          <div className="text-center">
            <button
              className="btn btn-ghost"
              onClick={() => {
                setGame(null);
                setStage("intro");
              }}
            >
              Try again
            </button>
          </div>
        </motion.div>
      )}
    </div>
  );
}

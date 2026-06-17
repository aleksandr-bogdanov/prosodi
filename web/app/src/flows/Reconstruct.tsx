import { useEffect, useState } from "react";
import { motion } from "framer-motion";
import JobProgress from "../components/JobProgress";
import AudioPlayer from "../components/AudioPlayer";
import ScoreCard from "../components/ScoreCard";
import * as api from "../lib/api";
import type { ReconstructResult, Voice } from "../lib/types";

const PLACEHOLDER = `Type a line, or add prosody markers:
I genuinely <pause 0.6s> don't know what to *tell* you.`;

// A worked example so the box is never blank: pauses, emphasis and a stretch,
// the markers Reconstruct actually imposes on f5.
const DEFAULT_NOTATION =
  "So <pause 0.7s> here is the whole idea. " +
  "I *measure* how you speak <pause 0.4s> the pauses, the tempo, the stress, <pause 0.4s> " +
  "and write<stretched 1.6x> it all down. " +
  "Then <pause 0.5s> any voice can read it back.";

/** Module 2: prosodi notation (typed or carried from Capture) -> voice -> audio. */
export default function Reconstruct({
  voice,
  seed,
  seedKey,
  onGoToVoices,
}: {
  voice: Voice | null;
  seed: { notation: string; sessionId: string } | null;
  seedKey: number;
  onGoToVoices: () => void;
}) {
  const [notation, setNotation] = useState(DEFAULT_NOTATION);
  const [sessionId, setSessionId] = useState<string | null>(null);
  const [busy, setBusy] = useState<{ p: number; msg: string } | null>(null);
  const [res, setRes] = useState<ReconstructResult | null>(null);
  const [err, setErr] = useState<string | null>(null);

  // load a capture handoff when one arrives (keyed so edits don't re-trigger it)
  useEffect(() => {
    if (seed) {
      setNotation(seed.notation);
      setSessionId(seed.sessionId);
      setRes(null);
      setErr(null);
    }
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [seedKey]);

  async function render() {
    if (!voice || !notation.trim()) return;
    setErr(null);
    setRes(null);
    setBusy({ p: 0, msg: "starting" });
    try {
      setRes(
        await api.reconstruct(notation, voice.id, sessionId, (p, msg) => setBusy({ p, msg })),
      );
    } catch (e) {
      setErr(String(e));
    } finally {
      setBusy(null);
    }
  }

  if (!voice) {
    return (
      <div className="card p-10 text-center">
        <div className="eyebrow mb-3">no voice selected</div>
        <p className="mb-5 text-ink-soft">
          Pick or create a voice first, then reconstruct any prosodi notation in their voice.
        </p>
        <button className="btn btn-primary" onClick={onGoToVoices}>
          Go to voices
        </button>
      </div>
    );
  }

  return (
    <div className="space-y-8">
      <div className="flex items-center justify-between gap-3">
        <p className="text-sm text-ink-soft">
          Rendering in <span style={{ color: "var(--color-accent)" }}>{voice.name}</span>'s voice.
          {sessionId
            ? " From your capture - edit the notation if you like."
            : " Type notation, or capture a recording first."}
        </p>
        <button className="font-mono text-xs text-ink-faint hover:text-accent" onClick={onGoToVoices}>
          change voice
        </button>
      </div>

      <div className="card space-y-3 p-6">
        <div className="flex items-center justify-between">
          <div className="eyebrow">notation</div>
          {sessionId && (
            <button
              className="font-mono text-xs text-ink-faint hover:text-accent"
              onClick={() => setSessionId(null)}
              title="drop the captured original (treat as typed, no scorecard)"
            >
              detach capture
            </button>
          )}
        </div>
        <textarea
          className="w-full rounded-xl border border-line bg-transparent p-3 font-mono text-sm leading-relaxed text-ink focus:border-accent focus:outline-none"
          style={{ minHeight: "8rem" }}
          value={notation}
          onChange={(e) => setNotation(e.target.value)}
          placeholder={PLACEHOLDER}
          spellCheck={false}
        />
        <div className="flex items-center justify-between gap-3">
          <span className="font-mono text-xs text-ink-faint">
            markers: &lt;pause 0.6s&gt; · *emphasis* · word&lt;stretched 1.8x&gt;
          </span>
          <button className="btn btn-primary" disabled={!!busy || !notation.trim()} onClick={render}>
            {busy ? "rendering..." : "Render"}
          </button>
        </div>
      </div>

      {busy && (
        <div className="card p-6">
          <JobProgress progress={busy.p} message={busy.msg} />
        </div>
      )}
      {err && (
        <div className="card p-4 text-sm" style={{ color: "var(--color-m-agitated)" }}>
          {err}
        </div>
      )}

      {res && (
        <motion.div
          initial={{ opacity: 0, y: 12 }}
          animate={{ opacity: 1, y: 0 }}
          className="space-y-6"
        >
          {res.original_url && (
            <div className="card space-y-3 p-6">
              <div className="eyebrow">the original</div>
              <AudioPlayer url={res.original_url} label="original" />
            </div>
          )}
          <div className={`grid gap-6 ${res.models.length > 1 ? "lg:grid-cols-2" : ""}`}>
            {res.models.map((m, i) => (
              <div key={i} className="card space-y-4 p-6">
                <div className="eyebrow">{m.name}</div>
                <AudioPlayer url={m.render_url} label="reconstructed" />
                {m.scorecard && <ScoreCard card={m.scorecard} />}
              </div>
            ))}
          </div>
        </motion.div>
      )}
    </div>
  );
}

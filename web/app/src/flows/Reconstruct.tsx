import { useState } from "react";
import { motion } from "framer-motion";
import Dropzone from "../components/Dropzone";
import JobProgress from "../components/JobProgress";
import AudioPlayer from "../components/AudioPlayer";
import MarkerText, { MarkerLegend } from "../components/MarkerText";
import ScoreCard from "../components/ScoreCard";
import * as api from "../lib/api";
import type { ReconstructResult, Voice } from "../lib/types";

export default function Reconstruct({
  voice,
  onGoToVoices,
}: {
  voice: Voice | null;
  onGoToVoices: () => void;
}) {
  const [busy, setBusy] = useState<{ p: number; msg: string } | null>(null);
  const [res, setRes] = useState<ReconstructResult | null>(null);
  const [err, setErr] = useState<string | null>(null);

  async function onFile(f: File) {
    if (!voice) return;
    setErr(null);
    setRes(null);
    setBusy({ p: 0, msg: "uploading" });
    try {
      setRes(await api.reconstruct(f, voice.id, (p, msg) => setBusy({ p, msg })));
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
          Pick or create a voice first. Then drop any clip of that person and hear it
          rebuilt in their voice from the measured prosody.
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
          Rebuilding in <span style={{ color: "var(--color-accent)" }}>{voice.name}</span>'s
          voice. Drop a clip of the same person.
        </p>
        <button className="font-mono text-xs text-ink-faint hover:text-accent" onClick={onGoToVoices}>
          change voice
        </button>
      </div>

      {!res && !busy && <Dropzone onFile={onFile} />}
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
        <motion.div initial={{ opacity: 0, y: 12 }} animate={{ opacity: 1, y: 0 }} className="space-y-6">
          <div className="grid gap-6 lg:grid-cols-2">
            <div className="card space-y-4 p-6">
              <div className="eyebrow">listen</div>
              <AudioPlayer url={res.original_url} label="original" />
              <AudioPlayer url={res.render_url} label={`reconstructed · ${voice.name}`} />
              <button className="font-mono text-xs text-ink-faint hover:text-accent" onClick={() => setRes(null)}>
                another clip
              </button>
            </div>
            <ScoreCard card={res.scorecard} />
          </div>
          <div className="card p-6">
            <div className="eyebrow mb-4">what we measured</div>
            <MarkerText view={res.view} />
            <div className="mt-5 border-t border-line-soft pt-4">
              <MarkerLegend />
            </div>
          </div>
        </motion.div>
      )}
    </div>
  );
}

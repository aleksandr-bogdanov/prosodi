import { useState } from "react";
import { motion } from "framer-motion";
import Dropzone from "../components/Dropzone";
import Recorder from "../components/Recorder";
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
  const [mode, setMode] = useState<"record" | "upload">("record");

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

      {!res && !busy && (
        <div className="card p-6">
          <div className="mb-6 flex justify-center gap-2">
            <button
              className={`btn text-sm ${mode === "record" ? "btn-primary" : ""}`}
              onClick={() => setMode("record")}
            >
              Record
            </button>
            <button
              className={`btn text-sm ${mode === "upload" ? "btn-primary" : ""}`}
              onClick={() => setMode("upload")}
            >
              Upload
            </button>
          </div>
          {mode === "record" ? (
            <>
              <Recorder onComplete={onFile} minSeconds={3} />
              <p className="mx-auto mt-5 max-w-md text-center text-xs text-ink-faint">
                Say a line the way you'd really say it — pauses, hesitations, tempo and all.
                We measure your prosody, then rebuild it in{" "}
                <span style={{ color: "var(--color-accent)" }}>{voice.name}</span>'s voice.
              </p>
            </>
          ) : (
            <Dropzone onFile={onFile} />
          )}
        </div>
      )}
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
          <div className="card space-y-3 p-6">
            <div className="flex items-center justify-between">
              <div className="eyebrow">the original</div>
              <button className="font-mono text-xs text-ink-faint hover:text-accent" onClick={() => setRes(null)}>
                another clip
              </button>
            </div>
            <AudioPlayer url={res.original_url} label="original" />
          </div>

          <div className={`grid gap-6 ${res.models.length > 1 ? "lg:grid-cols-2" : ""}`}>
            {res.models.map((m, i) => (
              <div key={i} className="card space-y-4 p-6">
                <div className="eyebrow">{m.name}</div>
                <AudioPlayer url={m.render_url} label="reconstructed" />
                <ScoreCard card={m.scorecard} />
              </div>
            ))}
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

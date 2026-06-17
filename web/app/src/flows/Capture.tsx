import { useState } from "react";
import { motion } from "framer-motion";
import Dropzone from "../components/Dropzone";
import Recorder from "../components/Recorder";
import JobProgress from "../components/JobProgress";
import AudioPlayer from "../components/AudioPlayer";
import MarkerText, { MarkerLegend } from "../components/MarkerText";
import * as api from "../lib/api";
import type { AnalyzeResult } from "../lib/types";

/** Module 1: audio in -> measured prosody as editable notation, handed to Reconstruct. */
export default function Capture({
  onReconstruct,
}: {
  onReconstruct: (notation: string, sessionId: string) => void;
}) {
  const [busy, setBusy] = useState<{ p: number; msg: string } | null>(null);
  const [res, setRes] = useState<AnalyzeResult | null>(null);
  const [notation, setNotation] = useState("");
  const [mode, setMode] = useState<"record" | "upload">("record");
  const [err, setErr] = useState<string | null>(null);

  async function onFile(f: File) {
    setErr(null);
    setRes(null);
    setBusy({ p: 0, msg: "uploading" });
    try {
      const r = await api.analyze(f, false, (p, msg) => setBusy({ p, msg }));
      setRes(r);
      setNotation(r.view.notation);
    } catch (e) {
      setErr(String(e));
    } finally {
      setBusy(null);
    }
  }

  return (
    <div className="space-y-8">
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
                Say a line the way you'd really say it - the pauses, the tempo, the emphasis.
                We measure them and write them into the transcript as notation you can edit.
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
        <motion.div
          initial={{ opacity: 0, y: 12 }}
          animate={{ opacity: 1, y: 0 }}
          className="space-y-6"
        >
          <div className="card space-y-3 p-6">
            <div className="flex items-center justify-between">
              <div className="eyebrow">what you said</div>
              <button
                className="font-mono text-xs text-ink-faint hover:text-accent"
                onClick={() => {
                  setRes(null);
                  setNotation("");
                }}
              >
                another take
              </button>
            </div>
            <AudioPlayer url={res.audio_url} label="original" />
          </div>

          <div className="card space-y-4 p-6">
            <div className="eyebrow">the prosody, measured</div>
            <MarkerText view={res.view} />
            <div className="border-t border-line-soft pt-4">
              <MarkerLegend />
            </div>
          </div>

          <div className="card space-y-3 p-6">
            <div className="flex items-center justify-between">
              <div className="eyebrow">notation</div>
              <span className="font-mono text-xs text-ink-faint">edit before reconstructing</span>
            </div>
            <textarea
              className="w-full rounded-xl border border-line bg-transparent p-3 font-mono text-sm leading-relaxed text-ink focus:border-accent focus:outline-none"
              style={{ minHeight: "9rem" }}
              value={notation}
              onChange={(e) => setNotation(e.target.value)}
              spellCheck={false}
            />
            <div className="flex justify-end">
              <button
                className="btn btn-primary"
                disabled={!notation.trim()}
                onClick={() => onReconstruct(notation, res.session_id)}
              >
                Reconstruct in a voice →
              </button>
            </div>
          </div>
        </motion.div>
      )}
    </div>
  );
}

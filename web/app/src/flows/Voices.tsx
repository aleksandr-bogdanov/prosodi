import { useState } from "react";
import { motion } from "framer-motion";
import Dropzone from "../components/Dropzone";
import JobProgress from "../components/JobProgress";
import AudioPlayer from "../components/AudioPlayer";
import RegionPicker from "../components/RegionPicker";
import * as api from "../lib/api";
import type { Voice } from "../lib/types";

export default function Voices({
  voices,
  activeId,
  onSelect,
  onChange,
}: {
  voices: Voice[];
  activeId: string | null;
  onSelect: (id: string) => void;
  onChange: () => void;
}) {
  const [pending, setPending] = useState<File | null>(null);
  const [name, setName] = useState("");
  const [region, setRegion] = useState<{ start: number; end: number } | null>(null);
  const [busy, setBusy] = useState<{ p: number; msg: string } | null>(null);
  const [err, setErr] = useState<string | null>(null);

  async function create() {
    if (!pending) return;
    setErr(null);
    setBusy({ p: 0, msg: "uploading" });
    try {
      const v = await api.createVoice(
        pending,
        name.trim() || pending.name,
        region,
        (p, msg) => setBusy({ p, msg }),
      );
      setPending(null);
      setName("");
      setRegion(null);
      onChange();
      onSelect(v.id);
    } catch (e) {
      setErr(String(e));
    } finally {
      setBusy(null);
    }
  }

  return (
    <div className="space-y-8">
      <div className="card p-6">
        <div className="eyebrow mb-2">new voice</div>
        <p className="mb-5 text-sm text-ink-soft">
          Drop an audio or video file of one person talking. prosodi pulls the cleanest
          ~12 seconds, saves it as a reusable voice, and you clone any clip of that person
          with it. About 12 seconds of clear speech is all it needs.
        </p>

        {!pending && !busy && <Dropzone onFile={setPending} />}

        {pending && !busy && (
          <div className="space-y-4">
            <RegionPicker file={pending} onRegion={setRegion} />
            <div className="flex flex-col gap-3 sm:flex-row sm:items-center">
              <input
                value={name}
                onChange={(e) => setName(e.target.value)}
                placeholder={`name this voice (e.g. ${pending.name.replace(/\.[^.]+$/, "")})`}
                className="flex-1 rounded-lg border border-line bg-surface px-3.5 py-2.5 text-sm outline-none focus:border-accent"
                onKeyDown={(e) => e.key === "Enter" && create()}
                autoFocus
              />
              <div className="flex gap-2">
                <button className="btn btn-primary" onClick={create}>
                  Save voice
                </button>
                <button className="btn btn-ghost" onClick={() => { setPending(null); setRegion(null); }}>
                  Cancel
                </button>
              </div>
            </div>
          </div>
        )}

        {busy && <JobProgress progress={busy.p} message={busy.msg} />}
        {err && (
          <div className="mt-3 text-sm" style={{ color: "var(--color-m-agitated)" }}>
            {err}
          </div>
        )}
      </div>

      {voices.length > 0 && (
        <div className="space-y-3">
          <div className="eyebrow">saved voices</div>
          {voices.map((v) => (
            <motion.div
              key={v.id}
              initial={{ opacity: 0, y: 8 }}
              animate={{ opacity: 1, y: 0 }}
              onClick={() => onSelect(v.id)}
              className="card cursor-pointer p-4 transition-colors"
              style={{
                borderColor: v.id === activeId ? "var(--color-accent)" : "var(--color-line)",
              }}
            >
              <div className="mb-3 flex items-center justify-between gap-3">
                <div className="flex items-center gap-2.5">
                  <span
                    className="grid h-5 w-5 place-items-center rounded-full border"
                    style={{
                      borderColor: v.id === activeId ? "var(--color-accent)" : "var(--color-line)",
                      background: v.id === activeId ? "var(--color-accent)" : "transparent",
                    }}
                  >
                    {v.id === activeId && (
                      <svg width="11" height="11" viewBox="0 0 24 24" fill="none" stroke="var(--color-accent-ink)" strokeWidth="3" strokeLinecap="round" strokeLinejoin="round">
                        <path d="M20 6 9 17l-5-5" />
                      </svg>
                    )}
                  </span>
                  <span className="font-medium">{v.name}</span>
                  <span className="chip">{v.ref_s}s ref</span>
                  {v.id === activeId && (
                    <span className="font-mono text-xs" style={{ color: "var(--color-accent)" }}>
                      active
                    </span>
                  )}
                </div>
                <button
                  className="font-mono text-xs text-ink-faint hover:text-[var(--color-m-agitated)]"
                  onClick={(e) => {
                    e.stopPropagation();
                    api.deleteVoice(v.id).then(onChange);
                  }}
                >
                  delete
                </button>
              </div>
              <AudioPlayer url={v.ref_url} label="reference" compact />
            </motion.div>
          ))}
        </div>
      )}
    </div>
  );
}

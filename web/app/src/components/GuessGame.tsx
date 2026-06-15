import { useState } from "react";
import { motion } from "framer-motion";
import AudioPlayer from "./AudioPlayer";
import type { GameItem } from "../lib/types";

type Truth = Record<string, { is_real: boolean; label: string }>;

export default function GuessGame({
  items,
  targetText,
  onReveal,
}: {
  items: GameItem[];
  targetText?: string;
  onReveal: () => Promise<Truth>;
}) {
  const [picked, setPicked] = useState<string | null>(null);
  const [truth, setTruth] = useState<Truth | null>(null);

  const reveal = async () => setTruth(await onReveal());
  const correct = truth && picked && truth[picked]?.is_real;

  return (
    <div>
      {targetText && (
        <p className="mb-6 text-center text-sm italic text-ink-soft">"{targetText}"</p>
      )}
      <div className="grid gap-3 sm:grid-cols-2">
        {items.map((it, i) => {
          const isReal = truth?.[it.id]?.is_real;
          const isPicked = picked === it.id;
          let ring = "var(--color-line)";
          let tag: string | null = null;
          let tagColor = "var(--color-ink-faint)";
          if (truth) {
            if (isReal) {
              ring = "var(--color-m-rise)";
              tag = "the human";
              tagColor = "var(--color-m-rise)";
            } else if (isPicked) {
              ring = "var(--color-m-agitated)";
              tag = "clone";
              tagColor = "var(--color-m-agitated)";
            } else {
              tag = "clone";
            }
          } else if (isPicked) {
            ring = "var(--color-accent)";
          }
          return (
            <motion.div
              key={it.id}
              whileHover={truth ? {} : { y: -2 }}
              onClick={() => !truth && setPicked(it.id)}
              className="rounded-xl border p-4 transition-colors"
              style={{
                borderColor: ring,
                cursor: truth ? "default" : "pointer",
                background: isPicked && !truth
                  ? "color-mix(in oklab, var(--color-accent) 6%, var(--color-surface))"
                  : "var(--color-surface)",
              }}
            >
              <div className="mb-2 flex items-center justify-between">
                <span className="font-mono text-xs text-ink-faint">#{i + 1}</span>
                {tag && (
                  <span className="font-mono text-xs" style={{ color: tagColor }}>
                    {tag}
                  </span>
                )}
                {!truth && (
                  <span
                    className="grid h-5 w-5 place-items-center rounded-full border"
                    style={{
                      borderColor: isPicked ? "var(--color-accent)" : "var(--color-line)",
                      background: isPicked ? "var(--color-accent)" : "transparent",
                    }}
                  >
                    {isPicked && (
                      <svg width="11" height="11" viewBox="0 0 24 24" fill="none" stroke="var(--color-accent-ink)" strokeWidth="3" strokeLinecap="round" strokeLinejoin="round">
                        <path d="M20 6 9 17l-5-5" />
                      </svg>
                    )}
                  </span>
                )}
              </div>
              <AudioPlayer url={it.url} compact accent={truth && isReal ? "var(--color-m-rise)" : undefined} />
            </motion.div>
          );
        })}
      </div>

      <div className="mt-6 text-center">
        {!truth ? (
          <button className="btn btn-primary" disabled={!picked} onClick={reveal}>
            {picked ? "Reveal which is the human" : "Pick the real human voice"}
          </button>
        ) : (
          <motion.div
            initial={{ opacity: 0, y: 8 }}
            animate={{ opacity: 1, y: 0 }}
            className="text-lg font-medium"
            style={{ color: correct ? "var(--color-m-rise)" : "var(--color-m-agitated)" }}
          >
            {correct ? "Right — that was the human take." : "Nope, that one was a clone."}
          </motion.div>
        )}
      </div>
    </div>
  );
}

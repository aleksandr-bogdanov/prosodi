import { useEffect, useState } from "react";
import { AnimatePresence, motion } from "framer-motion";
import { useTheme } from "./lib/theme";
import Voices from "./flows/Voices";
import Capture from "./flows/Capture";
import Reconstruct from "./flows/Reconstruct";
import LiveGame from "./flows/LiveGame";
import * as api from "./lib/api";
import type { Voice } from "./lib/types";

type Tab = "voices" | "capture" | "reconstruct" | "guess";
const TABS: { id: Tab; label: string; blurb: string }[] = [
  { id: "voices", label: "Voices", blurb: "Drop a recording, keep the voice. ~12 seconds is all it needs." },
  { id: "capture", label: "Capture", blurb: "Record or upload, and read the prosody back as editable notation." },
  { id: "reconstruct", label: "Reconstruct", blurb: "Render notation - captured or typed - in a saved voice." },
  { id: "guess", label: "Guess yourself", blurb: "Read a passage, then pick yourself out of the clones." },
];

function ThemeToggle() {
  const { dark, toggle } = useTheme();
  return (
    <button
      onClick={toggle}
      aria-label="toggle theme"
      className="grid h-9 w-9 place-items-center rounded-full border border-line text-ink-soft transition-colors hover:border-accent hover:text-accent"
    >
      {dark ? (
        <svg width="16" height="16" viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="2" strokeLinecap="round" strokeLinejoin="round">
          <circle cx="12" cy="12" r="4" />
          <path d="M12 2v2M12 20v2M4.9 4.9l1.4 1.4M17.7 17.7l1.4 1.4M2 12h2M20 12h2M4.9 19.1l1.4-1.4M17.7 6.3l1.4-1.4" />
        </svg>
      ) : (
        <svg width="16" height="16" viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="2" strokeLinecap="round" strokeLinejoin="round">
          <path d="M21 12.8A9 9 0 1 1 11.2 3a7 7 0 0 0 9.8 9.8z" />
        </svg>
      )}
    </button>
  );
}

function Wordmark() {
  return (
    <div className="flex items-center gap-2.5">
      <span className="flex h-7 items-end gap-[3px]" aria-hidden>
        {[10, 18, 13, 22, 15].map((h, i) => (
          <motion.span
            key={i}
            className="w-[3px] rounded-full"
            style={{ background: "var(--color-accent)" }}
            animate={{ height: [h, h * 0.5, h] }}
            transition={{ duration: 1.4, repeat: Infinity, delay: i * 0.12, ease: "easeInOut" }}
          />
        ))}
      </span>
      <span className="font-display text-lg font-semibold tracking-tight">prosodi</span>
    </div>
  );
}

export default function App() {
  const [tab, setTab] = useState<Tab>("voices");
  const [voices, setVoices] = useState<Voice[]>([]);
  const [activeId, setActiveId] = useState<string | null>(null);
  const [seed, setSeed] = useState<{ notation: string; sessionId: string } | null>(null);
  const [seedKey, setSeedKey] = useState(0);

  function handoff(notation: string, sessionId: string) {
    setSeed({ notation, sessionId });
    setSeedKey((k) => k + 1);
    setTab("reconstruct");
  }

  const refresh = () =>
    api.listVoices().then((vs) => {
      setVoices(vs);
      setActiveId((cur) => cur ?? (vs[0]?.id ?? null));
    });
  useEffect(() => {
    refresh();
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, []);

  const active = voices.find((v) => v.id === activeId) ?? null;
  const blurb = TABS.find((t) => t.id === tab)!.blurb;

  return (
    <div className="min-h-screen bg-dotgrid">
      <header className="relative z-30 border-b border-line-soft glass">
        <div className="shell flex h-16 items-center justify-between">
          <Wordmark />
          <nav className="hidden items-center gap-1 sm:flex">
            {TABS.map((t) => (
              <button
                key={t.id}
                onClick={() => setTab(t.id)}
                className="relative rounded-full px-4 py-1.5 text-sm transition-colors"
                style={{ color: tab === t.id ? "var(--color-ink)" : "var(--color-ink-soft)" }}
              >
                {tab === t.id && (
                  <motion.span
                    layoutId="tab-pill"
                    className="absolute inset-0 rounded-full"
                    style={{ background: "color-mix(in oklab, var(--color-accent) 12%, transparent)" }}
                    transition={{ type: "spring", stiffness: 380, damping: 30 }}
                  />
                )}
                <span className="relative">{t.label}</span>
              </button>
            ))}
          </nav>
          <ThemeToggle />
        </div>
      </header>

      <section className="shell pt-14 pb-8 sm:pt-20">
        <div className="eyebrow mb-4">speech to text, without losing the speech</div>
        <h1 className="max-w-3xl font-display text-[clamp(2.2rem,6vw,4rem)] font-semibold leading-[1.04] tracking-[-0.02em]">
          The words survive transcription.{" "}
          <span style={{ color: "var(--color-accent)" }}>How you said them</span> usually doesn't.
        </h1>
        <p className="mt-5 max-w-2xl text-lg text-ink-soft">
          prosodi measures the pauses, the emphasis, the drawl, the pitch you actually
          spoke, puts them back into the transcript, and clones a voice to read it back.
          Everything runs locally on this machine.
        </p>
      </section>

      <div className="shell sm:hidden">
        <div className="flex gap-1 overflow-x-auto pb-4">
          {TABS.map((t) => (
            <button
              key={t.id}
              onClick={() => setTab(t.id)}
              className="whitespace-nowrap rounded-full px-4 py-1.5 text-sm"
              style={{
                background: tab === t.id ? "color-mix(in oklab, var(--color-accent) 12%, transparent)" : "transparent",
                color: tab === t.id ? "var(--color-ink)" : "var(--color-ink-soft)",
              }}
            >
              {t.label}
            </button>
          ))}
        </div>
      </div>

      <main className="shell pb-24">
        <p className="mb-6 text-sm text-ink-faint">{blurb}</p>
        <AnimatePresence mode="wait">
          <motion.div
            key={tab}
            initial={{ opacity: 0, y: 10 }}
            animate={{ opacity: 1, y: 0 }}
            exit={{ opacity: 0, y: -8 }}
            transition={{ duration: 0.25, ease: [0.16, 1, 0.3, 1] }}
          >
            {tab === "voices" && (
              <Voices voices={voices} activeId={activeId} onSelect={setActiveId} onChange={refresh} />
            )}
            {tab === "capture" && <Capture onReconstruct={handoff} />}
            {tab === "reconstruct" && (
              <Reconstruct
                voice={active}
                seed={seed}
                seedKey={seedKey}
                onGoToVoices={() => setTab("voices")}
              />
            )}
            {tab === "guess" && <LiveGame />}
          </motion.div>
        </AnimatePresence>
      </main>

      <footer className="border-t border-line-soft">
        <div className="shell flex flex-col gap-2 py-8 text-sm text-ink-faint sm:flex-row sm:items-center sm:justify-between">
          <span>prosodi - deterministic prosody, local f5 cloning, MIT.</span>
          <span className="font-mono text-xs">no audio leaves this machine</span>
        </div>
      </footer>
    </div>
  );
}

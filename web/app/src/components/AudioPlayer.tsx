import { useEffect, useRef, useState } from "react";
import WaveSurfer from "wavesurfer.js";
import { cssVar } from "../lib/theme";

// Only one clip plays at a time across the whole page: starting one pauses the
// rest. Module scope, so every AudioPlayer shares it.
let CURRENT: WaveSurfer | null = null;

interface Props {
  url: string;
  label?: string;
  accent?: string; // CSS colour for the progress fill (defaults to the teal accent)
  compact?: boolean;
  onPlay?: () => void;
}

/** A themed waveform player. Click the wave or the button to play. */
export default function AudioPlayer({ url, label, accent, compact, onPlay }: Props) {
  const container = useRef<HTMLDivElement>(null);
  const ws = useRef<WaveSurfer | null>(null);
  const [playing, setPlaying] = useState(false);
  const [ready, setReady] = useState(false);

  useEffect(() => {
    if (!container.current) return;
    const wave = WaveSurfer.create({
      container: container.current,
      url,
      height: compact ? 36 : 56,
      waveColor: cssVar("--color-line") || "#ccc",
      progressColor: accent || cssVar("--color-accent") || "#0d9488",
      cursorColor: "transparent",
      barWidth: 2,
      barGap: 2,
      barRadius: 3,
      normalize: true,
    });
    ws.current = wave;
    wave.on("ready", () => setReady(true));
    wave.on("play", () => {
      if (CURRENT && CURRENT !== wave) CURRENT.pause();
      CURRENT = wave;
      setPlaying(true);
      onPlay?.();
    });
    wave.on("pause", () => {
      if (CURRENT === wave) CURRENT = null;
      setPlaying(false);
    });
    wave.on("finish", () => {
      if (CURRENT === wave) CURRENT = null;
      setPlaying(false);
    });
    return () => {
      if (CURRENT === wave) CURRENT = null;
      wave.destroy();
      ws.current = null;
    };
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [url, accent, compact]);

  return (
    <div className="flex items-center gap-3">
      <button
        onClick={() => ws.current?.playPause()}
        disabled={!ready}
        aria-label={playing ? "pause" : "play"}
        className="grid h-10 w-10 shrink-0 place-items-center rounded-full border border-line bg-surface transition-colors hover:border-accent disabled:opacity-40"
        style={{ color: accent || "var(--color-accent)" }}
      >
        {playing ? (
          <svg width="14" height="14" viewBox="0 0 14 14" fill="currentColor">
            <rect x="2" y="1" width="3.5" height="12" rx="1" />
            <rect x="8.5" y="1" width="3.5" height="12" rx="1" />
          </svg>
        ) : (
          <svg width="14" height="14" viewBox="0 0 14 14" fill="currentColor">
            <path d="M3 1.5v11l9-5.5z" />
          </svg>
        )}
      </button>
      <div className="min-w-0 flex-1">
        {label && (
          <div className="mb-1 font-mono text-[0.7rem] uppercase tracking-wider text-ink-faint">
            {label}
          </div>
        )}
        <div ref={container} className="w-full cursor-pointer" />
      </div>
    </div>
  );
}

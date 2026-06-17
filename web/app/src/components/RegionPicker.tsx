import { useEffect, useRef, useState } from "react";
import WaveSurfer from "wavesurfer.js";
import RegionsPlugin from "wavesurfer.js/dist/plugins/regions.esm.js";
import { cssVar } from "../lib/theme";

interface Props {
  file?: File;
  url?: string;
  defaultLen?: number; // seconds for the initial region
  onRegion: (r: { start: number; end: number }) => void;
}

/** Scrub a recording and drag a region to pick the exact reference window.
 * Takes a File (a fresh upload) or a url (an existing voice's stored source). */
export default function RegionPicker({ file, url, defaultLen = 12, onRegion }: Props) {
  const container = useRef<HTMLDivElement>(null);
  const ws = useRef<WaveSurfer | null>(null);
  const region = useRef<{ start: number; end: number } | null>(null);
  const [sel, setSel] = useState<{ start: number; end: number } | null>(null);

  useEffect(() => {
    if (!container.current) return;
    const objectUrl = file ? URL.createObjectURL(file) : null;
    const audioUrl = objectUrl ?? url;
    if (!audioUrl) return;
    const wave = WaveSurfer.create({
      container: container.current,
      url: audioUrl,
      height: 84,
      waveColor: cssVar("--color-line") || "#ccc",
      progressColor: cssVar("--color-accent") || "#0d9488",
      cursorColor: cssVar("--color-ink-faint") || "#888",
      barWidth: 2,
      barGap: 1,
      barRadius: 2,
      normalize: true,
    });
    ws.current = wave;
    const regions = wave.registerPlugin(RegionsPlugin.create());

    wave.on("decode", (duration: number) => {
      const len = Math.min(defaultLen, duration);
      const start = Math.max(0, Math.min(duration * 0.15, duration - len));
      const r = regions.addRegion({
        start,
        end: start + len,
        color: "color-mix(in oklab, var(--color-accent) 18%, transparent)",
        drag: true,
        resize: true,
      });
      const report = () => {
        region.current = { start: r.start, end: r.end };
        setSel({ start: r.start, end: r.end });
        onRegion(region.current);
      };
      report();
      r.on("update-end", report);
    });
    // keep a single region: clicking the wave should not spawn new ones
    regions.enableDragSelection({ color: "transparent" });
    regions.on("region-created", (r) => {
      const all = regions.getRegions();
      if (all.length > 1) r.remove();
    });

    return () => {
      wave.destroy();
      ws.current = null;
      if (objectUrl) URL.revokeObjectURL(objectUrl);
    };
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [file, url]);

  const dur = sel ? (sel.end - sel.start).toFixed(1) : "--";

  return (
    <div>
      <div ref={container} className="w-full cursor-text" />
      <div className="mt-3 flex items-center justify-between font-mono text-xs text-ink-faint">
        <span>drag the box to the clearest stretch of voice</span>
        <span style={{ color: "var(--color-accent)" }}>
          {sel ? `${sel.start.toFixed(1)}-${sel.end.toFixed(1)}s` : ""} ({dur}s)
        </span>
      </div>
    </div>
  );
}

import { useEffect, useRef, useState } from "react";
import WaveSurfer from "wavesurfer.js";
import RegionsPlugin from "wavesurfer.js/dist/plugins/regions.esm.js";
import { cssVar } from "../lib/theme";

interface Props {
  file?: File;
  url?: string;
  defaultLen?: number; // seconds for the initial region
  minLen?: number; // f5 clones badly below ~3s
  maxLen?: number; // f5 timbre saturates by ~12s
  onRegion: (r: { start: number; end: number }) => void;
}

/** Scrub a recording and drag a region to pick the exact reference window.
 * Takes a File (a fresh upload) or a url (an existing voice's stored source).
 * The region is clamped to [minLen, maxLen] and can be auditioned before saving. */
export default function RegionPicker({
  file,
  url,
  defaultLen = 10,
  minLen = 3,
  maxLen = 12,
  onRegion,
}: Props) {
  const container = useRef<HTMLDivElement>(null);
  const ws = useRef<WaveSurfer | null>(null);
  const region = useRef<{ start: number; end: number } | null>(null);
  const [sel, setSel] = useState<{ start: number; end: number } | null>(null);
  const [playing, setPlaying] = useState(false);

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
      const len = Math.min(Math.max(defaultLen, minLen), maxLen, duration);
      const start = Math.max(0, Math.min(duration * 0.15, duration - len));
      const r = regions.addRegion({
        start,
        end: start + len,
        color: "color-mix(in oklab, var(--color-accent) 18%, transparent)",
        drag: true,
        resize: true,
      });
      // clamp to [minLen, maxLen] on every resize/drag, then report
      const sync = () => {
        const s = r.start;
        let e = r.end;
        const dur = e - s;
        if (dur < minLen) e = Math.min(s + minLen, duration);
        else if (dur > maxLen) e = s + maxLen;
        if (Math.abs(e - r.end) > 0.001) r.setOptions({ start: s, end: e });
        region.current = { start: s, end: e };
        setSel({ start: s, end: e });
        onRegion(region.current);
      };
      sync();
      r.on("update-end", sync);
    });
    // keep a single region: clicking the wave should not spawn new ones
    regions.enableDragSelection({ color: "transparent" });
    regions.on("region-created", (r) => {
      const all = regions.getRegions();
      if (all.length > 1) r.remove();
    });

    wave.on("pause", () => setPlaying(false));
    wave.on("finish", () => setPlaying(false));

    return () => {
      wave.destroy();
      ws.current = null;
      if (objectUrl) URL.revokeObjectURL(objectUrl);
    };
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [file, url]);

  function togglePlay() {
    const wave = ws.current;
    if (!wave || !region.current) return;
    if (playing) {
      wave.pause();
      setPlaying(false);
    } else {
      wave.play(region.current.start, region.current.end);
      setPlaying(true);
    }
  }

  const dur = sel ? (sel.end - sel.start).toFixed(1) : "--";

  return (
    <div>
      <div ref={container} className="w-full cursor-text" />
      <div className="mt-3 flex items-center justify-between gap-3 font-mono text-xs text-ink-faint">
        <button
          onClick={togglePlay}
          disabled={!sel}
          className="btn btn-ghost text-xs"
          aria-label={playing ? "stop preview" : "play selection"}
        >
          {playing ? "■ stop" : "▶ play selection"}
        </button>
        <span className="flex-1 text-right">
          drag the box to the clearest stretch ({minLen}-{maxLen}s)
        </span>
        <span style={{ color: "var(--color-accent)" }}>
          {sel ? `${sel.start.toFixed(1)}-${sel.end.toFixed(1)}s` : ""} ({dur}s)
        </span>
      </div>
    </div>
  );
}

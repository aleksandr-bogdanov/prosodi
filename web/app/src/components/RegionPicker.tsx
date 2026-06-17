import { useEffect, useRef, useState } from "react";
import WaveSurfer from "wavesurfer.js";
import RegionsPlugin from "wavesurfer.js/dist/plugins/regions.esm.js";
import { cssVar } from "../lib/theme";

interface Props {
  file?: File;
  url?: string;
  defaultLen?: number; // seconds for the initial region
  minLen?: number; // f5 clones badly below ~3s
  maxLen?: number; // f5 timbre saturates by ~12s, 15 leaves room without hurting it
  onRegion: (r: { start: number; end: number }) => void;
}

/** Scrub a recording and drag a region to pick the exact reference window.
 * Takes a File (a fresh upload) or a url (an existing voice's stored source).
 * The region clamps to [minLen, maxLen]; dragging the LEFT edge auto-previews the
 * onset (so you can land the start on a pause, not mid-word); a zoom slider makes
 * tight selections on long sources workable; the selection can be auditioned. */
export default function RegionPicker({
  file,
  url,
  defaultLen = 12,
  minLen = 3,
  maxLen = 15,
  onRegion,
}: Props) {
  const container = useRef<HTMLDivElement>(null);
  const ws = useRef<WaveSurfer | null>(null);
  const region = useRef<{ start: number; end: number } | null>(null);
  const fit = useRef<number>(1); // px/sec that fits the whole source
  const [sel, setSel] = useState<{ start: number; end: number } | null>(null);
  const [playing, setPlaying] = useState(false);
  const [zoom, setZoom] = useState(1);

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
      minPxPerSec: 1,
    });
    ws.current = wave;
    const regions = wave.registerPlugin(RegionsPlugin.create());

    wave.on("decode", (duration: number) => {
      fit.current = Math.max(1, (container.current?.clientWidth ?? 640) / duration);
      setZoom(fit.current);

      const len = Math.min(Math.max(defaultLen, minLen), maxLen, duration);
      const start = Math.max(0, Math.min(duration * 0.15, duration - len));
      const r = regions.addRegion({
        start,
        end: start + len,
        color: "color-mix(in oklab, var(--color-accent) 18%, transparent)",
        drag: true,
        resize: true,
      });
      // clamp to [minLen, maxLen] on every resize/drag, report, and when the LEFT
      // edge is the one that moved, play the onset so the start can land on a pause
      const report = (autoPreview: boolean) => {
        const prev = region.current;
        const s = r.start;
        let e = r.end;
        const dur = e - s;
        if (dur < minLen) e = Math.min(s + minLen, duration);
        else if (dur > maxLen) e = s + maxLen;
        if (Math.abs(e - r.end) > 0.001) r.setOptions({ start: s, end: e });
        region.current = { start: s, end: e };
        setSel({ start: s, end: e });
        onRegion(region.current);
        if (autoPreview && prev && ws.current) {
          const movedStart = Math.abs(s - prev.start);
          const movedEnd = Math.abs(e - prev.end);
          if (movedStart > 0.02 && movedStart >= movedEnd) {
            ws.current.play(s, Math.min(e, s + 2.0));
            setPlaying(true);
          }
        }
      };
      report(false);
      r.on("update-end", () => report(true));
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

  function onZoom(v: number) {
    setZoom(v);
    ws.current?.zoom(v);
  }

  const dur = sel ? (sel.end - sel.start).toFixed(1) : "--";
  const zoomMax = Math.max(fit.current * 30, 80);

  return (
    <div>
      <div ref={container} className="w-full cursor-text" />
      <div className="mt-3 flex flex-wrap items-center gap-x-4 gap-y-2 font-mono text-xs text-ink-faint">
        <button
          onClick={togglePlay}
          disabled={!sel}
          className="btn btn-ghost text-xs"
          aria-label={playing ? "stop preview" : "play selection"}
        >
          {playing ? "■ stop" : "▶ play selection"}
        </button>
        <label className="flex items-center gap-2">
          zoom
          <input
            type="range"
            min={fit.current}
            max={zoomMax}
            step={0.5}
            value={zoom}
            onChange={(e) => onZoom(Number(e.target.value))}
            className="w-28 accent-[var(--color-accent)]"
          />
        </label>
        <span className="flex-1 text-right">drag to the clearest stretch ({minLen}-{maxLen}s)</span>
        <span style={{ color: "var(--color-accent)" }}>
          {sel ? `${sel.start.toFixed(1)}-${sel.end.toFixed(1)}s` : ""} ({dur}s)
        </span>
      </div>
    </div>
  );
}

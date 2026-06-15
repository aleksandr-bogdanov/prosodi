import { useEffect, useRef, useState } from "react";

interface Props {
  onComplete: (file: File) => void;
  minSeconds?: number;
  disabled?: boolean;
}

/** Mic capture via MediaRecorder, with a live level meter and a timer.
 * Emits a webm File the backend transcodes to wav. */
export default function Recorder({ onComplete, minSeconds = 8, disabled }: Props) {
  const [recording, setRecording] = useState(false);
  const [seconds, setSeconds] = useState(0);
  const [level, setLevel] = useState(0);
  const [error, setError] = useState<string | null>(null);

  const rec = useRef<MediaRecorder | null>(null);
  const chunks = useRef<Blob[]>([]);
  const stream = useRef<MediaStream | null>(null);
  const raf = useRef<number>(0);
  const timer = useRef<number>(0);

  useEffect(() => () => stopTracks(), []);

  function stopTracks() {
    cancelAnimationFrame(raf.current);
    clearInterval(timer.current);
    stream.current?.getTracks().forEach((t) => t.stop());
    stream.current = null;
  }

  async function start() {
    setError(null);
    try {
      const s = await navigator.mediaDevices.getUserMedia({ audio: true });
      stream.current = s;
      chunks.current = [];
      const mr = new MediaRecorder(s);
      rec.current = mr;
      mr.ondataavailable = (e) => e.data.size > 0 && chunks.current.push(e.data);
      mr.onstop = () => {
        const blob = new Blob(chunks.current, { type: mr.mimeType || "audio/webm" });
        stopTracks();
        onComplete(new File([blob], "recording.webm", { type: blob.type }));
      };
      mr.start();
      setRecording(true);
      setSeconds(0);
      timer.current = window.setInterval(() => setSeconds((x) => x + 1), 1000);

      // live level meter
      const ctx = new AudioContext();
      const an = ctx.createAnalyser();
      an.fftSize = 256;
      ctx.createMediaStreamSource(s).connect(an);
      const buf = new Uint8Array(an.frequencyBinCount);
      const tick = () => {
        an.getByteTimeDomainData(buf);
        let sum = 0;
        for (const v of buf) sum += (v - 128) ** 2;
        setLevel(Math.min(1, Math.sqrt(sum / buf.length) / 40));
        raf.current = requestAnimationFrame(tick);
      };
      tick();
    } catch {
      setError("microphone access denied — allow it and try again");
    }
  }

  function stop() {
    rec.current?.stop();
    setRecording(false);
  }

  const mm = String(Math.floor(seconds / 60)).padStart(2, "0");
  const ss = String(seconds % 60).padStart(2, "0");

  return (
    <div className="flex flex-col items-center gap-5">
      <div className="relative grid h-28 w-28 place-items-center">
        {recording && (
          <span
            className="absolute inset-0 rounded-full"
            style={{
              background: "var(--color-accent)",
              opacity: 0.18 + level * 0.5,
              transform: `scale(${1 + level * 0.5})`,
              transition: "transform 80ms linear, opacity 80ms linear",
            }}
          />
        )}
        <button
          onClick={recording ? stop : start}
          disabled={disabled || (recording && seconds < minSeconds)}
          className="relative grid h-20 w-20 place-items-center rounded-full border transition-transform hover:scale-105 disabled:opacity-50"
          style={{
            background: recording ? "var(--color-m-agitated)" : "var(--color-accent)",
            borderColor: "transparent",
            color: "var(--color-accent-ink)",
          }}
          aria-label={recording ? "stop recording" : "start recording"}
        >
          {recording ? (
            <span className="h-6 w-6 rounded-sm bg-current" />
          ) : (
            <svg width="26" height="26" viewBox="0 0 24 24" fill="currentColor">
              <rect x="9" y="2" width="6" height="12" rx="3" />
              <path fill="none" stroke="currentColor" strokeWidth="2" strokeLinecap="round" d="M5 11a7 7 0 0 0 14 0M12 18v3" />
            </svg>
          )}
        </button>
      </div>
      <div className="font-mono text-sm tabular-nums text-ink-soft">
        {mm}:{ss}
        {recording && seconds < minSeconds && (
          <span className="ml-2 text-ink-faint">read at least {minSeconds}s</span>
        )}
      </div>
      {error && <div className="text-sm" style={{ color: "var(--color-m-agitated)" }}>{error}</div>}
    </div>
  );
}

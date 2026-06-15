import { useRef, useState } from "react";

export default function Dropzone({
  onFile,
  disabled,
}: {
  onFile: (f: File) => void;
  disabled?: boolean;
}) {
  const input = useRef<HTMLInputElement>(null);
  const [over, setOver] = useState(false);

  return (
    <div
      onClick={() => !disabled && input.current?.click()}
      onDragOver={(e) => {
        e.preventDefault();
        if (!disabled) setOver(true);
      }}
      onDragLeave={() => setOver(false)}
      onDrop={(e) => {
        e.preventDefault();
        setOver(false);
        if (disabled) return;
        const f = e.dataTransfer.files?.[0];
        if (f) onFile(f);
      }}
      className="card grid cursor-pointer place-items-center px-6 py-12 text-center transition-colors"
      style={{
        borderStyle: "dashed",
        borderColor: over ? "var(--color-accent)" : "var(--color-line)",
        background: over
          ? "color-mix(in oklab, var(--color-accent) 7%, var(--color-surface))"
          : undefined,
        opacity: disabled ? 0.5 : 1,
      }}
    >
      <input
        ref={input}
        type="file"
        accept="audio/*,.wav,.mp3,.m4a,.webm,.ogg,.flac"
        className="hidden"
        onChange={(e) => {
          const f = e.target.files?.[0];
          if (f) onFile(f);
          e.target.value = "";
        }}
      />
      <div
        className="mb-3 grid h-12 w-12 place-items-center rounded-full"
        style={{ background: "var(--color-accent-soft)", color: "var(--color-accent)" }}
      >
        <svg width="22" height="22" viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="2" strokeLinecap="round" strokeLinejoin="round">
          <path d="M12 16V4M12 4l-4 4M12 4l4 4" />
          <path d="M4 16v2a2 2 0 0 0 2 2h12a2 2 0 0 0 2-2v-2" />
        </svg>
      </div>
      <div className="text-base font-medium">Drop a recording, or click to choose</div>
      <div className="mt-1 font-mono text-xs text-ink-faint">
        wav · mp3 · m4a · webm — a dictation or any voice clip
      </div>
    </div>
  );
}

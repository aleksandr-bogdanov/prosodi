import type { View, WordToken } from "../lib/types";

/** One annotated word: colour carries the marker, like the CLI console. */
function Word({ w }: { w: WordToken }) {
  const cls: string[] = ["transition-colors"];
  let style: React.CSSProperties = {};
  if (w.emphasized) {
    cls.push("font-semibold");
    style.color = "var(--color-m-emph)";
  } else if (w.stretched !== null) {
    style.color = "var(--color-m-stretch)";
  }
  if (w.tempo) {
    style.borderBottom = `2px solid color-mix(in oklab, var(--color-m-${w.tempo === "faster" ? "faster" : "slower"}) 60%, transparent)`;
  }
  const arrow = w.boundary === "rise" ? "↗" : w.boundary === "fall" ? "↘" : null;
  return (
    <span className={cls.join(" ")} style={style}>
      {w.text}
      {w.stretched !== null && (
        <sup
          className="ml-0.5 font-mono text-[0.6em] align-super"
          style={{ color: "var(--color-m-stretch)" }}
        >
          {w.stretched.toFixed(1)}×
        </sup>
      )}
      {arrow && (
        <span
          className="ml-0.5"
          style={{ color: `var(--color-m-${w.boundary})` }}
          title={w.boundary === "rise" ? "pitch rises (question-like)" : "pitch falls (decision-like)"}
        >
          {arrow}
        </span>
      )}
    </span>
  );
}

function Pause({ s }: { s: number }) {
  return (
    <span
      className="mx-1 inline-flex items-center rounded-full px-2 py-0.5 font-mono text-[0.7em] align-middle"
      style={{
        color: "var(--color-m-pause)",
        background: "color-mix(in oklab, var(--color-m-pause) 14%, transparent)",
      }}
      title={`${s}s of silence`}
    >
      ❙ {s}s
    </span>
  );
}

export function GlobalBanner({ view }: { view: View }) {
  if (!view.global?.marker) return null;
  const agitated = view.global.marker.startsWith("agitated");
  return (
    <div
      className="mb-4 inline-flex items-center gap-2 rounded-full border px-3 py-1.5 font-mono text-xs"
      style={{
        color: agitated ? "var(--color-m-agitated)" : "var(--color-m-pause)",
        borderColor: agitated
          ? "color-mix(in oklab, var(--color-m-agitated) 40%, transparent)"
          : "color-mix(in oklab, var(--color-m-pause) 40%, transparent)",
        background: agitated
          ? "color-mix(in oklab, var(--color-m-agitated) 10%, transparent)"
          : "color-mix(in oklab, var(--color-m-pause) 10%, transparent)",
      }}
    >
      &lt;{view.global.marker}&gt;
    </div>
  );
}

export function HeaderStats({ view }: { view: View }) {
  const h = view.header;
  const items: [string, string][] = [
    ["duration", `${h.duration_s}s`],
    ["words", String(h.n_words)],
    ["rate", h.speech_rate_wps ? `${h.speech_rate_wps} w/s` : "—"],
    ["pauses", `${h.pause_count} · ${h.pause_total_s}s`],
    ["F0", h.f0_median_hz ? `${h.f0_median_hz} Hz` : "—"],
    ["lang", h.language ?? "—"],
  ];
  return (
    <div className="mb-5 flex flex-wrap gap-x-5 gap-y-2 font-mono text-xs text-ink-faint">
      {items.map(([k, v]) => (
        <span key={k}>
          <span className="text-ink-soft">{k}</span> {v}
        </span>
      ))}
    </div>
  );
}

export function MarkerLegend() {
  const items: [string, string, string][] = [
    ["pause", "var(--color-m-pause)", "silence before the next word"],
    ["emphasis", "var(--color-m-emph)", "leaned on vs baseline"],
    ["stretch ×", "var(--color-m-stretch)", "drawled word"],
    ["↗ ↘", "var(--color-m-rise)", "clause-final pitch"],
    ["tempo", "var(--color-m-faster)", "faster / slower span"],
  ];
  return (
    <div className="flex flex-wrap gap-3 font-mono text-[0.7rem] text-ink-faint">
      {items.map(([label, color, title]) => (
        <span key={label} className="inline-flex items-center gap-1.5" title={title}>
          <span className="h-2 w-2 rounded-full" style={{ background: color }} />
          {label}
        </span>
      ))}
    </div>
  );
}

/** The annotated transcript: the thing plain STT throws away, put back inline. */
export default function MarkerText({ view }: { view: View }) {
  return (
    <div>
      <HeaderStats view={view} />
      <GlobalBanner view={view} />
      <p className="text-[1.15rem] leading-[2.1] tracking-[0.002em]">
        {view.tokens.map((t, i) =>
          t.type === "word" ? (
            <span key={i}>
              {i > 0 && view.tokens[i - 1].type === "word" ? " " : ""}
              <Word w={t} />
            </span>
          ) : (
            <Pause key={i} s={t.seconds} />
          ),
        )}
      </p>
    </div>
  );
}

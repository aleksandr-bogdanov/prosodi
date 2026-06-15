import type { Scorecard } from "../lib/types";

function Row({
  label,
  value,
  hint,
  good,
}: {
  label: string;
  value: string;
  hint: string;
  good?: boolean | null;
}) {
  return (
    <div className="flex items-baseline justify-between gap-4 border-b border-line-soft py-2.5 last:border-0">
      <div>
        <div className="text-sm text-ink">{label}</div>
        <div className="font-mono text-[0.7rem] text-ink-faint">{hint}</div>
      </div>
      <div
        className="shrink-0 font-mono text-sm tabular-nums"
        style={{
          color:
            good == null
              ? "var(--color-ink)"
              : good
                ? "var(--color-m-rise)"
                : "var(--color-ink-soft)",
        }}
      >
        {value}
      </div>
    </div>
  );
}

const fmt = (v: number | null, suffix = "") => (v == null ? "—" : `${v}${suffix}`);

/** The verify scorecard: what the render preserved, measured not guessed. */
export default function ScoreCard({ card }: { card: Scorecard }) {
  const { pauses: p, tempo_spans: t, stretch: s, speech_rate: r, f0 } = card;
  return (
    <div className="card p-5">
      <div className="eyebrow mb-3">verify · render vs original</div>
      <Row
        label="Pauses"
        hint="recall · duration error"
        value={`${fmt(p.recall)} · ${fmt(p.mean_abs_err_s, "s")}`}
        good={p.recall != null ? p.recall >= 0.6 : null}
      />
      <Row
        label="Tempo"
        hint="direction · magnitude"
        value={`${t.direction_agree}/${t.scored} · ×${fmt(t.magnitude_ratio)}`}
        good={t.scored > 0 ? t.direction_agree / t.scored >= 0.6 : null}
      />
      <Row
        label="Stretch"
        hint="realization over spec'd words"
        value={`×${fmt(s.realization_ratio)}`}
        good={null}
      />
      <Row
        label="Speech rate"
        hint="render / original"
        value={`×${fmt(r.ratio)}`}
        good={r.ratio != null ? Math.abs(r.ratio - 1) <= 0.25 : null}
      />
      <Row
        label="Register"
        hint="median F0 offset"
        value={fmt(f0.median_offset_st, " st")}
        good={f0.median_offset_st != null ? Math.abs(f0.median_offset_st) <= 3 : null}
      />
      <Row
        label="Pitch contour"
        hint={`r over ${f0.n_words} words`}
        value={fmt(f0.contour_r)}
        good={null}
      />
    </div>
  );
}

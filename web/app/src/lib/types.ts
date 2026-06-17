export type WordToken = {
  type: "word";
  text: string;
  emphasized: boolean;
  stretched: number | null;
  boundary: "rise" | "fall" | null;
  tempo: "faster" | "slower" | null;
  start?: number | null;
  end?: number | null;
  f0?: number | null;
};
export type PauseToken = { type: "pause"; seconds: number };
export type Token = WordToken | PauseToken;

export interface Header {
  duration_s: number;
  n_words: number;
  language: string | null;
  f0_median_hz: number | null;
  f0_range_st: number | null;
  speech_rate_wps: number | null;
  pause_count: number;
  pause_total_s: number;
}

export interface GlobalMarker {
  marker: string;
  rate_wps?: number | null;
  speaker_rate_wps?: number | null;
  rate_dev_pct?: number | null;
  f0_dev_st?: number | null;
}

export interface View {
  header: Header;
  tokens: Token[];
  global: GlobalMarker | null;
  notation: string;
}

export interface Scorecard {
  words: { orig: number; rend: number; aligned: number };
  pauses: { spec: number; matched: number; recall: number | null; mean_abs_err_s: number | null; inserted: number };
  tempo_spans: { spec: number; scored: number; direction_agree: number; magnitude_ratio: number | null };
  stretch: { spec: number; scored: number; realization_ratio: number | null };
  speech_rate: { orig_wps: number | null; rend_wps: number | null; ratio: number | null };
  f0: { median_offset_st: number | null; contour_r: number | null; contour_rmse_st: number | null; n_words: number };
}

export interface Job<T = unknown> {
  id: string;
  kind: string;
  status: "queued" | "running" | "done" | "error";
  progress: number;
  message: string;
  result: T | null;
  error: string | null;
  log: string[];
}

export interface AnalyzeResult {
  session_id: string;
  view: View;
  audio_url: string;
}

export interface RoundtripResult {
  render_url: string;
  original_url: string;
  scorecard: Scorecard;
}

export interface GameItem { id: string; url: string; position: number }
export interface GameResult {
  game_id: string;
  items: GameItem[];
  target_text: string;
  view: View;
}
export interface GameTruth {
  truth: Record<string, { is_real: boolean; label: string }>;
}

export interface Voice {
  id: string;
  name: string;
  ref_text: string;
  source: string;
  created: string;
  ref_s: number;
  ref_url: string;
  source_url?: string;
}

export interface ModelOutput {
  name: string;
  render_url: string;
  scorecard: Scorecard | null;
}

export interface ReconstructResult {
  original_url: string | null;
  view: View;
  models: ModelOutput[];
  voice: Voice;
}

export interface ExampleGallery {
  id: string;
  title: string;
  blurb: string;
  source: string;
  original_url: string;
  prosody_url: string;
  control_url?: string;
  view: View;
  scorecard?: Scorecard;
}
export interface ExamplesManifest {
  galleries: ExampleGallery[];
  game: { items: GameItem[]; truth_url?: string; target_text: string } | null;
}

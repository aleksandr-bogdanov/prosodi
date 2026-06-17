import type {
  AnalyzeResult, ExamplesManifest, GameResult, GameTruth, Job, ReconstructResult,
  RoundtripResult, Voice,
} from "./types";

async function submit(path: string, form: FormData): Promise<string> {
  const r = await fetch(path, { method: "POST", body: form });
  if (!r.ok) throw new Error(`${path} failed: ${r.status} ${await r.text()}`);
  const data = (await r.json()) as { job_id: string };
  return data.job_id;
}

export async function getJob<T>(id: string): Promise<Job<T>> {
  const r = await fetch(`/api/jobs/${id}`);
  if (!r.ok) throw new Error(`job ${id} not found`);
  return (await r.json()) as Job<T>;
}

/** Poll a job to completion, reporting progress; resolves with its result.
 *
 * Heavy renders (f5) hold Python's GIL and briefly starve the server's event
 * loop, so a poll can fail mid-job. That is not a real failure: tolerate a run
 * of transient fetch errors and keep polling, only giving up after a long
 * unbroken stretch of them. */
export async function pollJob<T>(
  id: string,
  onProgress?: (p: number, msg: string) => void,
): Promise<T> {
  let misses = 0;
  const MAX_MISSES = 90; // ~3 min of unbroken unreachability before giving up
  for (;;) {
    try {
      const job = await getJob<T>(id);
      misses = 0;
      onProgress?.(job.progress, job.message);
      if (job.status === "done") return job.result as T;
      if (job.status === "error") throw new Error(job.error ?? "job failed");
    } catch (e) {
      // a job-level error message is real; a network blip is not
      if (e instanceof Error && e.message && !e.message.includes("fetch")) throw e;
      if (++misses >= MAX_MISSES) throw new Error("server stopped responding");
    }
    await new Promise((res) => setTimeout(res, 1000));
  }
}

export async function analyze(
  file: File,
  useProfile: boolean,
  onProgress?: (p: number, msg: string) => void,
): Promise<AnalyzeResult> {
  const form = new FormData();
  form.append("file", file);
  form.append("use_profile", String(useProfile));
  return pollJob<AnalyzeResult>(await submit("/api/analyze", form), onProgress);
}

export async function roundtrip(
  sessionId: string,
  opts: { fitTempo: boolean; clauseMinPauseS: number },
  onProgress?: (p: number, msg: string) => void,
): Promise<RoundtripResult> {
  const form = new FormData();
  form.append("session_id", sessionId);
  form.append("fit_tempo", String(opts.fitTempo));
  form.append("clause_min_pause_s", String(opts.clauseMinPauseS));
  return pollJob<RoundtripResult>(await submit("/api/roundtrip", form), onProgress);
}

export async function startGame(
  src: { file?: File; sessionId?: string; nClones?: number },
  onProgress?: (p: number, msg: string) => void,
): Promise<GameResult> {
  const form = new FormData();
  if (src.file) form.append("file", src.file);
  if (src.sessionId) form.append("session_id", src.sessionId);
  form.append("n_clones", String(src.nClones ?? 4));
  return pollJob<GameResult>(await submit("/api/game", form), onProgress);
}

export async function revealGame(gameId: string): Promise<GameTruth> {
  const r = await fetch(`/api/game/${gameId}/reveal`);
  if (!r.ok) throw new Error("could not reveal the game");
  return (await r.json()) as GameTruth;
}

export async function listVoices(): Promise<Voice[]> {
  const r = await fetch("/api/voices");
  if (!r.ok) return [];
  return ((await r.json()) as { voices: Voice[] }).voices;
}

export async function createVoice(
  file: File,
  name: string,
  region: { start: number; end: number } | null,
  onProgress?: (p: number, msg: string) => void,
): Promise<Voice> {
  const form = new FormData();
  form.append("file", file);
  form.append("name", name);
  if (region) {
    form.append("ref_start", String(region.start));
    form.append("ref_end", String(region.end));
  }
  return pollJob<Voice>(await submit("/api/voices", form), onProgress);
}

export async function deleteVoice(id: string): Promise<void> {
  await fetch(`/api/voices/${id}`, { method: "DELETE" });
}

export async function reconstruct(
  notation: string,
  voiceId: string,
  sessionId: string | null,
  onProgress?: (p: number, msg: string) => void,
): Promise<ReconstructResult> {
  const form = new FormData();
  form.append("notation", notation);
  form.append("voice_id", voiceId);
  if (sessionId) form.append("session_id", sessionId);
  return pollJob<ReconstructResult>(await submit("/api/reconstruct", form), onProgress);
}

export async function getExamples(): Promise<ExamplesManifest> {
  const r = await fetch("/api/examples");
  if (!r.ok) return { galleries: [], game: null };
  return (await r.json()) as ExamplesManifest;
}

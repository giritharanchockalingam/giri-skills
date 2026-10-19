/* Browser runner for run_skill.py: a thin typed client over public/run-worker.js (Pyodide in a Web Worker).
 *
 * The worker loads CPython-in-WASM from the pinned Pyodide CDN, writes the runtime bundle (scripts/*.py,
 * shared/*.md, each wired skill's files) into its virtual FS under /repo, and runs the real runner in-process
 * (RUN_SKILL_INPROC=1 → runpy instead of subprocess; byte-identical outputs, see tests/test_run_skill_inproc.py).
 * Nothing here interprets results: what the page shows is what run.json says.
 */

export const PYODIDE_VERSION = "0.27.7";
export const PYODIDE_CDN = `https://cdn.jsdelivr.net/pyodide/v${PYODIDE_VERSION}/full/`;

/** Where to load Pyodide from: the pinned CDN, or a same-origin path given as `?pyodide=/path/` (local testing only;
 *  anything that is not a same-origin absolute path is ignored so a link cannot make the page load a foreign script). */
export function pyodideBase(): string {
  if (typeof window === "undefined") return PYODIDE_CDN;
  const q = new URLSearchParams(window.location.search).get("pyodide");
  if (q && /^\/[^/\\]/.test(q)) return q.endsWith("/") ? q : q + "/";
  return PYODIDE_CDN;
}

export type RunInputValue = { kind: "text"; ext: string; content: string } | { kind: "value"; value: string } | { kind: "files"; files: { path: string; content: string }[] } | null;

export interface RunStep {
  step: string; kind: string; ok: boolean; exit?: number; expected_exit?: number[]; duration_s?: number; cmd?: string;
  skipped?: boolean; reason?: string; skipped_reason?: string; error?: string; provider?: string; out?: string; log?: string;
}
export interface RunCheck { check: string; pass: boolean; evidence: string; path: string }
export interface RunJson {
  skill: string; version: string; provider: string; model: string; out: string;
  inputs: Record<string, string>; assumptions: Record<string, string>; steps: RunStep[]; checks: RunCheck[]; ok: boolean;
}
export interface NeedsInput { skill: string; missing: { name: string; type: string; from: string; question: string }[]; hint: string }

export interface RunResult {
  exitCode: number; outDir: string; runJson: RunJson | null; runText: string | null; needsInput: NeedsInput | null;
  /** Every file under the out dir (relative path → text), except run.json / needs_input.json. */
  files: Record<string, string | null>;
}
export interface LogLine { stream: "stdout" | "stderr" | "cmd" | "sys"; text: string }
export interface Progress { stage: string; message: string; pct?: number }

export interface RunRequest {
  skill: string;
  inputs: Record<string, RunInputValue>;
  assumptions: Record<string, string>;
  /** Anthropic API key. Held in memory only; passed to the worker for this one run, then dropped. */
  providerKey?: string;
  model?: string;
  onLog?: (line: LogLine) => void;
}

type Pending = { resolve: (v: unknown) => void; reject: (e: Error) => void; onLog?: (l: LogLine) => void };

class Runner {
  private worker: Worker | null = null;
  private ready: Promise<{ python: string; files: number }> | null = null;
  private pending = new Map<string, Pending>();
  private seq = 0;
  private progressListeners = new Set<(p: Progress) => void>();
  private lastProgress: Progress | null = null;

  onProgress(fn: (p: Progress) => void): () => void {
    this.progressListeners.add(fn);
    if (this.lastProgress) fn(this.lastProgress);
    return () => this.progressListeners.delete(fn);
  }

  /** Create the worker and load Pyodide + the repo bundle (once; lazy). */
  load(): Promise<{ python: string; files: number }> {
    if (this.ready) return this.ready;
    this.ready = new Promise((resolve, reject) => {
      const w = new Worker("/run-worker.js");
      this.worker = w;
      w.onerror = (e) => { reject(new Error(e.message || "worker failed to start")); };
      w.onmessage = (ev: MessageEvent) => {
        const m = ev.data;
        if (m.type === "progress") { this.lastProgress = m; for (const fn of this.progressListeners) fn(m); return; }
        if (m.type === "ready") { resolve({ python: m.python, files: m.files }); return; }
        if (m.type === "log") { this.pending.get(m.id)?.onLog?.({ stream: m.stream, text: m.text }); return; }
        if (m.type === "result" || m.type === "file") { const p = this.pending.get(m.id); this.pending.delete(m.id); p?.resolve(m); return; }
        if (m.type === "error") {
          if (m.id && this.pending.has(m.id)) { const p = this.pending.get(m.id)!; this.pending.delete(m.id); p.reject(new Error(m.message)); }
          else { this.ready = null; reject(new Error(m.message)); }
        }
      };
      w.postMessage({ type: "init", pyodideBase: pyodideBase() });
    });
    this.ready.catch(() => { this.ready = null; this.worker?.terminate(); this.worker = null; });
    return this.ready;
  }

  private call<T>(msg: Record<string, unknown>, onLog?: (l: LogLine) => void): Promise<T> {
    const id = `m${++this.seq}`;
    return new Promise<T>((resolve, reject) => {
      this.pending.set(id, { resolve: resolve as (v: unknown) => void, reject, onLog });
      this.worker!.postMessage({ ...msg, id });
    });
  }

  async runSkill(req: RunRequest): Promise<RunResult> {
    await this.load();
    const m = await this.call<RunResult & { type: string }>({
      type: "run", skill: req.skill, inputs: req.inputs, assumptions: req.assumptions,
      providerKey: req.providerKey || "", model: req.model || "claude-sonnet-4-5",
    }, req.onLog);
    return { exitCode: m.exitCode, outDir: m.outDir, runJson: m.runJson, runText: m.runText, needsInput: m.needsInput, files: m.files };
  }

  async readFile(path: string): Promise<string | null> {
    await this.load();
    const m = await this.call<{ content: string | null }>({ type: "read", path });
    return m.content;
  }
}

let singleton: Runner | null = null;
export const runner = (): Runner => (singleton ??= new Runner());

/** Public API used by the Run view. */
export const runSkill = (req: RunRequest) => runner().runSkill(req);
export const loadRuntime = () => runner().load();

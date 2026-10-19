"use client";
import { failureText } from "@/lib/runText";
/* "Run it" — runs scripts/run_skill.py for this skill in the browser (CPython via Pyodide, in a Web Worker).
 * Nothing on this panel is simulated: the inputs are written into the runner's virtual FS, the real runner and the
 * skill's real scripts execute, and every status shown is read back from the run.json the runner wrote. */
import { useCallback, useEffect, useMemo, useRef, useState } from "react";
import type { AgentInput, AgentSpec } from "@/lib/data";
import { loadRuntime, runSkill, runner, type LogLine, type Progress, type RunInputValue, type RunResult } from "@/lib/runner";
import { mdToHtml } from "@/lib/markdown.mjs";
import { PassPill } from "./Badge";
import { recordBrowserRun } from "@/app/insightsActions";

const FILE_TYPES = new Set(["csv", "json", "md", "txt", "file", "sql"]);
const MODELS = ["claude-sonnet-4-5", "claude-opus-4-1", "claude-haiku-4-5"];

type FolderFile = { path: string; content: string };
type Draft = { text: string; fileName: string | null; fixture: boolean; value: string; assume: string; checked: boolean; folder: FolderFile[] | null; folderNote: string };
const emptyDraft = (): Draft => ({ text: "", fileName: null, fixture: false, value: "", assume: "", checked: false, folder: null, folderNote: "" });

/** Read a chosen folder as text files (same limits as the server: 200 files, 2 MB); skips VCS/dependency folders and binaries. */
const SKIP_DIR = /(^|\/)(\.git|node_modules|\.next|dist|build|__pycache__|\.venv)(\/|$)/;
async function readFolder(list: FileList): Promise<{ files: FolderFile[]; note: string }> {
  const files: FolderFile[] = []; let bytes = 0, skipped = 0;
  for (const f of Array.from(list)) {
    const rel = ((f as File & { webkitRelativePath?: string }).webkitRelativePath || f.name).split("/").slice(1).join("/") || f.name;
    if (SKIP_DIR.test(rel) || f.size > 512 * 1024) { skipped++; continue; }
    const text = await f.text();
    if (text.includes("\u0000")) { skipped++; continue; }                     // binary
    if (files.length >= 200 || bytes + f.size > 2 * 1024 * 1024) { skipped++; continue; }
    files.push({ path: rel, content: text }); bytes += f.size;
  }
  return { files, note: `${files.length} file${files.length === 1 ? "" : "s"} read${skipped ? ` · ${skipped} skipped (binary, too large, or .git / node_modules)` : ""}` };
}

const extOf = (name: string | null, type: string) => {
  const m = name?.match(/\.([A-Za-z0-9]+)$/);
  return m ? m[1].toLowerCase() : type === "file" ? "txt" : type;
};
const isTruthy = (s: string) => ["1", "true", "yes", "y", "on"].includes(s.trim().toLowerCase());

function download(name: string, content: string) {
  const blob = new Blob([content], { type: "text/plain;charset=utf-8" });
  const url = URL.createObjectURL(blob);
  const a = document.createElement("a");
  a.href = url; a.download = name; a.click();
  setTimeout(() => URL.revokeObjectURL(url), 1000);
}

export function RunPanel({ skillId, agent, defaultOpen = false }: { skillId: string; agent: AgentSpec; defaultOpen?: boolean }) {
  const inputs = useMemo(() => [...agent.inputs].sort((a, b) => Number(b.required) - Number(a.required)), [agent.inputs]);
  // ?mode=new|existing picks that starting point's example; otherwise the happy-path example
  const [mode, setMode] = useState<"new" | "existing" | null>(null);
  const modeSpec = mode ? agent.modes?.[mode] ?? null : null;
  const demo = modeSpec ?? agent.demo;
  const [open, setOpen] = useState(defaultOpen);
  const [drafts, setDrafts] = useState<Record<string, Draft>>(() => {
    const d: Record<string, Draft> = {};
    for (const i of agent.inputs) {
      d[i.name] = emptyDraft();
      // path inputs are output targets (a dir the scripts create): default under the run's out dir
      if (i.type === "path") d[i.name].value = `{out}/${i.name}`;
    }
    return d;
  });
  const [key, setKey] = useState("");            // React state only — never persisted, logged or sent anywhere but api.anthropic.com
  const [model, setModel] = useState(MODELS[0]);
  const [progress, setProgress] = useState<Progress | null>(null);
  const [runtimeState, setRuntimeState] = useState<"idle" | "loading" | "ready" | "error">("idle");
  const [runtimeError, setRuntimeError] = useState("");
  const [running, setRunning] = useState(false);
  const [log, setLog] = useState<LogLine[]>([]);
  const [result, setResult] = useState<RunResult | null>(null);
  const [viewing, setViewing] = useState<{ path: string; raw: boolean } | null>(null);
  const logRef = useRef<HTMLPreElement>(null);

  const setDraft = (name: string, patch: Partial<Draft>) => setDrafts((d) => ({ ...d, [name]: { ...d[name], ...patch } }));

  // Arriving from the front door: ?task= is what the person asked; ?example=1 runs the skill on its own sample inputs.
  const [askedTask, setAskedTask] = useState("");
  const [auto, setAuto] = useState<"off" | "fill" | "run" | "done">("off");
  useEffect(() => {
    const q = new URLSearchParams(window.location.search);
    setAskedTask((q.get("task") || "").slice(0, 300));
    const m = q.get("mode");
    if (m === "new" || m === "existing") setMode(m);
    if (q.get("example") === "1" && (demo || agent.modes?.[m as "new" | "existing"])) { setOpen(true); setAuto("fill"); }
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, []);

  // lazy: the runtime (≈10 MB from the Pyodide CDN) loads only when the panel is opened
  useEffect(() => {
    if (!open) return;
    const off = runner().onProgress(setProgress);   // stays subscribed while the panel is open
    if (runtimeState === "idle") {
      setRuntimeState("loading");
      loadRuntime().then(() => setRuntimeState("ready")).catch((e) => { setRuntimeState("error"); setRuntimeError(String(e?.message || e)); });
    }
    return off;
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [open]);

  useEffect(() => { if (logRef.current) logRef.current.scrollTop = logRef.current.scrollHeight; }, [log]);

  // An auto-run example should open on its answer: bring the Result card into view, from its first line.
  const answerRef = useRef<HTMLDivElement>(null);
  const answerShown = useRef(false);

  const fixturePath = (i: AgentInput) => {
    const v = demo?.inputs[i.name];
    return v && v.startsWith("evals/") ? v : null;
  };
  const loadFixture = useCallback(async (i: AgentInput) => {
    const rel = fixturePath(i);
    if (!rel) return;
    const res = await fetch(`/runtime/repo/skills/${skillId}/${rel}`);
    if (!res.ok) { setDraft(i.name, { text: `(could not load fixture ${rel}: HTTP ${res.status})`, fixture: false }); return; }
    setDraft(i.name, { text: await res.text(), fileName: rel.split("/").pop() || rel, fixture: true });
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [skillId, demo]);

  // whether the inputs are still exactly the skill's sample inputs (an example run is a demo, not work: not counted as ROI)
  const [exampleFilled, setExampleFilled] = useState(false);
  const edit = (name: string, patch: Partial<Draft>) => { setExampleFilled(false); setDraft(name, patch); };
  const fillAllFromExample = async () => {
    if (!demo) return;
    for (const i of inputs) {
      const v = demo.inputs[i.name];
      if (v == null) continue;
      if (FILE_TYPES.has(i.type)) await loadFixture(i);
      else if (i.type === "dir") setDraft(i.name, { value: v.startsWith("evals/") ? `/repo/skills/${skillId}/${v}` : v, fixture: true, folder: null, folderNote: "" });
      else if (i.type === "flag") setDraft(i.name, { checked: isTruthy(v) });
      else setDraft(i.name, { value: v });
    }
    for (const [k, v] of Object.entries(demo.assume)) setDraft(k, { assume: v });
    setExampleFilled(true);
  };

  const onFile = (i: AgentInput, f: File | null) => {
    if (!f) return;
    f.text().then((t) => edit(i.name, { text: t, fileName: f.name, fixture: false }));
  };

  const buildRequest = () => {
    const req: Record<string, RunInputValue> = {};
    const assumptions: Record<string, string> = {};
    for (const i of inputs) {
      const d = drafts[i.name];
      let given = false;
      if (i.type === "dir" && d.folder?.length) {   // a whole chosen folder (e.g. your repo's migrations)
        req[i.name] = { kind: "files", files: d.folder }; given = true;
      } else if (i.type === "dir" && d.text.trim()) {  // one pasted/uploaded file stands in for the folder (scripts that accept a file)
        req[i.name] = { kind: "text", ext: ((d.fileName ?? "").split(".").pop() || "sql").toLowerCase(), content: d.text }; given = true;
      } else if (FILE_TYPES.has(i.type)) {
        if (d.text.trim()) { req[i.name] = { kind: "text", ext: extOf(d.fileName, i.type), content: d.text }; given = true; }
      } else if (i.type === "flag") {
        if (d.checked) { req[i.name] = { kind: "value", value: "true" }; given = true; }
      } else if (d.value.trim() !== "") { req[i.name] = { kind: "value", value: d.value }; given = true; }
      if (!given && d.assume.trim() !== "") assumptions[i.name] = d.assume;
    }
    return { req, assumptions };
  };

  const run = async () => {
    setRunning(true); setResult(null); setViewing(null); setLog([]);
    const { req, assumptions } = buildRequest();
    try {
      const t0 = Date.now();
      const r = await runSkill({ skill: skillId, inputs: req, assumptions, providerKey: key || undefined, model, onLog: (l) => setLog((x) => [...x, l]) });
      setResult(r);
      const checks = ((r.runJson as { checks?: { pass?: boolean }[] } | null)?.checks) ?? [];
      void recordBrowserRun({ skill: skillId, status: r.needsInput ? "needs_input" : r.exitCode === 0 ? "succeeded" : "failed", example: exampleFilled || inputs.some((i) => drafts[i.name]?.fixture),
        mode, checksPassed: checks.filter((c) => c.pass).length, checksTotal: checks.length, durationMs: Date.now() - t0 });
    } catch (e) {
      setLog((x) => [...x, { stream: "sys", text: `run failed: ${String((e as Error)?.message || e)}` }]);
    } finally { setRunning(false); }
  };

  useEffect(() => {
    if (auto === "fill" && runtimeState === "ready") { fillAllFromExample().then(() => setAuto("run")); }
    else if (auto === "run" && !running) { setAuto("done"); run(); }
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [auto, runtimeState]);

  const rj = result?.runJson ?? null;
  const banner = !result ? null
    : result.needsInput ? { tone: "hold", text: `NEEDS INPUT — missing: ${result.needsInput.missing.map((m) => m.name).join(", ")}` }
    : rj ? (rj.ok ? { tone: "sage", text: "OK — every step ran and every check passed" } : { tone: "rust", text: `FAILED — ${failureText(rj)}` })
    : { tone: "rust", text: `FAILED — the runner exited ${result.exitCode} without writing run.json` };
  const outputFiles = result ? Object.keys(result.files).filter((p) => !p.startsWith("logs/")).sort() : [];
  // the deliverable to show first: the skill's first declared Markdown output that was written, else its first output
  const declared = agent.outputs.map((o) => o.path.replace("{out}/", ""));
  const written = (rel: string) => outputFiles.find((p) => p === rel || p.endsWith("/" + rel));
  const primary = (declared.filter((d) => d.endsWith(".md")).map(written).find(Boolean)
    ?? declared.map(written).find(Boolean) ?? outputFiles[0]) || null;
  const logFiles = result ? Object.keys(result.files).filter((p) => p.startsWith("logs/")).sort() : [];
  const rel = (p: string) => (result && p.startsWith(result.outDir + "/") ? p.slice(result.outDir.length + 1) : p);

  return (
    <div className="card card-pad run-panel" id="run">
      <div className="flex flex-wrap items-center justify-between gap-x-4 gap-y-2">
        <div>
          <div className="h3">Run it</div>
          <p className="caption mt-1">Runs <code>run_skill.py</code> and this skill&apos;s scripts in your browser (CPython via Pyodide). Results come from the <code>run.json</code> it writes — nothing is simulated.</p>
        </div>
        {!open && <button type="button" className="btn btn-primary" onClick={() => setOpen(true)}>Open the run view</button>}
      </div>

      {open && (
        <>
          {modeSpec && (
            <div className="run-asked"><span className="caption">{mode === "new" ? "Starting new" : "Improving what exists"} — you bring:</span> {modeSpec.bring}</div>
          )}
          {askedTask && (
            <div className="run-asked"><span className="caption">You asked:</span> “{askedTask}”
              {auto !== "off" && <span className="caption"> — running this skill on its own sample inputs (fictional, labelled) so you can see exactly what it produces. Then replace the inputs with your files and run again.</span>}
            </div>
          )}
          <div className={`run-runtime run-runtime-${runtimeState}`} role="status" aria-live="polite">
            {runtimeState === "loading" && (
              <>
                <div className="run-runtime-msg">{progress?.message || "Loading Python runtime (≈10 MB, once)"}</div>
                <div className="run-bar"><span style={{ width: `${progress?.pct ?? 2}%` }} /></div>
              </>
            )}
            {runtimeState === "ready" && <div className="run-runtime-msg">{progress?.message}</div>}
            {runtimeState === "error" && <div className="run-runtime-msg fail">Runtime failed to load: {runtimeError}. The Pyodide CDN (cdn.jsdelivr.net) must be reachable.</div>}
          </div>

          <div className="flex flex-wrap items-center justify-between gap-3 mt-6 mb-2">
            <div className="h3" style={{ fontSize: 14 }}>Inputs <span className="muted font-normal">({inputs.length})</span></div>
            {demo && <button type="button" className="btn btn-secondary" onClick={fillAllFromExample}>Fill all from example ({demo.caseId})</button>}
          </div>
          <div className="run-inputs">
            {inputs.map((i) => {
              const d = drafts[i.name];
              const fx = fixturePath(i);
              return (
                <div key={i.name} className="run-input">
                  <div className="run-input-head">
                    <label htmlFor={`in-${i.name}`}><code>{i.name}</code>{i.required && <span className="agent-req" title="required"> *</span>}<span className="muted"> · {i.type || "string"}</span></label>
                    {i.from && <div className="caption">{i.from}</div>}
                  </div>
                  {FILE_TYPES.has(i.type) && (
                    <>
                      <div className="run-file-row">
                        <input id={`in-${i.name}`} type="file" className="run-file" onChange={(e) => onFile(i, e.target.files?.[0] ?? null)} />
                        {fx && <button type="button" className="btn btn-secondary" onClick={() => loadFixture(i)}>Use example fixture</button>}
                      </div>
                      {d.fixture && <div className="run-fixture-note">example fixture <code>{d.fileName}</code> — replace with your real file</div>}
                      {!d.fixture && d.fileName && <div className="caption">loaded <code>{d.fileName}</code></div>}
                      <textarea className="run-textarea" value={d.text} placeholder={`…or paste the ${i.type} content here`} spellCheck={false}
                        onChange={(e) => edit(i.name, { text: e.target.value, fixture: false, fileName: d.fileName })} />
                    </>
                  )}
                  {i.type === "dir" && (
                    <>
                      <div className="run-note">Choose your existing folder (read in this browser, never uploaded), or paste one file from it, or use the example folder.</div>
                      <div className="run-file-row">
                        <label className="btn btn-secondary btn-sm" style={{ cursor: "pointer" }}>Choose folder…
                          <input type="file" multiple hidden aria-label={`Choose a folder for ${i.name}`}
                            {...({ webkitdirectory: "", directory: "" } as Record<string, string>)}
                            onChange={async (e) => { if (!e.target.files?.length) return; const r = await readFolder(e.target.files); edit(i.name, { folder: r.files, folderNote: r.note, text: "", value: "", fixture: false }); }} />
                        </label>
                        <input type="file" className="input" aria-label={`Upload a file for ${i.name}`} onChange={(e) => { edit(i.name, { folder: null, folderNote: "" }); onFile(i, e.target.files?.[0] ?? null); }} />
                      </div>
                      {d.folder && <div className="caption">{d.folderNote} <button type="button" className="link" onClick={() => setDraft(i.name, { folder: null, folderNote: "" })}>clear</button></div>}
                      <textarea className="run-textarea" value={d.text} placeholder="…or paste the file content here" spellCheck={false}
                        onChange={(e) => edit(i.name, { text: e.target.value, value: "", fixture: false, fileName: d.fileName })} />
                      {fx && (
                        <div className="run-file-row">
                          <input id={`in-${i.name}`} className="input run-input-text" value={d.value} readOnly placeholder="(none)" />
                          <button type="button" className="btn btn-secondary" onClick={() => setDraft(i.name, { value: `/repo/skills/${skillId}/${fx}`, text: "", fixture: true, folder: null, folderNote: "" })}>Use example fixture folder</button>
                        </div>
                      )}
                    </>
                  )}
                  {i.type === "path" && (
                    <>
                      <input id={`in-${i.name}`} className="input run-input-text" value={d.value} onChange={(e) => edit(i.name, { value: e.target.value })} />
                      <div className="caption">An output target; <code>{"{out}"}</code> is this run&apos;s folder.</div>
                    </>
                  )}
                  {i.type === "flag" && (
                    <label className="run-check"><input id={`in-${i.name}`} type="checkbox" checked={d.checked} onChange={(e) => edit(i.name, { checked: e.target.checked })} /> set <code>{i.flag || `--${i.name.replace(/_/g, "-")}`}</code></label>
                  )}
                  {!FILE_TYPES.has(i.type) && !["dir", "path", "flag"].includes(i.type) && (
                    <input id={`in-${i.name}`} className="input run-input-text" value={d.value} placeholder={i.default != null ? `default: ${i.default}` : demo?.inputs[i.name] ? `e.g. ${demo.inputs[i.name]}` : ""}
                      onChange={(e) => edit(i.name, { value: e.target.value })} />
                  )}
                  <details className="run-assume"><summary className="caption">Assume instead{d.assume.trim() && <> — <code>{i.name}={d.assume}</code></>}</summary>
                    <label className="run-field mt-2"><span className="caption">Used only when the input above is empty; passed as <code>--assume {i.name}=…</code> and labelled <code>[ASSUMED]</code> in the outputs.</span>
                      <input className="input run-input-text" value={d.assume} placeholder="value to assume" onChange={(e) => edit(i.name, { assume: e.target.value })} />
                    </label>
                  </details>
                </div>
              );
            })}
            {inputs.length === 0 && <p className="none">No inputs.</p>}
          </div>

          <div className="h3 mt-6 mb-2" style={{ fontSize: 14 }}>Model</div>
          <div className="run-provider">
            <label className="run-field">
              <span className="caption">Anthropic API key (optional)</span>
              <input type="password" className="input run-input-text" value={key} autoComplete="off" placeholder="sk-ant-…" onChange={(e) => setKey(e.target.value)} />
              <span className="caption">Sent only to api.anthropic.com from your browser; not stored.</span>
            </label>
            <label className="run-field">
              <span className="caption">Model</span>
              <select className="select" value={model} onChange={(e) => setModel(e.target.value)}>{MODELS.map((m) => <option key={m}>{m}</option>)}</select>
            </label>
          </div>
          <p className="caption mt-2">No key: LLM steps are skipped, and the page says so — their outputs are absent and the checks on them fail.</p>

          <div className="flex flex-wrap items-center gap-3 mt-5">
            <button type="button" className="btn btn-primary" disabled={runtimeState !== "ready" || running} onClick={run}>{running ? "Running…" : "Run"}</button>
            <span className="caption">{runtimeState !== "ready" ? "Waiting for the runtime" : running ? "Python is running in a worker thread" : "Runs on your machine; nothing is uploaded except LLM prompts when you give a key."}</span>
          </div>

          {(log.length > 0 || running) && (
            <>
              <div className="h3 mt-6 mb-2" style={{ fontSize: 14 }}>Log</div>
              <pre className="run-log" ref={logRef} aria-live="polite">{log.map((l, k) => <span key={k} className={`run-log-${l.stream}`}>{l.stream === "cmd" ? "$ " : ""}{l.text.replace(/\n$/, "")}{"\n"}</span>)}{running && <span className="run-log-sys">…</span>}</pre>
            </>
          )}

          {result && banner && (
            <div className="run-results">
              <div className={`run-banner run-banner-${banner.tone}`} role="status">{banner.text}<span className="caption"> · exit {result.exitCode}</span></div>

              {result.needsInput && (
                <div className="tablewrap"><table className="mini mt-4"><thead><tr><th>Missing input</th><th>Type</th><th>What it is</th></tr></thead>
                  <tbody>{result.needsInput.missing.map((m) => <tr key={m.name}><td><code>{m.name}</code></td><td className="muted">{m.type}</td><td className="ink-2">{m.question}</td></tr>)}</tbody></table></div>
              )}

              {primary && (
                <div className="run-answer" ref={(el) => {
                  answerRef.current = el;
                  if (el && auto === "done" && !answerShown.current) {
                    answerShown.current = true;
                    requestAnimationFrame(() => {
                      el.querySelectorAll<HTMLElement>(".run-prose, .run-raw").forEach((p) => { p.scrollTop = 0; });
                      el.scrollIntoView({ behavior: "smooth", block: "start" });
                    });
                  }
                }}>
                  <div className="flex flex-wrap items-center justify-between gap-2 mb-2">
                    <div className="h3" style={{ margin: 0 }}>Result <span className="caption font-normal">· {primary.split("/").pop()}</span></div>
                    <button type="button" className="btn btn-secondary btn-sm" onClick={() => download(primary.split("/").pop() || primary, result.files[primary] ?? "")}>Download</button>
                  </div>
                  {primary.endsWith(".md")
                    ? <div className="prose run-prose" dangerouslySetInnerHTML={{ __html: mdToHtml(result.files[primary] ?? "") }} />
                    : <pre className="run-raw">{result.files[primary] ?? "(empty)"}</pre>}
                </div>
              )}

              {rj && (
                <details className="disclosure mt-5">
                  <summary><b>How it was checked</b> <span className="caption">— {rj.checks.filter((c) => c.pass).length} of {rj.checks.length} checks passed · {rj.steps.length} step{rj.steps.length === 1 ? "" : "s"}</span></summary>
                  <div className="h3 mt-4 mb-2" style={{ fontSize: 14 }}>Steps <span className="muted font-normal">({rj.steps.length})</span></div>
                  <div className="run-tablewrap"><table className="mini run-steps">
                    <thead><tr><th>Step</th><th>Kind</th><th>Status</th><th>Exit</th><th>Duration</th><th>Detail</th></tr></thead>
                    <tbody>{rj.steps.map((s) => (
                      <tr key={s.step}>
                        <td><code>{s.step}</code></td>
                        <td><span className={`agent-kind agent-kind-${s.kind}`}>{s.kind}</span></td>
                        <td>{s.skipped ? <span className="na-pill">skipped</span> : <PassPill pass={s.ok} />}</td>
                        <td className="muted">{s.exit ?? "—"}</td>
                        <td className="muted tnum">{s.duration_s != null ? `${s.duration_s}s` : "—"}</td>
                        <td className="ink-2">{s.skipped ? (s.skipped_reason ? `skipped — ${s.skipped_reason === "no provider key (LLM step not run)" ? "no provider key" : s.skipped_reason}` : s.reason) : s.ok ? (s.provider ? `provider ${s.provider}` : "") : s.error}</td>
                      </tr>
                    ))}</tbody>
                  </table></div>

                  <div className="h3 mt-6 mb-2" style={{ fontSize: 14 }}>Checks <span className="muted font-normal">({rj.checks.filter((c) => c.pass).length} of {rj.checks.length} passed)</span></div>
                  <div className="run-tablewrap"><table className="mini run-checks">
                    <thead><tr><th>File</th><th>Check</th><th>Result</th><th>Evidence</th></tr></thead>
                    <tbody>{rj.checks.map((c, k) => (
                      <tr key={k} className={c.pass ? "" : "run-row-fail"}>
                        <td><code>{rel(c.path).split("/").pop()}</code></td>
                        <td className="agent-check">{c.check.replaceAll(result.outDir + "/", "")}</td>
                        <td>{c.pass ? <PassPill pass /> : <span className="fail-pill">failed</span>}</td>
                        <td className="agent-evidence">{c.evidence.replaceAll(result.outDir + "/", "")}</td>
                      </tr>
                    ))}</tbody>
                  </table></div>
                </details>
              )}

              <div className="flex flex-wrap items-center justify-between gap-3 mt-6 mb-2">
                <div className="h3" style={{ fontSize: 14 }}>Output files <span className="muted font-normal">({outputFiles.length})</span></div>
                {result.runText && <button type="button" className="btn btn-secondary" onClick={() => download("run.json", result.runText!)}>Download run.json</button>}
              </div>
              {outputFiles.length === 0 && <p className="none">No output files were written.</p>}
              <ul className="run-files">
                {[...outputFiles, ...logFiles].map((p) => (
                  <li key={p}>
                    <code className="run-file-name">{p}</code>
                    <span className="run-file-actions">
                      <button type="button" className="btn btn-secondary btn-sm" onClick={() => setViewing(viewing?.path === p ? null : { path: p, raw: !p.endsWith(".md") })}>{viewing?.path === p ? "Hide" : "View"}</button>
                      <button type="button" className="btn btn-secondary btn-sm" onClick={() => download(p.split("/").pop() || p, result.files[p] ?? "")}>Download</button>
                    </span>
                  </li>
                ))}
              </ul>
              {viewing && (
                <div className="run-viewer">
                  <div className="flex flex-wrap items-center justify-between gap-2 mb-2">
                    <code className="run-file-name">{viewing.path}</code>
                    {viewing.path.endsWith(".md") && <button type="button" className="btn btn-secondary btn-sm" onClick={() => setViewing({ ...viewing, raw: !viewing.raw })}>{viewing.raw ? "Rendered" : "Raw"}</button>}
                  </div>
                  {viewing.raw || !viewing.path.endsWith(".md")
                    ? <pre className="run-raw">{result.files[viewing.path] ?? "(empty)"}</pre>
                    : <div className="prose run-prose" dangerouslySetInnerHTML={{ __html: mdToHtml(result.files[viewing.path] ?? "") }} />}
                </div>
              )}
            </div>
          )}
        </>
      )}
    </div>
  );
}

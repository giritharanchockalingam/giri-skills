/* Web Worker that runs scripts/run_skill.py in Pyodide (CPython compiled to WebAssembly).
 *
 * Why a worker: run_skill.py is synchronous Python, and so is the LLM provider it calls. A worker keeps the
 * page responsive while Python runs and lets the LLM bridge use a synchronous XMLHttpRequest (allowed in
 * workers, not on the main thread), which is the only way sync Python can wait for an HTTP reply.
 *
 * Messages in:  {type:"init", pyodideBase}  {type:"run", id, skill, inputs, assumptions, providerKey, model}
 *               {type:"read", id, path}
 * Messages out: {type:"progress", stage, message, pct?}  {type:"ready", python}  {type:"log", stream, text}
 *               {type:"result", id, ...}  {type:"file", id, path, content|null}  {type:"error", id?, message}
 *
 * The provider key only ever lives in a local variable for the duration of one run; it is never written to
 * the virtual FS, never logged, and never posted back.
 */
/* eslint-disable no-restricted-globals */
"use strict";

let pyodide = null;
let bundleFiles = 0;

const post = (m) => self.postMessage(m);
const progress = (stage, message, pct) => post({ type: "progress", stage, message, pct });

async function init(pyodideBase) {
  progress("runtime", "Loading Python runtime (≈10 MB, once)", 0);
  importScripts(pyodideBase + "pyodide.js");
  pyodide = await self.loadPyodide({ indexURL: pyodideBase });
  progress("runtime", "Python runtime loaded", 60);

  progress("repo", "Fetching skill files", 65);
  const res = await fetch("/runtime/bundle.json");
  if (!res.ok) throw new Error(`could not fetch /runtime/bundle.json (HTTP ${res.status})`);
  const bundle = await res.json();
  const paths = Object.keys(bundle);
  const FS = pyodide.FS;
  const mkdirp = (dir) => {
    const parts = dir.split("/").filter(Boolean);
    let cur = "";
    for (const p of parts) {
      cur += "/" + p;
      try { FS.mkdir(cur); } catch { /* exists */ }
    }
  };
  let n = 0;
  for (const rel of paths) {
    const full = "/repo/" + rel;
    mkdirp(full.slice(0, full.lastIndexOf("/")));
    FS.writeFile(full, bundle[rel], { encoding: "utf8" });
    n++;
    if (n % 100 === 0) progress("repo", `Writing skill files (${n}/${paths.length})`, 65 + Math.round((n / paths.length) * 30));
  }
  mkdirp("/repo/_inputs");
  mkdirp("/repo/_runs");
  bundleFiles = paths.length;

  pyodide.runPython(`
import os, sys
os.environ["RUN_SKILL_INPROC"] = "1"
if "/repo/scripts" not in sys.path:
    sys.path.insert(0, "/repo/scripts")
os.chdir("/repo")
import run_skill, check_output, behavioral_evals  # noqa: F401
`);
  const python = pyodide.runPython("import sys; sys.version.split()[0]");
  progress("ready", `Ready — Python ${python}, ${bundleFiles} files in /repo`, 100);
  post({ type: "ready", python, files: bundleFiles });
}

/* Synchronous HTTP call to the Anthropic Messages API. Sync XHR is what lets run_skill.py's
 * provider.complete() (plain blocking Python) get a reply. The key is a closure argument only. */
function makeLlmBridge(key) {
  return (system, user, model, maxTokens, temperature) => {
    const xhr = new XMLHttpRequest();
    xhr.open("POST", "https://api.anthropic.com/v1/messages", false);
    xhr.setRequestHeader("content-type", "application/json");
    xhr.setRequestHeader("x-api-key", key);
    xhr.setRequestHeader("anthropic-version", "2023-06-01");
    xhr.setRequestHeader("anthropic-dangerous-direct-browser-access", "true");
    const body = JSON.stringify({ model, max_tokens: Number(maxTokens), temperature: Number(temperature), system, messages: [{ role: "user", content: user }] });
    try {
      xhr.send(body);
    } catch (e) {
      throw new Error(`request to api.anthropic.com failed: ${e && e.message ? e.message : e}`);
    }
    if (xhr.status < 200 || xhr.status >= 300) {
      let detail = "";
      try { detail = JSON.parse(xhr.responseText).error.message; } catch { detail = (xhr.responseText || "").slice(0, 200); }
      throw new Error(`api.anthropic.com HTTP ${xhr.status}: ${detail}`);
    }
    const data = JSON.parse(xhr.responseText);
    return (data.content || []).filter((c) => c.type === "text").map((c) => c.text).join("");
  };
}

function readFile(path) {
  try { return pyodide.FS.readFile(path, { encoding: "utf8" }); } catch { return null; }
}
function listDir(path) {
  const out = [];
  const walk = (dir) => {
    let names;
    try { names = pyodide.FS.readdir(dir); } catch { return; }
    for (const nm of names) {
      if (nm === "." || nm === "..") continue;
      const full = `${dir}/${nm}`;
      let st;
      try { st = pyodide.FS.stat(full); } catch { continue; }
      if (pyodide.FS.isDir(st.mode)) walk(full); else out.push(full);
    }
  };
  walk(path);
  return out;
}

const extFor = (type) => ({ csv: "csv", json: "json", md: "md", txt: "txt", sql: "sql" }[type] || "txt");

function run(msg) {
  const { id, skill, inputs, assumptions, providerKey, model } = msg;
  const ts = Date.now();
  const outDir = `/repo/_runs/${ts}`;
  const inDir = `/repo/_inputs/${ts}`;
  const FS = pyodide.FS;
  try { FS.mkdir(inDir); } catch { /* exists */ }
  const argv = [skill];
  for (const [name, v] of Object.entries(inputs || {})) {
    if (v == null) continue;
    if (v.kind === "text") {
      const p = `${inDir}/${name}.${extFor(v.ext)}`;
      FS.writeFile(p, v.content, { encoding: "utf8" });
      argv.push("--input", `${name}=${p}`);
    } else if (v.kind === "value" && v.value !== "") {
      argv.push("--input", `${name}=${v.value}`);
    }
  }
  for (const [name, v] of Object.entries(assumptions || {})) if (v !== "") argv.push("--assume", `${name}=${v}`);
  argv.push("--out", outDir, "--provider", providerKey ? "jsbridge" : "none", "--model", model || "claude-sonnet-4-5", "--inproc");

  // stream the runner's own stdout/stderr (child scripts' output is captured into logs/ exactly as on the CLI)
  pyodide.setStdout({ batched: (text) => post({ type: "log", id, stream: "stdout", text }) });
  pyodide.setStderr({ batched: (text) => post({ type: "log", id, stream: "stderr", text }) });

  if (providerKey) pyodide.globals.set("__js_llm", makeLlmBridge(providerKey));
  else pyodide.globals.set("__js_llm", null);
  pyodide.globals.set("__argv", pyodide.toPy(argv));
  post({ type: "log", id, stream: "cmd", text: `python3 scripts/run_skill.py ${argv.map((a) => (/[\s"']/.test(a) ? JSON.stringify(a) : a)).join(" ")}` });

  let exitCode;
  try {
    exitCode = pyodide.runPython(`
import sys, importlib
import behavioral_evals, run_skill
behavioral_evals.JS_LLM_CALLBACK = __js_llm
sys.argv = ["run_skill.py"] + list(__argv)
try:
    _code = run_skill.main()
except SystemExit as _e:
    _code = _e.code
    if _code is None:
        _code = 0
    elif not isinstance(_code, int):
        print(_code, file=sys.stderr)
        _code = 1
finally:
    behavioral_evals.JS_LLM_CALLBACK = None
int(_code)
`);
  } catch (e) {
    post({ type: "log", id, stream: "stderr", text: String(e && e.message ? e.message : e) });
    exitCode = 1;
  } finally {
    pyodide.globals.set("__js_llm", null);
    pyodide.setStdout({ batched: () => {} });
    pyodide.setStderr({ batched: () => {} });
  }

  const runText = readFile(`${outDir}/run.json`);
  const needsText = readFile(`${outDir}/needs_input.json`);
  let runJson = null, needsInput = null;
  try { runJson = runText ? JSON.parse(runText) : null; } catch { runJson = null; }
  try { needsInput = needsText ? JSON.parse(needsText) : null; } catch { needsInput = null; }
  const files = {};
  for (const full of listDir(outDir)) {
    const rel = full.slice(outDir.length + 1);
    if (rel === "run.json" || rel === "needs_input.json") continue;
    files[rel] = readFile(full);
  }
  post({ type: "result", id, exitCode, outDir, runJson, runText, needsInput, files });
}

self.onmessage = async (ev) => {
  const msg = ev.data;
  try {
    if (msg.type === "init") await init(msg.pyodideBase);
    else if (msg.type === "run") run(msg);
    else if (msg.type === "read") post({ type: "file", id: msg.id, path: msg.path, content: readFile(msg.path) });
  } catch (e) {
    post({ type: "error", id: msg.id, message: String(e && e.message ? e.message : e) });
  }
};

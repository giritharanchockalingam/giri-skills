/* Self-service actions, the pure part: which form a skill needs to run on a repository, which repository files a
 * folder input takes, and whether the run uses a model (which decides approval under the default policy). */
import type { Manifest, InputSpec } from "@/lib/factory/manifest";
import { bound, type TreeFile } from "@/lib/scorecards/checks";

const SKIP = /(^|\/)(node_modules|\.next|dist|build|vendor|\.venv|__pycache__|coverage|\.git)\//;

/** What the person fills in: a repository folder for each folder input, text for the rest. */
export type ActionField =
  | { name: string; kind: "folder"; required: boolean; help: string; suggested: string }
  | { name: string; kind: "text"; required: boolean; help: string; multiline: boolean; defaultValue: string | null };
export type ActionInput = { folder: string } | { text: string };

export const usesModel = (m: Pick<Manifest, "run">) => m.run.some((s) => s.kind === "llm");

/** The repository's folders (for the folder picker), most files first, capped. */
export function foldersOf(tree: TreeFile[], max = 300): string[] {
  const n = new Map<string, number>();
  for (const f of tree) {
    if (SKIP.test(f.path)) continue;
    const parts = f.path.split("/").slice(0, -1);
    for (let i = 1; i <= parts.length; i++) { const d = parts.slice(0, i).join("/"); n.set(d, (n.get(d) ?? 0) + 1); }
  }
  return [".", ...[...n.entries()].sort((a, b) => a[0].localeCompare(b[0])).map(([d]) => d)].slice(0, max);
}

export function fieldsFor(m: Pick<Manifest, "inputs">, suggested: Record<string, string> = {}): ActionField[] {
  return m.inputs.map((i: InputSpec) => i.type === "dir"
    ? { name: i.name, kind: "folder" as const, required: i.required, help: i.from || "a folder of the repository", suggested: suggested[i.name] ?? "." }
    : { name: i.name, kind: "text" as const, required: i.required && i.default == null, help: i.from || i.type, multiline: ["csv", "json", "md", "txt", "file", "sql"].includes(i.type),
        defaultValue: i.default == null ? null : String(i.default) });
}

/** The files a folder input takes: everything under the folder ('.' = the whole repository), bounded like scorecards. */
export function filesUnder(tree: TreeFile[], folder: string): { files: TreeFile[]; partial: boolean; strip: string } {
  const f = folder.replace(/^\.?\/*|\/+$/g, "");
  if (f.split("/").some((p) => p === "..")) return { files: [], partial: false, strip: f };
  const under = tree.filter((t) => !SKIP.test(t.path) && (f === "" || t.path.startsWith(`${f}/`)));
  const b = bound(under);
  return { files: b.files, partial: b.partial, strip: f };
}

/** Validate what was asked against the form: folders must exist in the repository; required inputs present. */
export function checkRequest(fields: ActionField[], given: Record<string, ActionInput>, folders: string[]): string[] {
  const problems: string[] = [];
  for (const k of Object.keys(given)) if (!fields.some((f) => f.name === k)) problems.push(`${k}: not an input of this skill`);
  for (const f of fields) {
    const v = given[f.name];
    if (f.kind === "folder") {
      if (!v) { if (f.required) problems.push(`${f.name}: choose a folder`); continue; }
      if (!("folder" in v)) { problems.push(`${f.name}: expects a folder`); continue; }
      const norm = v.folder.replace(/^\.?\/*|\/+$/g, "") || ".";
      if (!folders.includes(norm)) problems.push(`${f.name}: no folder “${v.folder}” in the repository`);
    } else {
      const t = v && "text" in v ? v.text.trim() : "";
      if (!t && f.required) problems.push(`${f.name}: required`);
      if (v && !("text" in v)) problems.push(`${f.name}: expects text`);
    }
  }
  return problems;
}

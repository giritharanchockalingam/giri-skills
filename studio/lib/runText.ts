/* What failed in a run, in plain words (mirrors api/py/run.py failure_summary for in-browser runs). Pure. */
type Step = { step?: string; ok?: boolean; error?: string; exit?: number | null };
type Check = { pass?: boolean; check?: string; path?: string };
export function failureText(rj: { steps: Step[]; checks: Check[] }): string {
  const bad = rj.steps.filter((s) => !s.ok), badC = rj.checks.filter((c) => !c.pass);
  const parts = bad.slice(0, 3).map((s) => {
    const e = (s.error ?? "").trim();
    return /^gate:/i.test(e) ? `the skill's gate in step '${s.step}' said ${e.slice(5).trim()}` : `step '${s.step ?? "?"}' failed${e ? `: ${plainError(e)}` : s.exit != null ? ` (exit ${s.exit})` : ""}`;
  });
  if (bad.length > 3) parts.push(`${bad.length - 3} more step(s) failed`);
  if (badC.length) parts.push(`${badC.length} output check(s) failed, e.g. ${badC[0].check ?? "?"} on ${(badC[0].path ?? "?").split("/").pop()}`);
  // name the failure class, so the headline never contradicts "all checks passed" shown below it
  // (a gate saying FAIL is the skill's verdict, not an error, so it is reported as is)
  if (bad.length && !badC.length && !bad.every((s) => /^gate:/i.test((s.error ?? "").trim()))) return `${rj.checks.length ? "a step errored, although every check that ran passed" : "a step errored before any check ran"} — ${parts.join("; ")}`;
  return parts.join("; ") || "the run did not complete";
}

/* Engine messages people meet, in plain words. The raw text is never lost: pages show it under "Technical detail". */
const PLAIN: [RegExp, (m: RegExpExecArray) => string][] = [
  [/model '([^']+)' has no row in the price sheet/i, (m) => `the cost model has no price for the model used (${m[1]})`],
  [/concurrency limit reached/i, () => "too many runs were in progress at once; try again shortly"],
  [/monthly budget reached/i, () => "the workspace's monthly budget is used up"],
  [/Traceback \(most recent call last\)/, () => "the step's program stopped with an error"],
  [/not_in_role/i, () => "this skill is not in any job role assigned to the caller"],
  [/\b(timed out|timeout)\b/i, () => "it took longer than allowed"],
];
/** A raw engine message → a plain sentence (unknown messages pass through, first line only). Pure. */
export function plainError(raw: string): string {
  const t = raw.trim();
  for (const [re, f] of PLAIN) { const m = re.exec(t); if (m) return f(m); }
  return t.split("\n")[0];
}

/** Older runs stored a generic count ("1 step(s) not ok, 0 check(s) failed"); lists show it in plain words and without
 *  the zero half that read like a contradiction. Specific messages pass through unchanged. Pure. */
export function readableError(error: string | null | undefined): string {
  if (!error) return "";
  const m = /^(\d+) step\(s\) not ok, (\d+) check\(s\) failed\s*(?:\((?:partial:\s*)?(.+)\))?$/.exec(error.trim());
  if (!m) return plainError(error);
  const [steps, checks] = [Number(m[1]), Number(m[2])];
  const part = (n: number, one: string, many: string) => `${n} ${n === 1 ? one : many} failed`;
  const what = [steps && part(steps, "step", "steps"), checks && part(checks, "output check", "output checks")].filter(Boolean).join(" and ");
  return m[3] ? `Output incomplete: ${m[3].replace(/\.$/, "")}.` : `${what} (open the run for which)`;
}

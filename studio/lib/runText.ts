/* What failed in a run, in plain words (mirrors api/py/run.py failure_summary for in-browser runs). Pure. */
type Step = { step?: string; ok?: boolean; error?: string; exit?: number | null };
type Check = { pass?: boolean; check?: string; path?: string };
export function failureText(rj: { steps: Step[]; checks: Check[] }): string {
  const bad = rj.steps.filter((s) => !s.ok), badC = rj.checks.filter((c) => !c.pass);
  const parts = bad.slice(0, 3).map((s) => {
    const e = (s.error ?? "").trim();
    return /^gate:/i.test(e) ? `the skill's gate in step '${s.step}' said ${e.slice(5).trim()}` : `step '${s.step ?? "?"}' failed${e ? `: ${e}` : s.exit != null ? ` (exit ${s.exit})` : ""}`;
  });
  if (bad.length > 3) parts.push(`${bad.length - 3} more step(s) failed`);
  if (badC.length) parts.push(`${badC.length} output check(s) failed, e.g. ${badC[0].check ?? "?"} on ${(badC[0].path ?? "?").split("/").pop()}`);
  return parts.join("; ") || "the run did not complete";
}

/** Older runs stored a generic count ("1 step(s) not ok, 0 check(s) failed"); lists show it in plain words and without
 *  the zero half that read like a contradiction. Specific messages pass through unchanged. Pure. */
export function readableError(error: string | null | undefined): string {
  if (!error) return "";
  const m = /^(\d+) step\(s\) not ok, (\d+) check\(s\) failed$/.exec(error.trim());
  if (!m) return error;
  const [steps, checks] = [Number(m[1]), Number(m[2])];
  const part = (n: number, one: string, many: string) => `${n} ${n === 1 ? one : many} failed`;
  return [steps && part(steps, "step", "steps"), checks && part(checks, "output check", "output checks")].filter(Boolean).join(" and ") + " (open the run for which)";
}

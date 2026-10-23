/* Workflow orchestrator — the pure parts: verify a GitHub webhook, normalise the events we act on, match
 * automations, and render the GitHub Check Run. No I/O here (process.ts does it); every rule is unit-tested. */
import { createHmac, timingSafeEqual } from "node:crypto";

/** X-Hub-Signature-256 = "sha256=" + HMAC-SHA256(raw body, webhook secret). Constant-time compare. */
export function verifySignature(raw: string, header: string | null, secret: string): boolean {
  if (!header?.startsWith("sha256=") || !secret) return false;
  const want = Buffer.from(createHmac("sha256", secret).update(raw, "utf8").digest("hex"));
  const got = Buffer.from(header.slice(7));
  return got.length === want.length && timingSafeEqual(got, want);
}

export type NormEvent =
  | { kind: "pull_request"; installationId: number; repo: string; sha: string; baseSha: string | null; pr: number; title: string; fromFork: boolean }
  | { kind: "push"; installationId: number; repo: string; sha: string }
  | { kind: "repos_changed"; installationId: number };

type Payload = Record<string, unknown> & {
  action?: string; installation?: { id?: number }; repository?: { full_name?: string; default_branch?: string };
  pull_request?: { number?: number; title?: string; head?: { sha?: string; repo?: { full_name?: string } | null }; base?: { sha?: string; repo?: { full_name?: string } }; draft?: boolean };
  ref?: string; after?: string; deleted?: boolean;
  check_run?: { head_sha?: string; pull_requests?: { number?: number; head?: { sha?: string }; base?: { sha?: string } }[] };
};
const SHA = /^[0-9a-f]{40}$/;
const PR_ACTIONS = new Set(["opened", "synchronize", "reopened", "ready_for_review"]);

/** The events the orchestrator acts on; everything else is acknowledged and ignored (null). */
export function normalize(event: string, p: Payload): NormEvent | null {
  const installationId = Number(p.installation?.id);
  if (!Number.isSafeInteger(installationId) || installationId <= 0) return null;
  if (event === "installation_repositories" || (event === "installation" && ["created", "new_permissions_accepted", "unsuspend"].includes(p.action ?? ""))) {
    return { kind: "repos_changed", installationId };
  }
  const repo = p.repository?.full_name;
  if (!repo || !/^[\w.-]+\/[\w.-]+$/.test(repo)) return null;
  if (event === "pull_request" && PR_ACTIONS.has(p.action ?? "") && !p.pull_request?.draft) {
    const sha = p.pull_request?.head?.sha ?? "";
    const pr = Number(p.pull_request?.number);
    if (!SHA.test(sha) || !Number.isSafeInteger(pr)) return null;
    // the base commit lets findings.csv checks score only what the PR adds; a payload without one still scores (absolute)
    const baseSha = p.pull_request?.base?.sha ?? "";
    return { kind: "pull_request", installationId, repo, sha, baseSha: SHA.test(baseSha) ? baseSha : null, pr, title: String(p.pull_request?.title ?? "").slice(0, 200),
      fromFork: (p.pull_request?.head?.repo?.full_name ?? repo) !== (p.pull_request?.base?.repo?.full_name ?? repo) };
  }
  if (event === "push" && !p.deleted && p.ref === `refs/heads/${p.repository?.default_branch}` && SHA.test(p.after ?? "")) {
    return { kind: "push", installationId, repo, sha: p.after! };
  }
  // "Re-run" on our own check in GitHub's Checks tab (GitHub sends check_run.rerequested only to the app that owns the
  // check): the same commit is scored again — as the pull request it belongs to, or as a default-branch commit
  if (event === "check_run" && p.action === "rerequested") {
    const sha = p.check_run?.head_sha ?? "";
    if (!SHA.test(sha)) return null;
    const pr = (p.check_run?.pull_requests ?? []).find((x) => Number.isSafeInteger(Number(x.number)) && (x.head?.sha ?? sha) === sha);
    if (pr) {
      const baseSha = pr.base?.sha ?? "";
      return { kind: "pull_request", installationId, repo, sha, baseSha: SHA.test(baseSha) ? baseSha : null, pr: Number(pr.number), title: "", fromFork: false };
    }
    return { kind: "push", installationId, repo, sha };
  }
  return null;
}

export interface AutomationRow { id: string; name: string; trigger: "github.pull_request" | "github.push"; repos: string[]; checks: string[]; report_to_github: boolean; enabled: boolean; created_by: string }

export function matchAutomations(e: NormEvent, autos: AutomationRow[]): AutomationRow[] {
  if (e.kind === "repos_changed") return [];
  const trigger = e.kind === "pull_request" ? "github.pull_request" : "github.push";
  return autos.filter((a) => a.enabled && a.trigger === trigger && (a.repos.length === 0 || a.repos.includes(e.repo)));
}

/** The checks to run once for all matching automations (empty list on any automation = every applicable check). */
export const unionChecks = (autos: AutomationRow[]): string[] | undefined =>
  autos.some((a) => a.checks.length === 0) ? undefined : [...new Set(autos.flatMap((a) => a.checks))];

export interface ResultLine { check: string; title: string; verdict: string; summary: string }
export type Conclusion = "success" | "failure" | "neutral";

/** GitHub Check Run output: failure if any check fails or errors on the skill's own verdict; neutral on warnings
 *  or when nothing ran; success only when every check that ran passed. */
export function checkRunOutput(results: ResultLine[], detailsUrl: string, prefix = ""): { conclusion: Conclusion; title: string; summary: string } {
  const ran = results.filter((r) => r.verdict !== "skipped");
  const fail = ran.filter((r) => r.verdict === "fail" || r.verdict === "error");
  const warn = ran.filter((r) => r.verdict === "warn");
  const conclusion: Conclusion = !ran.length ? "neutral" : fail.length ? "failure" : warn.length ? "neutral" : "success";
  const title = !ran.length ? "No scorecard checks apply" : fail.length ? `${fail.length} of ${ran.length} checks failed` : warn.length ? `${warn.length} warning(s), no failures` : `All ${ran.length} checks passed`;
  const icon = (v: string) => (v === "pass" ? "✅" : v === "warn" ? "⚠️" : v === "skipped" ? "➖" : "❌");
  const esc = (s: string) => s.replace(/\|/g, "\\|").replace(/\r?\n/g, " ");
  const summary = [
    prefix,
    "| Check | Verdict | Summary |", "|---|---|---|",
    ...results.map((r) => `| ${esc(r.title)} | ${icon(r.verdict)} ${r.verdict} | ${esc(r.summary)} |`),
    "", `Each verdict is the library skill's own, on this commit's files. Evidence: ${detailsUrl}`,
  ].filter((l, i) => i > 0 || l).join("\n");
  return { conclusion, title, summary: summary.slice(0, 60_000) };
}

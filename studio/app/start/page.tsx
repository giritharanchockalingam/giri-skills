import Link from "next/link";
import { PageHead } from "@/components/PageHead";

export const metadata = { title: "Start here · Skills Factory" };

/* "How it fits together": the one page that tells the story connecting the skills, the factory and the scorecards.
 * Copy is final (owner brief, WP1) — change it only with the owner. Public: readable before sign-in; no data. */
export default function StartPage() {
  return (
    <>
      <PageHead eyebrow="Start here" title="How it fits" em="together" after="." lead="One story, four parts. Read this once and every page in this portal makes sense." />
      <article className="prose start" style={{ maxWidth: 720 }}>
        <h3>Skills are everywhere now.</h3>
        <p>A skill is a packaged capability that does one job — estimate a project, check a decision system for bias, inventory where your PII lives. Anyone can write one in an afternoon, and thousands of people have.</p>
        <p>That&apos;s the opportunity. It&apos;s also the problem.</p>

        <h3>An untested skill is a liability.</h3>
        <p>A skill doesn&apos;t sit in a document. It runs — with your tools, against your code and your data. A bad one rarely crashes loudly. It produces a confident, plausible, wrong answer, and somebody acts on it.</p>
        <p>Until now, there was no way to tell a good skill from a plausible one.</p>

        <h3>So every skill here is tested before it&apos;s trusted.</h3>
        <p>Before a skill can be used, it is evaluated. It runs against test cases — with its instructions and without them — and two things are measured:</p>
        <ul>
          <li><b>Trigger</b> — when someone asks for this job, does the right skill get picked?</li>
          <li><b>Lift</b> — do the skill&apos;s instructions actually make the answer better than the model would do alone?</li>
        </ul>
        <p>Skills that pass are reviewed, approved, and published. Only published versions can be run from people&apos;s tools. The evidence stays attached to the skill, where anyone can read it — including the skills that are still being improved, labelled as such.</p>

        <h3>And the ground it stands on gets graded too.</h3>
        <p>Skills run against repositories, services, and databases. If that code is insecure or unmaintained, even a good skill does damage. So connected repositories get <b>scorecards</b>: real checks that run against the code — database security, tenant isolation, conventions, observability — graded Bronze, Silver, or Gold. A scorecard says exactly what failed, and where.</p>
        <p>That&apos;s why a skills portal grades code. The skills are only as trustworthy as what they stand on.</p>

        <h2>The four areas are the four chapters</h2>
        <p><b><Link href="/">Use</Link> — for everyone.</b> Find, run, and connect skills. Start at <b>Find</b>: describe the work, get a tested skill for it. Or connect your own tools — Claude Code, Cursor, VS Code — and call published skills from there. That connection is called <b>MCP</b>: the standard plug that lets an AI tool use these skills.</p>
        <p><b><Link href="/pipeline">Build</Link> — for skill owners.</b> The factory floor. Import or author a skill, evaluate it, get it approved, publish it. The Publish pipeline shows what stands between each skill and release.</p>
        <p><b><Link href="/inbox">Govern</Link> — for governance and risk.</b> Approvals, runs, and insights. What&apos;s waiting on a person, what ran, what it cost, and what it delivered — with estimates labelled as estimates.</p>
        <p><b><Link href="/catalog">Platform</Link> — for platform teams.</b> Repositories, services, databases, and the automations that keep their scorecards current.</p>

        <h2>The words, once</h2>
        <ul>
          <li><b>Skill</b> — a packaged capability that does one job.</li>
          <li><b>Playbook</b> — skills chained in order, with approvals where a person decides.</li>
          <li><b>Evaluation</b> — the test evidence behind a skill (trigger and lift, above).</li>
          <li><b>Scorecard</b> — a grade for a repository, from checks that actually ran.</li>
          <li><b>MCP</b> — the standard connection that lets your AI tools call published skills.</li>
        </ul>

        <h2>Where to start</h2>
        <ul>
          <li><b>I need work done</b> → <Link href="/">Find</Link>.</li>
          <li><b>I build skills</b> → <Link href="/pipeline">Publish pipeline</Link>.</li>
          <li><b>I&apos;m accountable for the risk</b> → <Link href="/inbox">Inbox</Link> and <Link href="/insights">Insights</Link>.</li>
        </ul>

        <p><em>That&apos;s the whole product. Everything else is detail — and from here, every page explains itself.</em></p>
      </article>
    </>
  );
}

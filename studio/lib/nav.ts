/* The portal's information architecture, in one place: top-level sections, the pages inside each (shown as tabs under
 * the top bar), and the one name each concept goes by. Nav, section tabs, the phone menu and the glossary all read this. */

export interface Page { href: string; label: string; match: (path: string, query: URLSearchParams) => boolean }
export interface Section { id: string; label: string; href: string; hint: string; who: string; match: (path: string) => boolean; pages: Page[] }

const starts = (...p: string[]) => (path: string) => p.some((x) => path === x || path.startsWith(`${x}/`));
const type = (t: string | null) => (path: string, q: URLSearchParams) => path === "/catalog" && (q.get("type") ?? null) === t;

export const SECTIONS: Section[] = [
  {
    id: "use", label: "Use", href: "/", who: "For everyone: find a skill that works and run it, here or from your own tools",
    hint: "Find, run and connect skills",
    match: (p) => p === "/" || starts("/repo", "/agents", "/agent-runs", "/connect", "/assistant")(p),
    pages: [
      { href: "/", label: "Find", match: (p) => p === "/" },
      { href: "/repo/", label: "Library", match: starts("/repo") },
      { href: "/agents", label: "Playbooks", match: starts("/agents", "/agent-runs") },
      { href: "/connect", label: "Connect your tools", match: starts("/connect") },
      { href: "/assistant", label: "Assistant", match: starts("/assistant") },
    ],
  },
  {
    id: "build", label: "Build", href: "/pipeline", who: "For skill owners: build, test and publish skills",
    hint: "Publish pipeline, evaluations, reference skills",
    match: starts("/pipeline", "/skills", "/evaluations", "/evals", "/findings", "/upstream"),
    pages: [
      { href: "/pipeline", label: "Publish pipeline", match: (p) => starts("/pipeline", "/skills")(p) },
      { href: "/evaluations", label: "Evaluations", match: starts("/evaluations", "/evals", "/findings") },
      { href: "/upstream", label: "Reference skills", match: starts("/upstream") },
    ],
  },
  {
    id: "govern", label: "Govern", href: "/inbox", who: "For governance and risk: approve releases, audit runs, track spend and value",
    hint: "Approvals, runs, insights",
    match: starts("/inbox", "/activity", "/runs", "/insights"),
    pages: [
      { href: "/inbox", label: "Inbox", match: starts("/inbox") },
      { href: "/activity", label: "Runs", match: starts("/activity", "/runs") },
      { href: "/insights", label: "Insights", match: starts("/insights") },
    ],
  },
  {
    id: "platform", label: "Platform", href: "/catalog", who: "For platform teams: the systems skills run on, and the checks enforced on every change",
    hint: "Repositories, services, databases, automations",
    match: starts("/catalog", "/automations", "/initiatives", "/ai-assets"),
    pages: [
      { href: "/catalog", label: "Repositories", match: (p, q) => type(null)(p, q) || (p.startsWith("/catalog/") && !q.get("type")) },
      { href: "/catalog?type=service", label: "Services", match: type("service") },
      { href: "/catalog?type=database", label: "Databases", match: type("database") },
      { href: "/automations", label: "Automations", match: starts("/automations") },
      { href: "/initiatives", label: "Initiatives", match: starts("/initiatives") },
      { href: "/ai-assets", label: "AI assets", match: starts("/ai-assets") },
    ],
  },
  {
    id: "admin", label: "Admin", href: "/admin", who: "For administrators: access, keys, integrations and policies",
    hint: "Members, keys, roles, teams, integrations, audit log",
    match: starts("/admin", "/glossary", "/roles", "/pools", "/integrations"),
    pages: [
      { href: "/admin", label: "Administration", match: starts("/admin") },
      { href: "/roles", label: "Roles", match: starts("/roles") },
      { href: "/pools", label: "Teams", match: starts("/pools") },
      { href: "/integrations", label: "Integrations", match: starts("/integrations") },
      { href: "/glossary", label: "Glossary", match: starts("/glossary") },
    ],
  },
];

export const sectionOf = (path: string) => SECTIONS.find((s) => s.match(path)) ?? null;

/** One name per concept. Code and URLs may use older words (agents, pools, repo); the interface never does. */
export const GLOSSARY: { term: string; means: string; not: string[]; where: string }[] = [
  { term: "AI development lifecycle (ADLC)", means: "The 11 stages from strategy to improvement that the library is organised by (Home shows them); every skill belongs to one stage.", not: ["SDLC (for AI work)"], where: "/" },
  { term: "Skill", means: "A packaged capability that does one job: declared inputs, scripts and/or a model step, and an output contract that is checked on every run.", not: ["agent (for a single skill)", "tool"], where: "/repo/" },
  { term: "Library", means: "Every skill this portal ships (from the giri-skills repository), whether or not your workspace has imported it.", not: ["repository catalog", "repo"], where: "/repo/" },
  { term: "Workspace skill", means: "A library skill imported into your workspace, with its own versions, evaluations and approvals.", not: [], where: "/pipeline" },
  { term: "Published", means: "A workspace skill version that passed its release gates and was approved; only published versions are exposed over MCP and the API.", not: ["live", "released"], where: "/pipeline" },
  { term: "Instructions", means: "The SKILL.md text that tells a model how to use a skill.", not: ["authoring"], where: "/repo/" },
  { term: "Reference skill", means: "A skill vendored from a public GitHub repository, pinned to a commit; read-only.", not: ["upstream skill"], where: "/upstream" },
  { term: "Playbook", means: "Skills chained in order, with inputs wired between steps and optional approval gates.", not: ["agent", "pipeline"], where: "/agents" },
  { term: "Role", means: "A job (e.g. architect) defined by the skills it owns; tailorable.", not: [], where: "/roles" },
  { term: "Team", means: "Roles working together on one outcome, with hand-offs between them.", not: ["talent pool", "pool", "squad"], where: "/pools" },
  { term: "Run", means: "One execution of one skill. Counted on the server (portal, API, MCP, playbook steps) and, separately, in the browser.", not: ["job", "execution"], where: "/activity" },
  { term: "Evaluation", means: "Running a skill against its test cases to measure trigger accuracy, output quality and lift over no skill.", not: ["eval run (in the interface)"], where: "/evaluations" },
  { term: "Trigger", means: "How often a skill is picked for prompts it should handle (and not for prompts it should not).", not: [], where: "/evaluations" },
  { term: "Lift", means: "How much better the output is with the skill than without it, on the same cases.", not: [], where: "/evaluations" },
  { term: "Repository", means: "A GitHub repository in the catalog.", not: ["repo (in prose)"], where: "/catalog" },
  { term: "Service", means: "A deployed application (a Vercel project) in the catalog.", not: ["app", "project (alone)"], where: "/catalog?type=service" },
  { term: "Database", means: "A Supabase project in the catalog.", not: [], where: "/catalog?type=database" },
  { term: "Scorecard", means: "The latest verdict of each check on a repository's default branch, and the level that follows.", not: [], where: "/catalog" },
  { term: "Initiative", means: "A scorecard level set as a goal for some repositories, with an owner and a deadline.", not: ["campaign"], where: "/initiatives" },
  { term: "Action", means: "Running a skill on a catalog repository's files, with approval when policy requires it.", not: ["self-service action (in labels)"], where: "/catalog" },
  { term: "Automation", means: "A rule: when a GitHub event happens, run checks and report back.", not: ["workflow", "trigger"], where: "/automations" },
];

import { test } from "node:test";
import assert from "node:assert/strict";
import { mapPortCatalog, repoKeyOf, skipBlueprint } from "../lib/integrations/port/catalog.ts";

const blueprints = [
  { identifier: "githubRepository", title: "GitHub Repository", relations: {} },
  { identifier: "githubPullRequest", title: "GitHub Pull Request", schema: { properties: { status: { title: "Status" }, link: { title: "Link" } } }, relations: { repository: { target: "githubRepository" } } },
  { identifier: "_team", title: "Team" }, { identifier: "aiSkill", title: "AI Skill" },
];
test("port catalog: native repos are aliased (no duplicate); PRs become components linked to the repo; system and skill types skipped", () => {
  const entities = new Map([
    ["githubRepository", [{ identifier: "giri-skills", title: "giri-skills", properties: { url: "https://github.com/giritharanchockalingam/giri-skills" } },
                          { identifier: "other", title: "other", properties: { url: "https://github.com/acme/other" } }]],
    ["githubPullRequest", [{ identifier: "giri-skills51", title: "Port integration", properties: { status: "merged", link: "https://github.com/giritharanchockalingam/giri-skills/pull/51" }, relations: { repository: "giri-skills" }, updatedAt: "2026-10-20T20:00:00Z" }]],
    ["_team", [{ identifier: "t1" }]], ["aiSkill", [{ identifier: "llm-cost-model" }]],
  ]);
  const r = mapPortCatalog({ blueprints, entities, nativeRepoKeys: new Set(["giritharanchockalingam/giri-skills"]), fallbackUrl: "https://example.org" });
  assert.equal(r.aliases, 1);
  assert.deepEqual(r.components.map((c) => c.key).sort(), ["githubPullRequest:giri-skills51", "githubRepository:other"]);
  const pr = r.components.find((c) => c.key.startsWith("githubPullRequest"))!;
  assert.equal(pr.url, "https://github.com/giritharanchockalingam/giri-skills/pull/51", "the entity's own link, never a Port page");
  assert.equal(pr.properties.type, "GitHub Pull Request");
  assert.deepEqual(pr.properties.facts, [{ label: "Status", value: "merged" }]);
  assert.deepEqual(r.relations, [{ from: { kind: "component", key: "githubPullRequest:giri-skills51" }, to: { kind: "repository", key: "giritharanchockalingam/giri-skills" }, evidence: "GitHub Pull Request → repository" }]);
  assert.ok(skipBlueprint("_team") && skipBlueprint("aiSkill") && !skipBlueprint("service"));
  assert.equal(repoKeyOf({ identifier: "x", properties: { url: "https://github.com/A/B.git" } }), "a/b");
  assert.equal(repoKeyOf({ identifier: "x", properties: { url: "https://github.com/a/b/pull/3" } }), null);
});

test("port catalog: multi-line text (file contents) is not a detail", () => {
  const r = mapPortCatalog({ blueprints: [{ identifier: "service", title: "Service" }], entities: new Map([["service", [{ identifier: "s", properties: { gitignore: "a\nb", owner: "team-x" } }]]]), nativeRepoKeys: new Set(), fallbackUrl: "https://example.org" });
  assert.deepEqual(r.components[0].properties.facts, [{ label: "owner", value: "team-x" }]);
});

-- Behavioural tests for the sf_ schema: RLS per role, immutability trigger, stale approval, eval gate,
-- publish RPC, API-key RPCs. Runs under tests/sql/run.sh against a local PostgreSQL with supabase_stub.sql.
-- Every block raises (and aborts the script via ON_ERROR_STOP) when an expectation fails.
\set ON_ERROR_STOP on
\set QUIET on

insert into auth.users (id, email) values
  ('00000000-0000-0000-0000-000000000001', 'admin@example.test'),
  ('00000000-0000-0000-0000-000000000002', 'author@example.test'),
  ('00000000-0000-0000-0000-000000000003', 'reviewer@example.test'),
  ('00000000-0000-0000-0000-000000000004', 'consumer@example.test'),
  ('00000000-0000-0000-0000-000000000005', 'outsider@example.test');

-- helper: act as a user (role authenticated + JWT sub)
create or replace function test_as(p_user text) returns void language plpgsql as $$
begin
  perform set_config('request.jwt.claim.sub', p_user, false);
  perform set_config('role', 'authenticated', false);
end $$;
create or replace function test_as_anon() returns void language plpgsql as $$
begin
  perform set_config('request.jwt.claim.sub', '', false);
  perform set_config('role', 'anon', false);
end $$;
create or replace function test_expect_error(p_sql text, p_fragment text) returns void language plpgsql as $$
begin
  begin
    execute p_sql;
  exception when others then
    if position(p_fragment in sqlerrm) = 0 then
      raise exception 'expected error containing [%] but got [%]', p_fragment, sqlerrm;
    end if;
    return;
  end;
  raise exception 'expected an error containing [%] but the statement succeeded: %', p_fragment, p_sql;
end $$;
create or replace function test_assert(p_cond boolean, p_msg text) returns void language plpgsql as $$
begin
  if not coalesce(p_cond, false) then raise exception 'assertion failed: %', p_msg; end if;
end $$;

-- ───────── 1. workspace bootstrap: first user becomes admin ─────────
select test_as('00000000-0000-0000-0000-000000000001');
select sf_create_workspace('Acme Factory', 'acme') as ws \gset
select test_assert((select role from sf_memberships where workspace_id = :'ws' and user_id = auth.uid()) = 'admin', 'creator is admin');
select test_assert((select count(*) from sf_policies where workspace_id = :'ws') = 1, 'default policy row');

-- admin adds members (RLS insert policy)
insert into sf_memberships (workspace_id, user_id, role) values
  (:'ws', '00000000-0000-0000-0000-000000000002', 'author'),
  (:'ws', '00000000-0000-0000-0000-000000000003', 'reviewer'),
  (:'ws', '00000000-0000-0000-0000-000000000004', 'consumer');
select test_assert((select count(*) from sf_member_directory(:'ws')) = 4, 'member directory lists 4 with emails');
select test_assert(sf_user_id_by_email('Author@example.test') = '00000000-0000-0000-0000-000000000002', 'email lookup');

-- outsider sees nothing and cannot join
select test_as('00000000-0000-0000-0000-000000000005');
select test_assert((select count(*) from sf_workspaces) = 0, 'outsider sees no workspace');
select test_expect_error($$insert into sf_memberships (workspace_id, user_id, role) values ('$$ || :'ws' || $$', '00000000-0000-0000-0000-000000000005', 'admin')$$, 'row-level security');

-- consumer cannot add members or create skills
select test_as('00000000-0000-0000-0000-000000000004');
select test_expect_error($$insert into sf_skills (workspace_id, slug, name, owner_id) values ('$$ || :'ws' || $$', 'x', 'X', '00000000-0000-0000-0000-000000000004')$$, 'row-level security');

-- ───────── 2. author creates a skill + v1 draft ─────────
select test_as('00000000-0000-0000-0000-000000000002');
insert into sf_skills (workspace_id, slug, name, owner_id, purpose) values (:'ws', 'invoice-check', 'Invoice check', auth.uid(), 'Validate an invoice against a PO')
  returning id as skill \gset
insert into sf_skill_versions (skill_id, version, manifest, manifest_hash, created_by)
  values (:'skill', 1,
          '{"inputs":[{"name":"invoice","type":"json","required":true}],"outputs":[{"path":"{out}/result.json","checks":["exists","json"]}],"release_criteria":{"min_eval_pass_rate":0.8,"require_approval":true}}',
          repeat('a', 64), auth.uid())
  returning id as v1 \gset
update sf_skills set latest_version_id = :'v1' where id = :'skill';
insert into sf_files (version_id, path, content, sha256) values (:'v1', 'scripts/check.py', 'print(1)', repeat('b', 64));
select test_expect_error($$insert into sf_files (version_id, path, content, sha256) values ('$$ || :'v1' || $$', '../etc/passwd', 'x', repeat('b', 64))$$, 'check');
insert into sf_eval_cases (version_id, name, inputs, checks) values (:'v1', 'happy', '{"invoice":"x"}', '["exit:0"]') returning id as case1 \gset

-- release state before anything: not publishable
select test_assert((select publishable from sf_version_release_state where version_id = :'v1') = false, 'draft without eval/approval is not publishable');
select test_assert((select eval_gate_met from sf_version_release_state where version_id = :'v1') = false, 'eval gate unmet without a run');
select test_expect_error($$select sf_publish_version('$$ || :'v1' || $$')$$, 'no valid approval');

-- ───────── 3. consumer may not run a draft; author may ─────────
select test_as('00000000-0000-0000-0000-000000000004');
select test_expect_error($$select sf_run_insert('$$ || :'v1' || $$', 'ui', '[]'::jsonb)$$, 'consumers can only run published');
select test_as('00000000-0000-0000-0000-000000000002');
select (sf_run_insert(:'v1', 'ui', '[{"name":"invoice","sha256":"x","bytes":1}]'::jsonb, 'idem-1')->>'run_id') as run1 \gset
select test_assert((sf_run_insert(:'v1', 'ui', '[]'::jsonb, 'idem-1')->>'existing')::boolean, 'idempotency key returns the existing run');
update sf_runs set status = 'succeeded', finished_at = now(), cost_usd = 0.01 where id = :'run1';

-- concurrency: policy max 2, two in-flight runs block a third
update sf_policies set max_concurrency = 1 where workspace_id = :'ws';  -- author can't (admin only)
select test_assert((select max_concurrency from sf_policies where workspace_id = :'ws') = 2, 'author cannot change policy (RLS: 0 rows updated)');
select test_as('00000000-0000-0000-0000-000000000001');
update sf_policies set max_concurrency = 1 where workspace_id = :'ws';
select test_as('00000000-0000-0000-0000-000000000002');
select (sf_run_insert(:'v1', 'ui', '[]'::jsonb)->>'run_id') as run2 \gset
select test_expect_error($$select sf_run_insert('$$ || :'v1' || $$', 'ui', '[]'::jsonb)$$, 'concurrency limit');
update sf_runs set status = 'failed', error = 'test' where id = :'run2';

-- budget: 0.005 USD budget already exceeded by the 0.01 estimate
select test_as('00000000-0000-0000-0000-000000000001');
update sf_policies set monthly_budget_usd = 0.005 where workspace_id = :'ws';
select test_as('00000000-0000-0000-0000-000000000002');
select test_expect_error($$select sf_run_insert('$$ || :'v1' || $$', 'ui', '[]'::jsonb)$$, 'monthly budget');
select test_as('00000000-0000-0000-0000-000000000001');
update sf_policies set monthly_budget_usd = null where workspace_id = :'ws';

-- ───────── 4. evaluation run: gate becomes met only with a current, passing run ─────────
select test_as('00000000-0000-0000-0000-000000000002');
select sf_eval_set_hash(:'v1') as h1 \gset
insert into sf_eval_runs (version_id, eval_set_hash, status, pass_rate, finished_at, created_by)
  values (:'v1', :'h1', 'finished', 0.5, now(), auth.uid());
select test_assert((select eval_gate_met from sf_version_release_state where version_id = :'v1') = false, 'pass rate 0.5 < 0.8 fails the gate');
insert into sf_eval_runs (version_id, eval_set_hash, status, pass_rate, finished_at, created_by)
  values (:'v1', :'h1', 'finished', 1.0, now() + interval '1 second', auth.uid());
select test_assert((select eval_gate_met from sf_version_release_state where version_id = :'v1') = true, 'pass rate 1.0 meets the gate');
-- adding a case makes the evidence outdated
insert into sf_eval_cases (version_id, name, inputs, checks) values (:'v1', 'missing input', '{}', '["exit:2"]');
select test_assert((select eval_current from sf_version_release_state where version_id = :'v1') = false, 'new case -> eval outdated');
select test_assert((select eval_gate_met from sf_version_release_state where version_id = :'v1') = false, 'outdated eval does not meet the gate');
select test_expect_error($$select sf_publish_version('$$ || :'v1' || $$')$$, 'no valid approval');
select sf_eval_set_hash(:'v1') as h2 \gset
insert into sf_eval_runs (version_id, eval_set_hash, status, pass_rate, finished_at, created_by)
  values (:'v1', :'h2', 'finished', 1.0, now() + interval '2 seconds', auth.uid());
select test_assert((select eval_gate_met from sf_version_release_state where version_id = :'v1') = true, 'fresh run meets the gate again');

-- ───────── 5. review: only in_review versions, only reviewers/admins, not the author ─────────
select test_expect_error($$select sf_review_version('$$ || :'v1' || $$', 'approve')$$, 'reviewers or admins only');
update sf_skill_versions set status = 'in_review' where id = :'v1';
select test_expect_error($$update sf_skill_versions set status = 'published' where id = '$$ || :'v1' || $$'$$, 'only allowed through');
select test_as('00000000-0000-0000-0000-000000000003');
update sf_skill_versions set status = 'approved' where id = :'v1';  -- reviewer has no update right: RLS filters the row, 0 updated
select test_assert((select status from sf_skill_versions where id = :'v1') = 'in_review', 'reviewer cannot flip status directly');
select sf_review_version(:'v1', 'approve', 'looks right');
select test_assert((select status from sf_skill_versions where id = :'v1') = 'approved', 'approved status');
select test_assert((select approval_valid from sf_version_release_state where version_id = :'v1') = true, 'approval valid');
select test_assert((select publishable from sf_version_release_state where version_id = :'v1') = true, 'publishable');

-- ───────── 6. stale approval: an approved version is immutable; a draft edit after reject goes stale ─────────
select test_as('00000000-0000-0000-0000-000000000002');
select test_expect_error($$update sf_skill_versions set manifest = '{"inputs":[]}', manifest_hash = repeat('c', 64) where id = '$$ || :'v1' || $$'$$, 'immutable');
select test_expect_error($$insert into sf_files (version_id, path, content, sha256) values ('$$ || :'v1' || $$', 'scripts/new.py', 'x', repeat('b', 64))$$, 'immutable');

-- a second version: approve, then reject route: in_review -> draft keeps the approval row but it no longer matches once edited
insert into sf_skill_versions (skill_id, version, manifest, manifest_hash, created_by)
  values (:'skill', 2, '{"inputs":[],"outputs":[],"release_criteria":{"min_eval_pass_rate":0,"require_approval":true}}', repeat('d', 64), auth.uid())
  returning id as v2 \gset
update sf_skill_versions set status = 'in_review' where id = :'v2';
select test_as('00000000-0000-0000-0000-000000000003');
select sf_review_version(:'v2', 'approve');
select test_assert((select approval_valid from sf_version_release_state where version_id = :'v2') = true, 'v2 approved');
-- author reopens the approved version for editing: allowed; the approval stays valid until the manifest changes
select test_as('00000000-0000-0000-0000-000000000002');
update sf_skill_versions set status = 'draft' where id = :'v2';
select test_assert((select approval_valid from sf_version_release_state where version_id = :'v2') = true, 'reopened, unchanged: approval still valid');
update sf_skill_versions set manifest = '{"inputs":[],"outputs":[],"limits":{"timeout_s":20},"release_criteria":{"min_eval_pass_rate":0,"require_approval":true}}', manifest_hash = repeat('9', 64) where id = :'v2';
select test_assert((select approval_stale from sf_version_release_state where version_id = :'v2') = true, 'edited after approval: approval is STALE');
select test_assert((select publishable from sf_version_release_state where version_id = :'v2') = false, 'stale approval blocks publish');
select test_expect_error($$select sf_publish_version('$$ || :'v2' || $$')$$, 'approval is stale');
select test_expect_error($$update sf_skill_versions set status = 'published' where id = '$$ || :'v2' || $$'$$, 'only allowed through');
-- simulate the stale case directly: an in_review draft edited after an approval row exists
insert into sf_skill_versions (skill_id, version, manifest, manifest_hash, created_by)
  values (:'skill', 3, '{"inputs":[],"outputs":[],"release_criteria":{"min_eval_pass_rate":0,"require_approval":true}}', repeat('e', 64), auth.uid())
  returning id as v3 \gset
update sf_skill_versions set status = 'in_review' where id = :'v3';
select test_as('00000000-0000-0000-0000-000000000003');
select sf_review_version(:'v3', 'reject', 'needs a timeout');
select test_assert((select status from sf_skill_versions where id = :'v3') = 'draft', 'reject returns to draft');
select test_as('00000000-0000-0000-0000-000000000002');
update sf_skill_versions set manifest = '{"inputs":[],"outputs":[],"limits":{"timeout_s":30},"release_criteria":{"min_eval_pass_rate":0,"require_approval":true}}', manifest_hash = repeat('f', 64) where id = :'v3';
select test_assert((select approval_valid from sf_version_release_state where version_id = :'v3') = false, 'rejected+edited: no valid approval');
-- approve-then-edit staleness through the RPC path: approve v3 after re-review, then prove the hash comparison
update sf_skill_versions set status = 'in_review' where id = :'v3';
select test_as('00000000-0000-0000-0000-000000000003');
select sf_review_version(:'v3', 'approve');
select test_assert((select latest_approval_hash from sf_version_release_state where version_id = :'v3') = repeat('f', 64), 'approval pinned to the reviewed hash');
-- approvals are append-only
delete from sf_approvals where version_id = :'v3';  -- no delete policy: RLS filters every row
select test_assert((select count(*) from sf_approvals where version_id = :'v3') = 2, 'approvals are append-only (reject + approve kept)');
select set_config('role', 'postgres', false);  -- even the owner cannot delete: the trigger rejects it
select test_expect_error($$delete from sf_approvals where version_id = '$$ || :'v3' || $$'$$, 'append-only');
select test_as('00000000-0000-0000-0000-000000000003');

-- ───────── 7. publish: role check, gate, supersede, skill pointer, audit ─────────
select test_as('00000000-0000-0000-0000-000000000004');
select test_expect_error($$select sf_publish_version('$$ || :'v1' || $$')$$, 'authors or admins only');
select test_as('00000000-0000-0000-0000-000000000002');
select sf_publish_version(:'v1');
select test_assert((select status from sf_skill_versions where id = :'v1') = 'published', 'v1 published');
select test_assert((select latest_version_id from sf_skills where id = :'skill') = :'v1', 'skill points at v1');
select sf_publish_version(:'v3');
select test_assert((select status from sf_skill_versions where id = :'v1') = 'superseded', 'v1 superseded by v3');
select test_assert((select status from sf_skill_versions where id = :'v3') = 'published', 'v3 published');
select test_expect_error($$select sf_publish_version('$$ || :'v1' || $$')$$, 'cannot be published');
select test_assert((select count(*) from sf_audit_events where action = 'version.publish') = 2, 'publish audited');
-- published version immutable
select test_expect_error($$update sf_skill_versions set manifest = '{}' where id = '$$ || :'v3' || $$'$$, 'immutable');
-- consumer can now run the published version
select test_as('00000000-0000-0000-0000-000000000004');
select (sf_run_insert(:'v3', 'ui', '[]'::jsonb)->>'run_id') as run3 \gset
update sf_runs set status = 'succeeded' where id = :'run3';
select test_assert((select count(*) from sf_runs where id = :'run3' and status = 'succeeded') = 1, 'consumer updated own run');
select test_expect_error($$select sf_run_insert('$$ || :'v1' || $$', 'ui', '[]'::jsonb)$$, 'consumers can only run published');

-- ───────── 8. API keys: anon + hash only ─────────
select test_as('00000000-0000-0000-0000-000000000001');
insert into sf_api_keys (workspace_id, name, key_hash, prefix, created_by) values (:'ws', 'ci', repeat('1', 64), 'sf_live_abcd', auth.uid()) returning id as key1 \gset
select test_as_anon();
select test_assert((select count(*) from sf_resolve_api_key(repeat('1', 64))) = 1, 'valid key resolves');
select test_assert((select count(*) from sf_resolve_api_key(repeat('2', 64))) = 0, 'unknown key does not resolve');
select test_assert(jsonb_array_length(sf_api_skills(repeat('1', 64))) = 1, 'api lists the one published skill');
select test_assert((sf_api_skill(repeat('1', 64), 'invoice-check')->>'version')::int = 3, 'api returns the published version');
select test_assert(sf_api_skill(repeat('1', 64), 'nope') is null, 'unknown slug -> null');
select test_expect_error($$select sf_api_skills(repeat('2', 64))$$, 'invalid api key');
select (sf_record_run(repeat('1', 64), 'invoice-check', '[]'::jsonb, 'api-idem-1')->>'run_id') as apirun \gset
select test_assert((sf_record_run(repeat('1', 64), 'invoice-check', '[]'::jsonb, 'api-idem-1')->>'existing')::boolean, 'api idempotency');
select sf_api_run_update(repeat('1', 64), :'apirun', '{"status":"succeeded","provider":"none","duration_ms":12}');
select test_assert((sf_api_run_get(repeat('1', 64), :'apirun')->>'status') = 'succeeded', 'api run readback');
select test_expect_error($$select count(*) from sf_skills$$, 'permission denied');  -- anon has no table grants at all
-- revoked key
select test_as('00000000-0000-0000-0000-000000000001');
update sf_api_keys set revoked_at = now() where id = :'key1';
select test_as_anon();
select test_expect_error($$select sf_api_skills(repeat('1', 64))$$, 'invalid api key');

-- ───────── 9. retire ─────────
select test_as('00000000-0000-0000-0000-000000000002');
select sf_retire_version(:'v3');
select test_assert((select status from sf_skills where id = :'skill') = 'retired', 'skill retired when its only published version is retired');

-- ───────── 10. cross-tenant isolation ─────────
select test_as('00000000-0000-0000-0000-000000000005');
select sf_create_workspace('Other', 'other') as ws2 \gset
select test_assert((select count(*) from sf_skills) = 0, 'other workspace sees no acme skills');
select test_assert((select count(*) from sf_runs) = 0, 'other workspace sees no acme runs');
select test_assert((select count(*) from sf_audit_events) = 1, 'other workspace sees only its own audit');
select test_expect_error($$select sf_run_insert('$$ || :'v1' || $$', 'ui', '[]'::jsonb)$$, 'not a member');

-- ───────── 11. composed agents: draft editable, publish by reviewer, published spec frozen ─────────
select test_as('00000000-0000-0000-0000-000000000005');
select id as ws_other from sf_workspaces where slug = 'other' \gset
select test_as('00000000-0000-0000-0000-000000000002');
select id as ws_acme from sf_workspaces where slug <> 'other' limit 1 \gset
insert into sf_agents (workspace_id, slug, name, owner_id) values (:'ws_acme', 'pursuit', 'Pursuit', '00000000-0000-0000-0000-000000000002') returning id as ag \gset
insert into sf_agent_versions (agent_id, version, spec, spec_hash, created_by)
  values (:'ag', 1, '{"name":"pursuit","steps":[]}', repeat('a', 64), '00000000-0000-0000-0000-000000000002') returning id as av \gset
update sf_agent_versions set spec = '{"name":"pursuit","steps":[{"id":"x"}]}', spec_hash = repeat('b', 64) where id = :'av';
select test_assert((select spec_hash from sf_agent_versions where id = :'av') = repeat('b', 64), 'author edits a draft agent');
select test_expect_error($$update sf_agent_versions set status = 'published' where id = '$$ || :'av' || $$'$$, 'only through sf_publish_agent_version');
select test_expect_error($$select sf_publish_agent_version('$$ || :'av' || $$')$$, 'reviewers or admins only');
select test_as('00000000-0000-0000-0000-000000000003');
select sf_publish_agent_version(:'av');
select test_assert((select status from sf_agents where id = :'ag') = 'published', 'agent published');
select test_as('00000000-0000-0000-0000-000000000002');
select test_expect_error($$update sf_agent_versions set spec = '{"steps":[]}', spec_hash = repeat('c', 64) where id = '$$ || :'av' || $$'$$, 'immutable');
select test_as('00000000-0000-0000-0000-000000000004');
select test_expect_error($$insert into sf_agents (workspace_id, slug, name, owner_id) values ('$$ || :'ws_acme' || $$', 'c', 'C', '00000000-0000-0000-0000-000000000004')$$, 'row-level security');
insert into sf_agent_runs (workspace_id, agent_version_id, invoked_by) values (:'ws_acme', :'av', '00000000-0000-0000-0000-000000000004') returning id as ar \gset
select test_assert((select count(*) from sf_agent_runs where id = :'ar') = 1, 'consumer starts a run of a published agent');
select test_as('00000000-0000-0000-0000-000000000005');
select test_assert((select count(*) from sf_agents) = 0 and (select count(*) from sf_agent_runs) = 0, 'other workspace sees no acme agents or runs');

-- ───────── 12. roles and talent pools: same draft/publish/frozen rules as agents ─────────
select test_as('00000000-0000-0000-0000-000000000002');
insert into sf_talent (workspace_id, kind, slug, name, owner_id) values (:'ws_acme', 'role', 'architect', 'Architect', '00000000-0000-0000-0000-000000000002') returning id as tr \gset
insert into sf_talent (workspace_id, kind, slug, name, owner_id) values (:'ws_acme', 'pool', 'architect', 'Architect pod', '00000000-0000-0000-0000-000000000002') returning id as tp \gset
select test_expect_error($$insert into sf_talent (workspace_id, kind, slug, name, owner_id) values ('$$ || :'ws_acme' || $$', 'role', 'architect', 'Dup', '00000000-0000-0000-0000-000000000002')$$, 'duplicate');
insert into sf_talent_versions (talent_id, version, spec, spec_hash, created_by)
  values (:'tr', 1, '{"name":"architect","skills":["a/b"]}', repeat('a', 64), '00000000-0000-0000-0000-000000000002') returning id as trv \gset
update sf_talent_versions set spec = '{"name":"architect","skills":["a/b","c/d"]}', spec_hash = repeat('b', 64) where id = :'trv';
select test_expect_error($$update sf_talent_versions set status = 'published' where id = '$$ || :'trv' || $$'$$, 'only through sf_publish_talent_version');
select test_expect_error($$select sf_publish_talent_version('$$ || :'trv' || $$')$$, 'reviewers or admins only');
select test_as('00000000-0000-0000-0000-000000000003');
select sf_publish_talent_version(:'trv');
select test_assert((select status from sf_talent where id = :'tr') = 'published', 'role published');
select test_assert((select count(*) from sf_audit_events where action = 'role.publish' and entity_id = :'trv') = 1, 'role publish audited');
select test_as('00000000-0000-0000-0000-000000000002');
select test_expect_error($$update sf_talent_versions set spec = '{}', spec_hash = repeat('c', 64) where id = '$$ || :'trv' || $$'$$, 'immutable');
insert into sf_talent_versions (talent_id, version, spec, spec_hash, created_by)
  values (:'tr', 2, '{"name":"architect","skills":["c/d"]}', repeat('d', 64), '00000000-0000-0000-0000-000000000002') returning id as trv2 \gset
select test_as('00000000-0000-0000-0000-000000000001');
select sf_publish_talent_version(:'trv2');
select test_assert((select status from sf_talent_versions where id = :'trv') = 'superseded', 'previous role version superseded');
select test_as('00000000-0000-0000-0000-000000000004');
select test_assert((select count(*) from sf_talent where workspace_id = :'ws_acme') = 2, 'consumer reads roles and pools');
select test_expect_error($$insert into sf_talent (workspace_id, kind, slug, name, owner_id) values ('$$ || :'ws_acme' || $$', 'role', 'c', 'C', '00000000-0000-0000-0000-000000000004')$$, 'row-level security');
update sf_talent set name = 'hijack' where id = :'tr';
select test_assert((select name from sf_talent where id = :'tr') = 'Architect', 'consumer cannot rename a role');
select test_as('00000000-0000-0000-0000-000000000005');
select test_assert((select count(*) from sf_talent) = 0 and (select count(*) from sf_talent_versions) = 0, 'other workspace sees no acme roles or pools');

-- ───────── MCP read paths (0005): catalog and published talent, by API key only ─────────
select test_as('00000000-0000-0000-0000-000000000001');
insert into sf_api_keys (workspace_id, name, key_hash, prefix, created_by) values (:'ws_acme', 'mcp', repeat('7', 64), 'sf_live_mcp1', auth.uid());
select test_as_anon();
select test_assert((sf_api_talent(repeat('7', 64), 'role', 'architect')->'spec'->'skills') = '["c/d"]'::jsonb, 'mcp: published role spec (latest published version)');
select test_assert(sf_api_talent(repeat('7', 64), 'pool', 'architect') is null, 'mcp: team without a published version -> null');
select test_assert(sf_api_talent(repeat('7', 64), 'role', 'nope') is null, 'mcp: unknown role -> null');
select test_expect_error($$select sf_api_talent(repeat('7', 64), 'skill', 'architect')$$, 'kind must be role or pool');
select test_expect_error($$select sf_api_talent(repeat('8', 64), 'role', 'architect')$$, 'invalid api key');
select test_assert(jsonb_typeof(sf_api_catalog(repeat('7', 64))) = 'array', 'mcp: catalog is an array');
select test_expect_error($$select sf_api_catalog(repeat('8', 64))$$, 'invalid api key');

-- ───────── Context Lake (0007): installations admin-only and verified by the acting user; catalog per workspace ─────────
select test_as('00000000-0000-0000-0000-000000000001');
insert into sf_github_installations (workspace_id, installation_id, account_login, account_type, verified_by)
  values (:'ws_acme', 9001, 'acme-org', 'Organization', auth.uid());
select test_expect_error($$insert into sf_github_installations (workspace_id, installation_id, account_login, verified_by)
  values ('$$ || :'ws_acme' || $$', 9002, 'x', '00000000-0000-0000-0000-000000000002')$$, 'row-level security');   -- must be verified by yourself
select test_as('00000000-0000-0000-0000-000000000002');
select test_expect_error($$insert into sf_github_installations (workspace_id, installation_id, account_login, verified_by)
  values ('$$ || :'ws_acme' || $$', 9003, 'x', auth.uid())$$, 'row-level security');                                 -- authors cannot connect GitHub
insert into sf_catalog_entities (workspace_id, kind, key, external_id, installation_id, title, url, properties)
  values (:'ws_acme', 'repository', 'acme-org/billing', '1', 9001, 'billing', 'https://github.com/acme-org/billing', '{"stack":["supabase"]}');
insert into sf_catalog_syncs (workspace_id, installation_id, status, started_by) values (:'ws_acme', 9001, 'succeeded', auth.uid());
select test_expect_error($$insert into sf_catalog_entities (workspace_id, kind, key, external_id, title, url)
  values ('$$ || :'ws_acme' || $$', 'repository', 'acme-org/billing', '1', 'dup', 'https://github.com/x')$$, 'duplicate');
select test_expect_error($$insert into sf_catalog_entities (workspace_id, kind, key, external_id, title, url)
  values ('$$ || :'ws_acme' || $$', 'repository', 'acme-org/x', '2', 'x', 'javascript:alert(1)')$$, 'check');
select test_as('00000000-0000-0000-0000-000000000004');
select test_assert((select count(*) from sf_catalog_entities where workspace_id = :'ws_acme') = 1, 'consumer reads the catalog');
update sf_catalog_entities set title = 'hijack' where workspace_id = :'ws_acme';
select test_assert((select title from sf_catalog_entities where key = 'acme-org/billing') = 'billing', 'consumer cannot edit the catalog');
select test_as('00000000-0000-0000-0000-000000000005');
select test_assert((select count(*) from sf_catalog_entities) = 0 and (select count(*) from sf_github_installations) = 0
                   and (select count(*) from sf_catalog_syncs) = 0, 'other workspace sees no catalog, installation or sync');
select test_as('00000000-0000-0000-0000-000000000001');
select test_expect_error($$insert into sf_github_installations (workspace_id, installation_id, account_login, verified_by)
  values ('$$ || :'ws_acme' || $$', 9001, 'again', auth.uid())$$, 'duplicate');                                     -- one workspace per installation

-- ───────── Scorecards (0008): append-only evidence, workspace-scoped, latest view respects RLS ─────────
select test_as('00000000-0000-0000-0000-000000000002');
select id as ent from sf_catalog_entities where key = 'acme-org/billing' \gset
insert into sf_scorecard_results (workspace_id, entity_id, check_id, skill, verdict, summary, findings, run_by)
  values (:'ws_acme', :'ent', 'rls', 'build/supabase-schema-rls', 'fail', '2 error(s)', 2, auth.uid());
insert into sf_scorecard_results (workspace_id, entity_id, check_id, skill, verdict, summary, findings, run_by)
  values (:'ws_acme', :'ent', 'rls', 'build/supabase-schema-rls', 'pass', '0 error(s)', 0, auth.uid());
select test_assert((select verdict from sf_scorecard_latest where entity_id = :'ent' and check_id = 'rls') = 'pass', 'latest view: newest result wins');
select test_assert((select count(*) from sf_scorecard_results where entity_id = :'ent') = 2, 'history kept');
select test_expect_error($$update sf_scorecard_results set verdict = 'pass'$$, 'permission denied');   -- evidence cannot be edited
select test_expect_error($$delete from sf_scorecard_results$$, 'permission denied');                    -- … or deleted
select test_expect_error($$insert into sf_scorecard_results (workspace_id, entity_id, check_id, skill, verdict, run_by)
  values ('$$ || :'ws_acme' || $$', '$$ || :'ent' || $$', 'rls', 'x', 'pass', auth.uid())$$, 'check');
select test_as('00000000-0000-0000-0000-000000000004');
select test_expect_error($$insert into sf_scorecard_results (workspace_id, entity_id, check_id, skill, verdict, run_by)
  values ('$$ || :'ws_acme' || $$', '$$ || :'ent' || $$', 'rls', 'build/supabase-schema-rls', 'pass', auth.uid())$$, 'row-level security');
select test_as('00000000-0000-0000-0000-000000000005');
select test_assert((select count(*) from sf_scorecard_latest) = 0, 'other workspace: latest view shows nothing');
select test_expect_error($$insert into sf_scorecard_results (workspace_id, entity_id, check_id, skill, verdict, run_by)
  values ('$$ || :'ws_acme' || $$', '$$ || :'ent' || $$', 'rls', 'build/supabase-schema-rls', 'pass', auth.uid())$$, 'row-level security');

-- ───────── Insights (0009): browser runs are the caller's own; ROI baselines admin-owned with owner + source ─────────
select test_as('00000000-0000-0000-0000-000000000004');
insert into sf_browser_runs (workspace_id, user_id, skill, status, example) values (:'ws_acme', auth.uid(), 'build/supabase-schema-rls', 'succeeded', true);
select test_expect_error($$insert into sf_browser_runs (workspace_id, user_id, skill, status) values ('$$ || :'ws_acme' || $$', '00000000-0000-0000-0000-000000000001', 'a/b', 'succeeded')$$, 'row-level security');
select test_expect_error($$update sf_browser_runs set status = 'failed'$$, 'permission denied');
select test_expect_error($$insert into sf_roi_baselines (workspace_id, skill, manual_minutes, owner, source, set_by) values ('$$ || :'ws_acme' || $$', 'a/b', 30, 'me', 'guess', auth.uid())$$, 'row-level security');
select test_as('00000000-0000-0000-0000-000000000001');
insert into sf_roi_baselines (workspace_id, skill, manual_minutes, hourly_rate_usd, owner, source, set_by)
  values (:'ws_acme', 'build/supabase-schema-rls', 45, 120, 'Platform lead', 'timed 5 manual reviews, Oct 2026', auth.uid());
select test_expect_error($$insert into sf_roi_baselines (workspace_id, skill, manual_minutes, owner, source, set_by) values ('$$ || :'ws_acme' || $$', 'a/c', 0, 'x', 'none', auth.uid())$$, 'check');
select test_expect_error($$insert into sf_roi_baselines (workspace_id, skill, manual_minutes, owner, source, set_by) values ('$$ || :'ws_acme' || $$', 'a/d', 10, 'x', '', auth.uid())$$, 'check');
select test_as('00000000-0000-0000-0000-000000000005');
select test_assert((select count(*) from sf_browser_runs) = 0 and (select count(*) from sf_roi_baselines) = 0, 'other workspace sees no runs or baselines');

-- every key-authenticated function writes last_used_at through sf_resolve_api_key, so none may be STABLE/IMMUTABLE:
-- PostgREST runs those in a READ ONLY transaction (found live: "cannot execute UPDATE in a read-only transaction")
select test_assert((select count(*) from pg_proc p join pg_namespace n on n.oid = p.pronamespace
                    where n.nspname = 'public' and p.proname like 'sf\_api\_%' and p.provolatile <> 'v') = 0,
                   'all sf_api_* functions are VOLATILE');

-- the shared project's own tables were never touched
select test_assert((select count(*) from pg_policies where tablename = 'profiles') = 0, 'profiles untouched');
select 'ALL SQL TESTS PASSED' as result;

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

-- ───────── 8b. roles decide who can run which skill (0019) ─────────
-- policy off (default): consumer and key run as before (proved by sections 7 and 8); now turn it on
select test_as('00000000-0000-0000-0000-000000000001');
insert into sf_api_keys (workspace_id, name, key_hash, prefix, created_by) values (:'ws', 'finance-app', repeat('3', 64), 'sf_live_fin0', auth.uid()) returning id as key3 \gset
update sf_policies set skills_by_role = true, max_concurrency = 50 where workspace_id = :'ws';
-- consumer with no role: refused, answered (not raised) and audited
select test_as('00000000-0000-0000-0000-000000000004');
select test_assert((sf_run_insert(:'v3', 'ui', '[]'::jsonb)->>'error') = 'not_in_role', 'consumer without a role is refused');
select test_assert((select count(*) from sf_audit_events where action = 'run.denied' and actor_id = '00000000-0000-0000-0000-000000000004') = 1, 'refusal audited');
-- the direct insert path is refused by the backstop
select test_expect_error($$insert into sf_runs (workspace_id, version_id, invoked_by, source) values ('$$ || :'ws' || $$', '$$ || :'v3' || $$', auth.uid(), 'ui')$$, 'not_in_role');
select test_expect_error($$insert into sf_runs (workspace_id, version_id, invoked_by, source) values ('$$ || :'ws' || $$', '$$ || :'v3' || $$', auth.uid(), 'eval')$$, 'not_in_role');
-- key with no role: refused and audited
select test_as_anon();
select test_assert((sf_record_run(repeat('3', 64), 'invoice-check', '[]'::jsonb)->>'error') = 'not_in_role', 'key without a role is refused');
select test_assert((sf_api_catalog(repeat('3', 64))->0->>'allowed')::boolean = false, 'MCP catalog marks the skill not allowed for this key');
select test_assert((sf_api_skills(repeat('3', 64))->0->>'allowed')::boolean = false, 'API list marks it too');
-- authors are not restricted (they test before release)
select test_as('00000000-0000-0000-0000-000000000002');
select test_assert((sf_run_insert(:'v3', 'ui', '[]'::jsonb)->>'run_id') is not null, 'author unrestricted');
-- a published role listing the skill (by workspace slug), assigned to the consumer and the key
insert into sf_talent (workspace_id, kind, slug, name, owner_id) values (:'ws', 'role', 'finance-analyst', 'Finance analyst', auth.uid()) returning id as role1 \gset
insert into sf_talent_versions (talent_id, version, status, spec, spec_hash, created_by)
  values (:'role1', 1, 'draft', '{"name":"finance-analyst","title":"Finance analyst","description":"","skills":["invoice-check"],"playbooks":["month-end"]}', repeat('c', 64), auth.uid())
  returning id as role1v \gset
-- a draft role grants nothing
select test_as('00000000-0000-0000-0000-000000000001');
insert into sf_role_assignments (workspace_id, talent_id, user_id, granted_by) values (:'ws', :'role1', '00000000-0000-0000-0000-000000000004', auth.uid());
insert into sf_role_assignments (workspace_id, talent_id, api_key_id, granted_by) values (:'ws', :'role1', :'key3', auth.uid());
select test_as('00000000-0000-0000-0000-000000000004');
select test_assert((sf_run_insert(:'v3', 'ui', '[]'::jsonb)->>'error') = 'not_in_role', 'a draft role grants nothing');
select test_assert((sf_playbook_access(:'ws', 'month-end')->>'allowed')::boolean = false, 'draft role: no playbook either');
select test_as('00000000-0000-0000-0000-000000000003');
select sf_publish_talent_version(:'role1v');
select test_as('00000000-0000-0000-0000-000000000004');
select (sf_run_insert(:'v3', 'ui', '[]'::jsonb)->>'run_id') as rolerun \gset
select test_assert((select granted_by_role from sf_runs where id = :'rolerun') = :'role1', 'run records the role that allowed it');
select test_assert((sf_playbook_access(:'ws', 'month-end')->>'allowed')::boolean, 'role lists the playbook');
select test_assert((sf_playbook_access(:'ws', 'other-playbook')->>'allowed')::boolean = false, 'playbook not in the role');
select test_as_anon();
select (sf_record_run(repeat('3', 64), 'invoice-check', '[]'::jsonb)->>'run_id') as keyrun \gset
select test_as('00000000-0000-0000-0000-000000000001');
select test_assert((select count(*) from sf_runs where id = :'keyrun' and granted_by_role = :'role1') = 1, 'key runs through its role');
select test_as_anon();
select test_assert((sf_api_catalog(repeat('3', 64))->0->>'allowed')::boolean, 'MCP catalog: allowed through the role');
select test_as('00000000-0000-0000-0000-000000000001');
-- only admins assign; assignments stay in the workspace; the rule function is not callable
select test_as('00000000-0000-0000-0000-000000000004');
select test_expect_error($$insert into sf_role_assignments (workspace_id, talent_id, user_id, granted_by) values ('$$ || :'ws' || $$', '$$ || :'role1' || $$', '00000000-0000-0000-0000-000000000003', auth.uid())$$, 'row-level security');
select test_expect_error($$select sf_run_access('$$ || :'ws' || $$', '$$ || :'v3' || $$', '00000000-0000-0000-0000-000000000004', null)$$, 'permission denied');
select test_as('00000000-0000-0000-0000-000000000001');
select test_expect_error($$insert into sf_role_assignments (workspace_id, talent_id, user_id, granted_by) values ('$$ || :'ws' || $$', '$$ || :'role1' || $$', '00000000-0000-0000-0000-000000000005', auth.uid())$$, 'member of this workspace');
-- policy off again: everything as before
update sf_policies set skills_by_role = false where workspace_id = :'ws';
delete from sf_role_assignments where workspace_id = :'ws';
-- access requests (0020): a member asks, any admin decides (never their own), approval assigns the role
select test_as('00000000-0000-0000-0000-000000000004');
select (sf_access_request(:'ws', :'role1', 'invoice-check', 'month-end close')->>'id') as areq \gset
select test_assert((sf_access_request(:'ws', :'role1', 'invoice-check', 'again')->>'existing')::boolean, 'one pending request per role and person');
select test_expect_error($$select sf_access_decide('$$ || :'areq' || $$', true, '')$$, 'only admins');
select test_assert((select count(*) from sf_access_requests) = 1, 'requester sees their own request');
select test_expect_error($$insert into sf_access_requests (workspace_id, talent_id, requested_by) values ('$$ || :'ws' || $$', '$$ || :'role1' || $$', auth.uid())$$, 'permission denied');
select test_as('00000000-0000-0000-0000-000000000003');
select test_assert((select count(*) from sf_access_requests) = 0, 'a reviewer does not see others'' requests');
select test_expect_error($$select sf_access_decide('$$ || :'areq' || $$', true, '')$$, 'only admins');
select test_as('00000000-0000-0000-0000-000000000001');
select test_assert(sf_access_decide(:'areq', true, 'ok') = 'approved', 'admin approves');
select test_assert((select count(*) from sf_role_assignments where talent_id = :'role1' and user_id = '00000000-0000-0000-0000-000000000004') = 1, 'approval assigns the role');
select test_expect_error($$select sf_access_decide('$$ || :'areq' || $$', false, '')$$, 'already approved');
select (sf_access_request(:'ws', :'role1', null, 'me too')->>'id') as ownreq \gset
select test_expect_error($$select sf_access_decide('$$ || :'ownreq' || $$', true, '')$$, 'your own request');
select test_assert((select count(*) from sf_audit_events where action in ('access.request', 'access.approve')) = 3, 'requests and decisions audited');
delete from sf_role_assignments where workspace_id = :'ws';
select test_as('00000000-0000-0000-0000-000000000004');
select test_assert((sf_run_insert(:'v3', 'ui', '[]'::jsonb)->>'run_id') is not null, 'policy off: consumer runs without a role');
select test_as('00000000-0000-0000-0000-000000000001');
delete from sf_talent where id = :'role1';
select test_assert((select granted_by_role from sf_runs where id = :'rolerun') is null, 'deleting a role keeps the run, clears the link');
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

-- ───────── 0010: workspace_id on child tables is derived from the parent, never supplied ─────────
select test_assert((select count(*) from sf_skill_versions where workspace_id is null) = 0, 'every version carries its workspace');
select test_assert((select count(*) from sf_skill_versions v join sf_skills s on s.id = v.skill_id where v.workspace_id <> s.workspace_id) = 0, 'version workspace matches its skill');
select test_assert((select count(*) from sf_files f join sf_skill_versions v on v.id = f.version_id where f.workspace_id <> v.workspace_id) = 0, 'file workspace matches its version');
select test_assert((select count(*) from sf_approvals a join sf_skill_versions v on v.id = a.version_id where a.workspace_id <> v.workspace_id) = 0, 'approval workspace matches its version');
select test_as('00000000-0000-0000-0000-000000000002');
insert into sf_talent_versions (talent_id, version, spec, spec_hash, created_by, workspace_id)
  values (:'tr', 9, '{"name":"architect","skills":["c/d"]}', repeat('e', 64), auth.uid(), (select id from sf_workspaces where slug = 'other'))
  returning workspace_id as derived \gset
select test_assert(:'derived' = :'ws_acme', 'a spoofed workspace_id is overwritten with the parent''s');
select test_as_anon();
select test_assert(sf_health_ping() = 1, 'health ping answers over the anon role');

-- ───────── Automations (0011): admin-managed rules; runs and deliveries are server-only; PR results stay off the scorecard ─────────
select test_as('00000000-0000-0000-0000-000000000001');
insert into sf_automations (workspace_id, name, trigger, created_by) values (:'ws_acme', 'PR gate', 'github.pull_request', auth.uid()) returning id as auto \gset
select test_as('00000000-0000-0000-0000-000000000002');
select test_expect_error($$insert into sf_automations (workspace_id, name, trigger, created_by) values ('$$ || :'ws_acme' || $$', 'x', 'github.push', auth.uid())$$, 'row-level security');
select test_expect_error($$insert into sf_automation_runs (workspace_id, automation_id, repo, event) values ('$$ || :'ws_acme' || $$', '$$ || :'auto' || $$', 'acme-org/billing', 'pull_request')$$, 'permission denied');
select test_expect_error($$insert into sf_github_deliveries (delivery_id, workspace_id, event, installation_id) values ('d1', '$$ || :'ws_acme' || $$', 'push', 9001)$$, 'permission denied');
insert into sf_scorecard_results (workspace_id, entity_id, check_id, skill, verdict, summary, run_by, context, pr_number)
  values (:'ws_acme', :'ent', 'rls', 'build/supabase-schema-rls', 'fail', 'PR introduces a table without RLS', auth.uid(), 'pull_request', 7);
select test_assert((select verdict from sf_scorecard_latest where entity_id = :'ent' and check_id = 'rls') = 'pass', 'a pull-request result does not replace the default-branch scorecard');
select test_as('00000000-0000-0000-0000-000000000005');
select test_assert((select count(*) from sf_automations) = 0 and (select count(*) from sf_automation_runs) = 0, 'other workspace sees no automations or runs');

-- ───────── Assistant (0012): each user logs their own questions; admins read the workspace's; append-only ─────────
select test_as('00000000-0000-0000-0000-000000000002');
insert into sf_assistant_log (workspace_id, user_id, question, status) values (:'ws_acme', auth.uid(), 'which repos fail rls?', 'answered') returning id as qlog \gset
select test_expect_error($$insert into sf_assistant_log (workspace_id, user_id, question, status) values ('$$ || :'ws_acme' || $$', '00000000-0000-0000-0000-000000000001', 'spoofed', 'answered')$$, 'row-level security');
select test_expect_error($$update sf_assistant_log set question = 'edited' where id = '$$ || :'qlog' || $$'$$, 'permission denied');
select test_as('00000000-0000-0000-0000-000000000001');
insert into sf_assistant_log (workspace_id, user_id, question, status) values (:'ws_acme', auth.uid(), 'admin question', 'answered');
select test_assert((select count(*) from sf_assistant_log) = 2, 'an admin reads the workspace''s questions');
select test_as('00000000-0000-0000-0000-000000000002');
select test_assert((select count(*) from sf_assistant_log) = 1, 'a member reads only their own questions');
select test_as('00000000-0000-0000-0000-000000000005');
select test_assert((select count(*) from sf_assistant_log) = 0, 'other workspace reads no questions');
select test_expect_error($$insert into sf_assistant_log (workspace_id, user_id, question, status) values ('$$ || :'ws_acme' || $$', auth.uid(), 'x', 'answered')$$, 'row-level security');

-- ───────── Initiatives (0013): authors/admins set goals; members read; only admins delete ─────────
select test_as('00000000-0000-0000-0000-000000000002');
insert into sf_initiatives (workspace_id, title, target_level, owner, due_on, created_by)
  values (:'ws_acme', 'Every repo at Silver', 'silver', 'Platform team', '2026-12-01', auth.uid()) returning id as ini \gset
select test_expect_error($$insert into sf_initiatives (workspace_id, title, target_level, owner, due_on, created_by) values ('$$ || :'ws_acme' || $$', 'x', 'platinum', 'o', '2026-12-01', auth.uid())$$, 'check');
select test_expect_error($$insert into sf_initiatives (workspace_id, title, target_level, owner, due_on, created_by) values ('$$ || :'ws_acme' || $$', 'x', 'gold', 'o', '2026-12-01', '00000000-0000-0000-0000-000000000001')$$, 'row-level security');
update sf_initiatives set status = 'closed' where id = :'ini';
select test_assert((select status from sf_initiatives where id = :'ini') = 'closed', 'an author closes an initiative');
delete from sf_initiatives where id = :'ini';
select test_assert((select count(*) from sf_initiatives where id = :'ini') = 1, 'an author cannot delete an initiative');
select test_as('00000000-0000-0000-0000-000000000004');
select test_assert((select count(*) from sf_initiatives) = 1, 'a consumer reads initiatives');
select test_expect_error($$insert into sf_initiatives (workspace_id, title, target_level, owner, due_on, created_by) values ('$$ || :'ws_acme' || $$', 'x', 'gold', 'o', '2026-12-01', auth.uid())$$, 'row-level security');
select test_as('00000000-0000-0000-0000-000000000005');
select test_assert((select count(*) from sf_initiatives) = 0, 'other workspace sees no initiatives');
select test_as('00000000-0000-0000-0000-000000000001');
delete from sf_initiatives where id = :'ini';
select test_assert((select count(*) from sf_initiatives where id = :'ini') = 0, 'an admin deletes an initiative');

-- ───────── Actions (0014): requests only via functions; policy decides approval; no self-approval; valid transitions ─────────
select test_as('00000000-0000-0000-0000-000000000004');   -- consumer
select (sf_action_request(:'ws_acme', 'acme-org/billing', 'security-review', '{"code":{"folder":"src"}}', false, 'pre-release'))->>'status' as st_script \gset
select test_assert(:'st_script' = 'approved', 'default policy: an action without model steps runs without approval');
select (sf_action_request(:'ws_acme', 'acme-org/billing', 'proposal-writer', '{}', true, ''))->>'id' as act \gset
select test_assert((select status from sf_action_runs where id = :'act') = 'pending_approval', 'default policy: an action with model steps waits for approval');
select test_expect_error($$select sf_action_request('$$ || :'ws_acme' || $$', 'acme-org/not-there', 's', '{}', false, '')$$, 'not in this workspace');
select test_expect_error($$insert into sf_action_runs (workspace_id, repo, skill, status, requested_by) values ('$$ || :'ws_acme' || $$', 'acme-org/billing', 's', 'approved', auth.uid())$$, 'permission denied');
select test_expect_error($$update sf_action_runs set status = 'approved' where id = '$$ || :'act' || $$'$$, 'permission denied');
select test_expect_error($$select sf_action_mark('$$ || :'act' || $$', 'running', null, null)$$, 'cannot move');
select test_expect_error($$select sf_action_decide('$$ || :'act' || $$', true, 'mine')$$, 'only reviewers');
select test_as('00000000-0000-0000-0000-000000000002');   -- author
select test_expect_error($$select sf_action_decide('$$ || :'act' || $$', true, '')$$, 'only reviewers');
select test_as('00000000-0000-0000-0000-000000000003');   -- reviewer
select test_assert(sf_action_decide(:'act', true, 'ok for staging') = 'approved', 'a reviewer approves someone else''s request');
select test_expect_error($$select sf_action_decide('$$ || :'act' || $$', false, '')$$, 'already approved');
select test_as('00000000-0000-0000-0000-000000000004');
select test_assert(sf_action_mark(:'act', 'running', null, null, repeat('a', 40)) = 'running', 'the requester starts the approved action');
select test_assert(sf_action_mark(:'act', 'succeeded', null, null) = 'succeeded', 'and finishes it');
select test_assert((select commit_sha from sf_action_runs where id = :'act') = repeat('a', 40), 'the commit is recorded');
select test_expect_error($$select sf_action_mark('$$ || :'act' || $$', 'running', null, null)$$, 'cannot move');
select test_as('00000000-0000-0000-0000-000000000003');
select (sf_action_request(:'ws_acme', 'acme-org/billing', 'x', '{}', true, ''))->>'id' as own \gset
select test_expect_error($$select sf_action_decide('$$ || :'own' || $$', true, '')$$, 'your own request');
select test_as('00000000-0000-0000-0000-000000000001');
update sf_policies set action_approval = 'none' where workspace_id = :'ws_acme';
select test_assert((sf_action_request(:'ws_acme', 'acme-org/billing', 'x', '{}', true, ''))->>'status' = 'approved', 'policy none: no approval even with model steps');
update sf_policies set action_approval = 'always' where workspace_id = :'ws_acme';
select test_assert((sf_action_request(:'ws_acme', 'acme-org/billing', 'x', '{}', false, ''))->>'status' = 'pending_approval', 'policy always: every action waits');
select test_as('00000000-0000-0000-0000-000000000005');
select test_assert((select count(*) from sf_action_runs) = 0, 'other workspace sees no actions');
select test_expect_error($$select sf_action_decide('$$ || :'own' || $$', true, '')$$, 'not found');

-- ───────── Delivery metrics (0015): authors/admins write snapshots for their workspace's entities; members read ─────────
select test_as('00000000-0000-0000-0000-000000000002');
insert into sf_delivery_snapshots (workspace_id, entity_id, metrics, computed_by) values (:'ws_acme', :'ent', '{"d30":{"merges":3}}', auth.uid());
select test_expect_error($$insert into sf_delivery_snapshots (workspace_id, entity_id, metrics, computed_by) values ('$$ || :'ws_acme' || $$', '$$ || :'ent' || $$', '{}', '00000000-0000-0000-0000-000000000001')$$, 'row-level security');
select test_as('00000000-0000-0000-0000-000000000004');
select test_assert((select (metrics->'d30'->>'merges')::int from sf_delivery_latest where entity_id = :'ent') = 3, 'a consumer reads the latest delivery snapshot');
select test_expect_error($$insert into sf_delivery_snapshots (workspace_id, entity_id, metrics, computed_by) values ('$$ || :'ws_acme' || $$', '$$ || :'ent' || $$', '{}', auth.uid())$$, 'row-level security');
select test_as('00000000-0000-0000-0000-000000000005');
select test_assert((select count(*) from sf_delivery_snapshots) = 0, 'other workspace sees no delivery metrics');

-- ───────── Invitations (0016): admins invite; acceptance on sign-in by email; never downgrades; expiry/revoke ─────────
select test_as('00000000-0000-0000-0000-000000000001');
insert into sf_invitations (workspace_id, email, role, invited_by) values (:'ws_acme', 'new.person@example.com', 'reviewer', auth.uid());
insert into sf_invitations (workspace_id, email, role, invited_by) values (:'ws_acme', 'author@example.com', 'consumer', auth.uid());
select test_expect_error($$insert into sf_invitations (workspace_id, email, role, invited_by) values ('$$ || :'ws_acme' || $$', 'Mixed@Case.com', 'author', auth.uid())$$, 'check');
select test_expect_error($$insert into sf_invitations (workspace_id, email, role, invited_by) values ('$$ || :'ws_acme' || $$', 'new.person@example.com', 'author', auth.uid())$$, 'duplicate');
select test_as('00000000-0000-0000-0000-000000000002');
select test_expect_error($$insert into sf_invitations (workspace_id, email, role, invited_by) values ('$$ || :'ws_acme' || $$', 'x@example.com', 'admin', auth.uid())$$, 'row-level security');
select test_assert((select count(*) from sf_invitations) = 0, 'a non-admin sees no invitations');
reset role;
insert into auth.users (id, email) values ('00000000-0000-0000-0000-000000000009', 'New.Person@example.com');
select test_as('00000000-0000-0000-0000-000000000009');
select test_assert(sf_accept_invitations() = 1, 'the invited email accepts on sign-in (case-insensitive)');
select test_assert(sf_role(:'ws_acme') = 'reviewer', 'with the invited role');
select test_assert(sf_accept_invitations() = 0, 'accepting twice does nothing');
reset role;
select email as author_email from auth.users where id = '00000000-0000-0000-0000-000000000002' \gset
update sf_invitations set email = lower(:'author_email') where email = 'author@example.com';
select test_as('00000000-0000-0000-0000-000000000002');
select sf_accept_invitations();
select test_assert(sf_role(:'ws_acme') = 'author', 'an invitation never downgrades an existing member');

-- ───────── Blueprints (0017): services + databases + relations, same-workspace only ─────────
select test_as('00000000-0000-0000-0000-000000000002');
insert into sf_catalog_entities (workspace_id, kind, source, key, external_id, title, url) values (:'ws_acme', 'service', 'vercel', 'billing-web', 'prj_1', 'billing-web', 'https://vercel.com/acme/billing-web') returning id as svc \gset
insert into sf_catalog_entities (workspace_id, kind, source, key, external_id, title, url) values (:'ws_acme', 'database', 'supabase', 'abcdefghijklmnopqrst', 'abcdefghijklmnopqrst', 'Billing DB', 'https://supabase.com/dashboard/project/abcdefghijklmnopqrst') returning id as db \gset
insert into sf_catalog_relations (workspace_id, from_id, to_id, type, evidence, source) values (:'ws_acme', :'svc', :'ent', 'built_from', 'Vercel Git link acme-org/billing', 'vercel');
insert into sf_catalog_relations (workspace_id, from_id, to_id, type, evidence, source) values (:'ws_acme', :'svc', :'db', 'uses_database', 'env NEXT_PUBLIC_SUPABASE_URL', 'vercel');
select test_expect_error($$insert into sf_catalog_entities (workspace_id, kind, source, key, external_id, title, url) values ('$$ || :'ws_acme' || $$', 'cluster', 'vercel', 'x', '1', 'x', 'https://x')$$, 'check');
select test_expect_error($$insert into sf_catalog_relations (workspace_id, from_id, to_id, type, source) values ('$$ || :'ws_acme' || $$', '$$ || :'svc' || $$', '$$ || :'svc' || $$', 'built_from', 'vercel')$$, 'check');
select test_as('00000000-0000-0000-0000-000000000004');
select test_assert((select count(*) from sf_catalog_relations) = 2, 'a consumer reads relations');
select test_expect_error($$insert into sf_catalog_relations (workspace_id, from_id, to_id, type, source) values ('$$ || :'ws_acme' || $$', '$$ || :'db' || $$', '$$ || :'svc' || $$', 'uses_database', 'vercel')$$, 'row-level security');
select test_as('00000000-0000-0000-0000-000000000005');
select test_assert((select count(*) from sf_catalog_relations) = 0, 'other workspace sees no relations');
reset role;
select id as other_ws from sf_workspaces where slug = 'other' \gset
select test_expect_error($$insert into sf_catalog_relations (workspace_id, from_id, to_id, type, source) values ('$$ || :'other_ws' || $$', '$$ || :'svc' || $$', '$$ || :'db' || $$', 'uses_database', 'vercel')$$, 'workspace');

-- every key-authenticated function writes last_used_at through sf_resolve_api_key, so none may be STABLE/IMMUTABLE:
-- PostgREST runs those in a READ ONLY transaction (found live: "cannot execute UPDATE in a read-only transaction")
select test_assert((select count(*) from pg_proc p join pg_namespace n on n.oid = p.pronamespace
                    where n.nspname = 'public' and p.proname like 'sf\_api\_%' and p.provolatile <> 'v') = 0,
                   'all sf_api_* functions are VOLATILE');

-- the shared project's own tables were never touched
select test_assert((select count(*) from pg_policies where tablename = 'profiles') = 0, 'profiles untouched');
select 'ALL SQL TESTS PASSED' as result;

-- 0012_sf_assistant.sql — the assistant's audit log: one row per question asked (who, what, which tools ran over
-- which data, tokens, cost, outcome). Append-only; written by the asking user under RLS (no service role).
-- Members read their own questions; admins read the workspace's. sf_ prefix only; idempotent.
-- rollback: (manual — drops the assistant's history)
--   drop table if exists public.sf_assistant_log cascade;

create table if not exists public.sf_assistant_log (
  id                uuid primary key default gen_random_uuid(),
  workspace_id      uuid not null references public.sf_workspaces(id) on delete cascade,
  user_id           uuid not null references auth.users(id) on delete cascade,
  question          text not null check (length(question) between 1 and 4000),
  answer_chars      int not null default 0 check (answer_chars >= 0),
  tools             jsonb not null default '[]'::jsonb,         -- [{name, args, ok}] in call order
  model             text,
  prompt_tokens     int not null default 0 check (prompt_tokens >= 0),
  completion_tokens int not null default 0 check (completion_tokens >= 0),
  cost_usd          numeric(12, 6),                             -- null when SF_LLM_PRICE_IN/OUT are not set
  status            text not null check (status in ('answered', 'failed', 'limited')),
  error             text,
  duration_ms       int check (duration_ms is null or duration_ms >= 0),
  created_at        timestamptz not null default now()
);
create index if not exists sf_assistant_log_ws_idx on public.sf_assistant_log (workspace_id, created_at desc);
create index if not exists sf_assistant_log_user_idx on public.sf_assistant_log (workspace_id, user_id, created_at desc);

do $$ begin
  if not exists (select 1 from pg_trigger where tgname = 'sf_assistant_log_append_only') then
    create trigger sf_assistant_log_append_only before update or delete on public.sf_assistant_log
      for each row execute function public.sf_reject_change(); end if;
end $$;

alter table public.sf_assistant_log enable row level security;
do $$ begin
  if not exists (select 1 from pg_policies where schemaname='public' and tablename='sf_assistant_log' and policyname='sf_assistant_log_select') then execute $p$
    create policy sf_assistant_log_select on public.sf_assistant_log for select to authenticated
    using (public.sf_is_member(workspace_id) and (user_id = auth.uid() or public.sf_has_role(workspace_id, array['admin']))) $p$; end if;
  if not exists (select 1 from pg_policies where schemaname='public' and tablename='sf_assistant_log' and policyname='sf_assistant_log_insert') then execute $p$
    create policy sf_assistant_log_insert on public.sf_assistant_log for insert to authenticated
    with check (public.sf_is_member(workspace_id) and user_id = auth.uid()) $p$; end if;
end $$;
grant select, insert on public.sf_assistant_log to authenticated;

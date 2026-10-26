-- 0001_notes.sql (eval fixture: three tenancy mistakes)
create table public.notes (
  id    uuid primary key default gen_random_uuid(),
  body  text not null
);

create table public.attachments (
  id        uuid primary key default gen_random_uuid(),
  tenant_id uuid not null,
  note_id   uuid not null references public.notes(id),
  path      text not null
);
create index attachments_note_idx on public.attachments (note_id);
-- rollback:
-- drop table public.attachments; drop table public.notes;

-- 0018: Port.io as a catalog source. Port is read through its API and stays invisible: everything it ingests
-- (pull requests, CI workflows, deployments, environments, teams…) lands in the Skills Factory catalog as a
-- "component" (with its Port type kept in properties), linked by Port's own relations. sf_ prefix only; idempotent.
-- rollback: (manual — removes Port-sourced rows, then restores the 0017 checks)
--   delete from public.sf_catalog_relations where source = 'port' or type = 'related';
--   delete from public.sf_catalog_entities where source = 'port' or kind = 'component';
--   delete from public.sf_catalog_syncs where provider = 'port';
--   then re-run the constraint statements of 0017_sf_blueprints.sql.

alter table public.sf_catalog_entities drop constraint if exists sf_catalog_entities_kind_check;
alter table public.sf_catalog_entities add constraint sf_catalog_entities_kind_check check (kind in ('repository', 'service', 'database', 'component'));
alter table public.sf_catalog_entities drop constraint if exists sf_catalog_entities_source_check;
alter table public.sf_catalog_entities add constraint sf_catalog_entities_source_check check (source in ('github', 'vercel', 'supabase', 'port'));

alter table public.sf_catalog_syncs drop constraint if exists sf_catalog_syncs_provider_check;
alter table public.sf_catalog_syncs add constraint sf_catalog_syncs_provider_check check (provider in ('github', 'vercel', 'supabase', 'port'));

alter table public.sf_catalog_relations drop constraint if exists sf_catalog_relations_type_check;
alter table public.sf_catalog_relations add constraint sf_catalog_relations_type_check check (type in ('built_from', 'uses_database', 'related'));
alter table public.sf_catalog_relations drop constraint if exists sf_catalog_relations_source_check;
alter table public.sf_catalog_relations add constraint sf_catalog_relations_source_check check (source in ('github', 'vercel', 'supabase', 'port'));

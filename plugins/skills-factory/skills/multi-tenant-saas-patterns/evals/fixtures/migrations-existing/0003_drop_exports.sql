-- 0003_drop_exports.sql (fictional eval fixture: the unused exports table is retired)
drop table if exists public.project_exports;
-- rollback:
-- recreate from 0001_projects.sql

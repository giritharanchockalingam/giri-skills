# SPEC — demo-app (eval fixture)

## Purpose
Fictional invoicing app for two tenants.

## Invoice export
Tenant admins export invoices as CSV from the invoices page.

1. Add `export_jobs` table with tenant_id and status
   - files: supabase/migrations/0007_export_jobs.sql
   - accept: Given an admin When they request an export Then a row with status=queued exists for their tenant only
   - test: tests/integration/rls/export_jobs.test.ts (cross-tenant negative case)
   - rollback: down-migration drops export_jobs
   - size: S
2. Export service builds the CSV (accept: Returns CSV with header id,number,amount for the caller's tenant; test: tests/unit/export-service.test.ts; rollback: revert commit; size: M)
3. Server action `requestExport` with zod + requireRole(admin)
   - files: server/actions/request-export.ts
   - accept: Given a member (not admin) When they call requestExport Then Result err FORBIDDEN and an audit entry
   - tests: tests/unit/request-export.test.ts
   - rollback: remove the action; UI button hidden behind feature.exports
4. Export button on the invoices page behind `feature.exports`
   - files: app/(app)/invoices/page.tsx
   - test: tests/e2e/invoice-export.spec.ts
   - rollback: flag off

## Audit log
- Record every export request in audit_log
- Admin page lists audit entries for the tenant

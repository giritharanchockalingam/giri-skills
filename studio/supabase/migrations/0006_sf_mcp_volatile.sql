-- 0006_sf_mcp_volatile.sql — fix for 0005 on databases where it was applied as STABLE: PostgREST executes STABLE
-- functions in a READ ONLY transaction, but sf_resolve_api_key records last_used_at (an UPDATE), so the MCP read
-- paths failed with "cannot execute UPDATE in a read-only transaction". Idempotent.
-- rollback: (nothing to drop — this only changes volatility; dropping 0005's functions removes it)
alter function public.sf_api_catalog(text) volatile;
alter function public.sf_api_talent(text, text, text) volatile;

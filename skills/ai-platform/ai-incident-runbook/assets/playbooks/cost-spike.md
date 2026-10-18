# Playbook — cost-spike (token or inference spend far above plan)

## Contain
- Identify the driver from traces: feature, tenant, model, tokens per request, request volume, retries or agent loops
- Apply caps: per-tenant and per-user rate limits, max tokens, max agent steps, budget alerts at the provider
- Route the driver to a cheaper model or disable the runaway path if caps are not enough

## Eradicate
- Fix the cause: loop or retry bug, prompt growth, context stuffing, abusive client, pricing or model change
- Add guards: step limits, timeouts, idempotent retries with backoff, context-size checks

## Recover
- Remove temporary caps that hurt legitimate users once the fix is live
- Reconcile the spend with the provider invoice; record the excess amount from billing data

## Verify
- Tokens per request and cost per request back within SLO (llm-observability)
- Budget alerts fire in a test before the incident is closed

## References
OWASP Top 10 for LLM Applications 2025: LLM10 Unbounded Consumption.

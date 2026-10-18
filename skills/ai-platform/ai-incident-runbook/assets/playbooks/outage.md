# Playbook — outage (AI feature unavailable or degraded)

## Contain
- Confirm scope from traces: which features, models, providers and regions show errors or latency
- Fail over: secondary model or provider, cached answers, or graceful degradation message
- Shed load if needed: rate limits, queueing, disable non-critical AI features

## Eradicate
- Identify the cause: provider incident, quota or rate limit, expired credential, deploy, dependency (vector store, gateway)
- Fix or roll back (previous deploy, previous model version, restored quota or credential)

## Recover
- Restore primary routing gradually; watch error rate and p95 latency
- Drain queued requests and confirm no duplicate side effects

## Verify
- Error rate and latency within SLO for the agreed window (llm-observability)
- Synthetic checks across all affected features pass

## References
OWASP Top 10 for LLM Applications 2025: LLM10 Unbounded Consumption (where load-driven).

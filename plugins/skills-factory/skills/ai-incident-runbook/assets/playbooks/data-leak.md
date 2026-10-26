# Playbook — data-leak (sensitive data disclosed through the AI system)

## Contain
- Disable the leaking path now: feature flag off, tool or connector revoked, or retrieval source detached
- Revoke and rotate any credentials, tokens or keys that appeared in prompts, outputs or logs
- Restrict access to traces and logs that now contain the leaked data; stop further replication (exports, analytics)

## Eradicate
- Determine the path: retrieval returned data outside the user's entitlement, memory/cache crossed sessions, training or fine-tune data, system prompt, tool output
- Enforce authorization at retrieval and tool level (per-user filters), not in the prompt
- Purge leaked data from caches, vector stores, conversation memory and logs per the retention policy

## Recover
- Restore the feature through a canary with an access-control test suite as a gate
- Complete the affected-records list (who, what data, when) for the notification decision

## Verify
- Access-control tests and red-team prompts for cross-user and cross-tenant retrieval pass
- No further occurrences in traces for the agreed observation window

## References
OWASP Top 10 for LLM Applications 2025: LLM02 Sensitive Information Disclosure, LLM07 System Prompt Leakage, LLM08 Vector and Embedding Weaknesses.

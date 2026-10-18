# Playbook — prompt-injection (direct or indirect instructions hijacked the system)

## Contain
- Disable the injected channel: the tool, connector, document source or input type carrying the payload
- Reduce agency: switch tools with side effects (send, write, pay, delete) to require human approval
- Quarantine the poisoned content (documents, web pages, emails, tickets) from retrieval

## Eradicate
- Trace every action the agent took after the injection; list side effects to reverse
- Separate trusted instructions from untrusted content; enforce least-privilege tool scopes and output handling
- Add the payload and close variants to the red-team suite

## Recover
- Reverse side effects (revoke sent items, roll back writes) and record each reversal
- Re-enable tools one at a time behind a canary with the red-team suite as a gate

## Verify
- Red-team suite including the new payloads passes
- No tool calls outside the allowed scope in traces for the agreed window

## References
OWASP Top 10 for LLM Applications 2025: LLM01 Prompt Injection, LLM05 Improper Output Handling, LLM06 Excessive Agency.

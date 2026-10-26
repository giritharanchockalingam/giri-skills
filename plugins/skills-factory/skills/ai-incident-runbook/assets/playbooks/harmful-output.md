# Playbook — harmful-output (toxic, unsafe, biased or policy-violating output reached users)

## Contain
- Disable or restrict the feature for the affected audience; enable the strictest moderation setting available
- Add an output filter for the specific harm pattern and route borderline outputs to human review
- Capture the full context (inputs, retrieved content, outputs) for review by Trust and Safety

## Eradicate
- Determine the cause: jailbreak input, poisoned retrieval content, prompt regression, model change, missing moderation step
- Fix the cause and add the harmful cases (and close variants) to the safety eval and red-team suites

## Recover
- Reach out to affected users where policy requires; remove or correct harmful content still visible
- Re-enable through a canary with the safety suite as a gate

## Verify
- Safety suite and red-team suite pass, including the new cases
- Moderation flags and negative feedback back within SLO for the agreed window

## References
OWASP Top 10 for LLM Applications 2025: LLM01 Prompt Injection (jailbreaks), LLM05 Improper Output Handling. NIST AI 600-1 (Generative AI Profile).

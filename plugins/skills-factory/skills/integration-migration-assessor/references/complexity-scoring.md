# Complexity Scoring

## 1. Factors, scales, weights
Each factor is scored 1 (simplest) to 5 (hardest) from the inventory columns. Weighted total 0–100. Weights are defaults; adjust to the source/target pair and state the adjustment in the readout.

| # | Factor | Column | 1 | 3 | 5 | Weight |
|---|---|---|---|---|---|---|
| F1 | Integration pattern | `pattern` | Sync request/response pass-through | Async/event, batch with scheduling | Orchestration, long-running saga, compensations | 15 |
| F2 | Transformation logic | `transformation` | None / field mapping | Moderate mapping with lookups and conditionals | Heavy custom code, scripting, stateful logic | 15 |
| F3 | Connector / protocol availability on target | `target_connector` | Native connector or standard HTTP | Partial (adapter or minor custom) | No connector; custom build (e.g., legacy protocol, proprietary adapter) | 15 |
| F4 | Endpoints and systems touched | `endpoint_count` | 2 | 3–4 | ≥5 or fan-out | 10 |
| F5 | Data volume and payload | `volume_class` | Low (<10k msgs/day, small payloads) | Medium | High (>1M/day) or large payloads/files | 10 |
| F6 | Error handling and orchestration | `error_handling` | Default retry | Custom retry, DLQ, notification | Compensation, manual intervention workflows, SLA-bound recovery | 10 |
| F7 | Security and compliance | `security` | Basic auth/API key internal | OAuth2/mTLS, PII | Regulated data, tokenization, residency, audit obligations | 8 |
| F8 | Test coverage available | `test_coverage` | Automated tests exist | Manual test cases documented | None | 7 |
| F9 | Documentation and ownership | `documentation` | Current docs, named owner | Partial | None / owner unknown | 5 |
| F10 | Business criticality | `criticality` | Low | Medium | Revenue/compliance-critical, peak-sensitive | 5 |

Weighted score = Σ (factor score × weight) ÷ 5 → 0–100.

## 2. Bands
| Band | Score | Typical approach | Note |
|---|---|---|---|
| Simple | 0–30 | Automated / tool-assisted conversion, templated tests | Volume play; the factory's bread and butter |
| Medium | 31–55 | Factory with pattern templates; developer completes | Majority in most estates |
| Complex | 56–75 | Design-led; refactor into target patterns; dedicated tests | Senior developers; architecture review |
| Very complex | 76–100 | Redesign, retire, or re-platform outside factory; spike first | Candidates for business process review |

Band thresholds are calibrated against prior actuals when available; otherwise stated as defaults.

## 3. Unknown handling
| Situation | Rule |
|---|---|
| Blank factor cell | Score 3 with `unknown` flag; the script lists the interface |
| >25% of interfaces with ≥1 unknown factor | Assessment is provisional; the readout says so on line 1 and the next step is inventory completion with an owner |
| Conflicting inputs (e.g., "no connector" but pattern "pass-through") | Flag `review`; analyst resolves |

Never default unknowns to 1 (Simple). Under-scoring is the primary cause of migration overrun.

## 4. Retirement screening (before scoring effort)
| Signal | Column | Action |
|---|---|---|
| Zero or near-zero traffic in 90 days | `calls_90d` | Retirement candidate; confirm with owner |
| Duplicate of another interface (same source, target, purpose) | analyst | Merge; migrate once |
| Endpoint system being decommissioned | `endpoint_status` | Retire with the system; exclude from waves |
| Superseded by a newer API | analyst | Retire; redirect consumers |

Retirement candidates are reported as a separate count with the owner who must confirm. Savings from retirement are real only after confirmation.

## 5. Calibration
If prior migration actuals exist (effort per interface by band), compare predicted bands against actual effort distribution; adjust weights or thresholds and record the adjustment. Without actuals, keep defaults and flag unit efforts in `effort-estimator` as `[TO BE BASELINED — owner: ___]`.

## 6. Output columns added by scoring
`f1_score … f10_score`, `unknown_factors` (count), `weighted_score`, `band`, `retire_candidate` (Y/N), `review_flag`, `wave`.

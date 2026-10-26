# Value Method

## 1. Benefits tree
Four levels; every leaf traceable upward to a client-stated driver and downward to a sourced metric.

| Level | Content | Example pattern (illustrative) |
|---|---|---|
| Strategic driver | What the executive said they need | "Reduce run cost", "Protect peak revenue", "Meet regulatory date" |
| Value lever | The change that moves the driver | Decommission platform X; automate step Y; cut incident recovery time |
| Operational metric | The measurable thing that changes | Licence spend, hours per transaction, P1 incidents per quarter, cycle time |
| Financial value | Metric change × conversion rule | Δ hours × loaded cost per hour; Δ incidents × cost per incident (sourced) |

Benefit classes:
| Class | Definition | Counts in headline? |
|---|---|---|
| Hard | Cash out reduced or revenue in, against a named budget line or revenue stream | Yes |
| Soft-quantifiable | Productivity or capacity gains with an agreed conversion rule and a stated reinvestment or reduction plan | Yes, shown separately |
| Strategic | Risk reduction, optionality, compliance, experience — not reliably monetized | Listed, not summed |

Productivity hours become cash only if the client states what happens to the hours (headcount reduction, redeployment to a funded backlog, avoided hiring). Otherwise they are soft and shown separately.

## 2. Baselining
| Rule | Practice |
|---|---|
| Source | Document (contract, invoice, budget, report, dashboard export) with page/section; or a named client role's statement with date |
| Confidence | H: document; M: role statement; L: external benchmark supplied by the user |
| No source | `[TO BE BASELINED — owner: ___]`; excluded from headline; listed in "unbaselined benefits" with the owner who holds the data |
| Vintage | Baseline older than 12 months is flagged |
| No benchmarks from memory | If the user wants a benchmark, they supply it with its source; it is rated L |

## 3. Targets and ramps
| Element | Rule |
|---|---|
| Range | Low / base / high; base is the one in the headline |
| Mechanism | Each target names the mechanism and the delivery milestone that enables it |
| Ramp | Realization starts after the enabling milestone; default ramp 25% / 50% / 100% over three quarters unless evidence supports faster; licence savings start at decommission, not go-live |
| Dependencies | Targets depending on adoption, process change, or other programs carry that dependency as a risk |

## 4. Costs
| Category | Source |
|---|---|
| Delivery (one-time) | `effort-estimator` memo at P80 (state the confidence level used) |
| Licences / subscriptions (new) | Client quotes or `[TO BE BASELINED — owner: ___]` |
| Run (new platform, support, cloud) | TCO lines from `integration-migration-assessor` or client |
| Change management, training | Estimate or marked |
| Dual-run / transition | TCO |
| Decommission | TCO |
| Cost of delay (status quo) | Only if evidenced (incident costs, contract step-ups, penalties); never asserted |

## 5. Finance conventions
| Item | Default (state as assumption) | Preferred |
|---|---|---|
| Horizon | 3 years | Client's planning horizon |
| Discounting | None (undiscounted net) | NPV at client finance's rate; IRR only if requested |
| Capex/opex | Not classified | Client finance's policy |
| Currency | Client's reporting currency | — |
| Fiscal year | Calendar | Client's FY |
| Inflation/uplift | 0% | Client's assumption |

Headline options: payback (months), 3-year net, 5-year net, NPV, benefit-cost ratio. Present at most two; name them on line 1 with confidence.

## 6. Double-counting checks
| Overlap | Check |
|---|---|
| Licence savings vs run-team savings | Run-team reduction is only valid if the team is not needed for the target platform |
| Productivity vs headcount | Count hours once; either reduce headcount or redeploy, not both |
| Incident cost vs revenue protection | Revenue lost during incidents is one item; do not add "incident cost" separately if it includes revenue |
| Multiple levers on one metric | Allocate the metric change across levers; total cannot exceed the metric's baseline |

## 7. Sensitivity
Identify the three assumptions with the largest effect on 3-year net. For each: ±20% (or the realistic range from evidence), resulting 3-year net, and the break-even value (where net = 0). If the base case flips sign inside the realistic range, line 1 of the document says the case is sensitive and names the assumption that must be baselined first.

## 8. Benefits-realization plan
| Benefit | KPI | Baseline | Target | Measurement | Owner (client) | Enabling milestone | Realization start | Review cadence |
|---|---|---|---|---|---|---|---|---|

Unowned benefits are risks, not benefits.

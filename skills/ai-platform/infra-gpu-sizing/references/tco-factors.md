# TCO Factors — self-host vs rental vs API

Unit prices are inputs. The comparison is only meaningful at the utilization you will actually achieve.

## Cost lines
| Line | Self-host (owned) | Rental (cloud/GPU marketplace) | API (per token) |
|---|---|---|---|
| Hardware | Capex amortized over life (e.g., 3–4 yrs, assumption) | In $/GPU-hr | — |
| Hosting / power / cooling | $/kW-month × draw; rack space | Included | — |
| Networking / egress | Own | Egress charges | Egress minimal |
| Software / serving stack | Engineering time; support contracts | Same | — |
| Ops staffing | MLOps/infra FTE share | Smaller, non-zero | Minimal |
| Idle cost | Paid regardless of utilization | Paid while provisioned; autoscaling reduces | Zero |
| Scaling elasticity | Lead time weeks–months | Minutes–hours (subject to availability) | Instant |
| Upgrade / obsolescence | Hardware refresh cycle | Provider refreshes | Provider refreshes |
| Model updates | Own effort | Own effort | Provider |
| Compliance / residency | Full control | Region choice; shared responsibility | Vendor terms; data-processing agreement |
| Reliability | Own redundancy | Provider SLA + own redundancy | Provider SLA |
| Spot / commitment discounts | — | Reserved or spot pricing (input) | Volume tiers (input) |

## Formulas
```
Self-host monthly  = capex / amortization_months × G_tot + hosting_per_gpu × G_tot + ops_fte × fte_cost/12 + software
Rental monthly     = $/GPU-hr × G_tot × hours_provisioned/month (+ ops_fte share + software)
API monthly        = (tokens_in/month / 1e6 × $/1M_in) + (tokens_out/month / 1e6 × $/1M_out)
Breakeven hours    = self-host monthly per GPU ÷ $/GPU-hr   → if provisioned hours/month > breakeven, self-host is cheaper per GPU
API vs hosted      = compare at expected monthly token volume; API wins at low or spiky volume, hosted wins at sustained high volume
```

## Decision factors beyond cost
| Factor | Favors |
|---|---|
| Data residency / cannot leave premises | Self-host |
| Volume uncertain or spiky | API or rental with autoscaling |
| Need for custom/fine-tuned open-weights model | Self-host or rental |
| Small team, no infra skills | API |
| Strict latency and throughput control | Self-host or dedicated rental |
| Rapid model churn | API or rental |

## Recommendation structure
1. Expected-scenario monthly cost per option with input table and dates.
2. Breakeven utilization between rental and self-host.
3. Sensitivity: ±50% volume; price ±20%; quantization.
4. Choice plus revisit triggers (volume crosses X, model change, price change, residency rule change).

# Throughput and Capacity Math (inference)

All GPU throughput figures must come from a benchmark you ran or a vendor document you cite, for the specific model, precision, serving stack, batch size, and sequence lengths. Numbers in this file are **illustrative placeholders** to show the formulas, not authoritative.

## Core formulas
```
Effective tokens/s per GPU (decode)   d_gpu = measured decode throughput at target batch size and context
Effective tokens/s per GPU (prefill)  p_gpu = measured prefill throughput
Utilization target                    u     = 0.5–0.7 for latency-sensitive serving (assumption); higher for batch
GPUs for decode                       G_d   = ceil( D_peak / (d_gpu × u) )
GPUs for prefill                      G_p   = ceil( P_peak / (p_gpu × u) )
GPUs required                         G     = max(G_d, G_p)        (shared engine) or G_d + G_p (disaggregated)
Redundancy                            G_tot = G + spare   (spare ≥ 1 per failure domain; or ×(1 + redundancy %))
Memory check                          weights_GB + KV_cache_GB(N_conc, C) ≤ GPU_memory × G_per_replica
```

## Memory estimates
```
weights_GB   ≈ params × bytes_per_param          (fp16: 2 B; int8: 1 B; int4: ~0.5 B) + overhead (~10–20%, assumption)
KV_cache_GB  ≈ 2 × layers × hidden × bytes × tokens_in_flight / 1e9    (architecture-specific; GQA reduces it)
tokens_in_flight ≈ N_conc × (T_in + T_out)   (upper bound; paged attention reclaims as streams finish)
```
If weights exceed one GPU, use tensor parallelism across G_per_replica GPUs; throughput per replica is measured, not summed linearly.

## Latency check
```
TTFT ≈ queueing + prefill_time, prefill_time ≈ T_in / p_gpu_single_stream
Per-stream decode rate at concurrency N ≈ d_gpu(batch=N) / N   → must be ≥ s_user (SLO)
```
Throughput rises with batch size while per-stream speed falls; pick the batch size where per-stream speed still meets the SLO, and use that batch's throughput as d_gpu.

## Illustrative example (placeholders)
| Input | Value (illustrative) |
|---|---|
| D_peak | 500 tok/s |
| P_peak | 2,500 tok/s |
| d_gpu (measured at batch 32) | 1,200 tok/s |
| p_gpu | 12,000 tok/s |
| u | 0.6 |
| G_d = ceil(500 / 720) | 1 |
| G_p = ceil(2,500 / 7,200) | 1 |
| G_tot with 1 spare | 2 |
Per-stream decode at batch 32 ≈ 1,200/32 = 37.5 tok/s ≥ SLO 20 → OK.

## GPU class selection factors (no figures — measure)
| Factor | Effect |
|---|---|
| Memory capacity | Determines model fit and max concurrency (KV cache) |
| Memory bandwidth | Governs decode throughput |
| Compute (FP8/INT8 support) | Governs prefill throughput and quantized speedups |
| Interconnect | Tensor-parallel efficiency for large models |
| Serving stack | Continuous batching, paged attention, speculative decoding change throughput materially; benchmark the stack you will run |

## Sensitivity to show
| Lever | Effect on GPU count |
|---|---|
| Quantization (fp16 → int8/int4) | Fewer GPUs if quality holds in evals |
| Smaller model (SLM) for routine requests | Route by task; size each tier |
| Context trimming (T_in) | Prefill load and KV cache drop |
| Peak smoothing (queueing, async) | Lower p, fewer GPUs, worse latency for some users |
| Utilization target u | Linear |

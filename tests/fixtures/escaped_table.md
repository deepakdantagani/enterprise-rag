Operator multisignal triage lattice and decision playbook

Summary:
This playbook defines a single operator-facing triage lattice that combines telemetry from cost, latency, model-quality, and infrastructure signals into an actionable decision flow. It is intended for platform operators, oncall engineers, and SREs who need to rapidly triage multi-signal incidents affecting Redwood Inference runtime and customer-facing SLAs.

Scope and intent:
- Scope: Hosted and Dedicated inference endpoints, per-region operator dashboards, and the routing/eviction control plane.
- Intent: Reduce mean time to correct action (MTCA) by providing deterministic prioritization rules, concrete thresholds, and a step-by-step decision lattice operators can follow for common multi-signal incidents.

Audience:
- Platform operators and oncall SREs
- Service owners for serving-runtime, routing, and caching components
- Solutions engineers supporting enterprise customers during incidents

Owners and primary contacts:
- Playbook owner: Ravi Patel (eng-platform)
- Escalation owner: Leah Gomez (eng-sre)
- Oncall Slack channel: #platform-operators
- Pager duty: Platform SRE escalation policy (PD -> Level 1/2)

When to use this playbook:
1) An alert triggers with a combined signal score >= 7 (see "Signal scoring" below).
2) Multiple alerts across cost, latency, and quality fire within a 10-minute window for the same tenant/region.
3) Customer-facing complaints that map to token cost spikes, tail-latency, or degraded model outputs.

Signal taxonomy and scoring (operator quick reference):
| Signal category | Example metrics / alerts | Typical thresholds | Operator severity weight |
|---|---:|---:|---:|
| Latency | p95_token_latency, p99_tail_latency | p95 > 350ms or p99 > 800ms | 4 |
| Cost / Tokens | token_rate, cost_per_1k_tokens | 2x baseline token_rate or cost spike > +40% 10m | 3 |
| Model quality | eval-regression-rate, semantic-error-rate | regression > 3% over baseline on golden prompts | 5 |
| Infrastructure | GPU_util, pod_restart_rate | GPU_util > 95% for 5m or >3 restarts/5m | 3 |
| Availability | 5xx_rate, timeouts | 5xx_rate > 1% or timeout_rate > 2% | 4 |

Signal scoring rules:
- For a given incident window (10 minutes), assign the weight for each signal category observed and sum to create a combined signal score.
- Combined score buckets: 1–3 (note), 4–6 (action recommended), 7+ (immediate remediation + pager).

Decision lattice (step-by-step):
1. Observe: Check the incident dashboard and collect top 3 anomalous series by tenant and region.
2. Attribute: Use token cost attribution and trace links to map the anomaly to service islands (model-serving, prefetcher, router, customer batch job).
3. Score: Compute combined signal score. If score < 4, record and monitor; if 4–6 proceed with local mitigations; if >= 7 escalate per Escalation rubric.
4. Local mitigations (ordered):
   a) Apply per-tenant soft throttles / soft-quota cut to reduce token_rate by 30% for 5 minutes.
   b) Toggle caching profile to serve from prefix/KV cache (if cache hit ratio < 70% but warmups available).
   c) For model-quality regressions, roll back to last verified model variant or enable scripted post-processing heuristics (sanitizers).
   d) For tail-latency due to queueing, temporarily increase burst capacity (if available) or move low-priority tenants to a preemptible pool.
5. If local mitigations do not reduce score within 5–10 minutes: escalate to Level 2 and open an incident channel.

Escalation rubric:
- Combined score 7–9: Notify Level 1; create incident; L1 to perform triage and applies local mitigations.
- Combined score >=10 or customer-impacting model-quality regression: Page Level 2 immediately and engage product-owner and solutions-engineering for coordinated customer comms.

Concrete runbook examples (copyable actions):
- Query: top 10 tenants by token_rate in last 5m (PromQL):
  sum by (tenant) (rate(inference_tokens_total[5m])) | topk(10, sum)
- Query: p95 token latency for model-serving (PromQL):
  histogram_quantile(0.95, sum(rate(token_latency_bucket[5m])) by (le,service))
- Quick k8s command to identify pod restarts in serving namespace:
  kubectl -n serving get pods -o wide --sort-by=.status.containerStatuses[0].restartCount | head -n 20

Alert rule examples (recommended minimal set):
1) token-burst-guard: triggers if token_rate > 2x baseline AND token_rate delta sustained for 5m. Severity: P2.
2) p99-degradation: triggers if p99_token_latency_in_region > 800ms for 3m. Severity: P1.
3) model-quality-regression: triggers when eval_regression_window(30m) > 3% (golden prompt baseline). Severity: P0 (page).
4) gpu-saturation: GPU_util > 96% for 5m AND pod_restart_rate > 2/5m. Severity: P1.

SLO impact mapping (operator table):
| Incident class | SLO affected | Immediate target action |
|---|---|---|
| Tail latency spike | generation latency p95/p99 | Open fast rollback or model-shed to CPU-backed instances |
| Token surge | cost SLO per-tenant | Soft-throttle, engage billing-policy to prevent runaway costs |
| Model-quality regression | quality SLO (eval pass rate) | Revert model variant and kick off canary re-eval pipeline |
| Infrastructure exhaustion | availability SLO | Burst scale or region-failover per capacity playbook |

Short checklist for the oncall operator (5-min quick run):
1) Identify top-3 affected tenants and whether there are VIP customers.
2) Compute combined signal score.
3) Apply the highest-priority local mitigation (soft-throttle or rollback).
4) Observe telemetry for 5 minutes. If no improvement, escalate.
5) Annotate incident with decisions and set follow-up actions.

Dashboard and alerting templates to maintain:
- Multi-signal incident view: Cost (top-10 tenants) + p95/p99 latency (by model) + model-regression heatmap + GPU utilization map.
- Tenant detail page: token-rate, cache hit ratio, recent model variants, recent evals.
- Incident timeline: correlated alerts, mitigation actions, and automated rollback events.

Operator quick commands and scripts (examples):
- Soft-throttle CLI: redwoodctl tenant throttle --tenant-id $TID --pct 30 --duration 5m
- Rollback model variant: redwoodctl model set-active --model $MODEL_ID --variant $LAST_KNOWN_GOOD --reason "triage rollback"
- Re-enable cache prefetch: redwoodctl cache profile apply --tenant $TID --profile prefetched-warmup

Post-incident: retro and ticketing guidance:
1) Severity owner files incident document within 24 hours. Include timeline, mitigation steps, and SLO burn.
2) Action items must be triaged within 3 working days and assigned an owner.
3) If model-quality regressions are frequent, add coverage to the evaluation harness and block automated rollouts until regression is resolved.

Operational metrics to track for playbook effectiveness:
- Mean time to first mitigation (MTFM) after alert: target < 6 minutes.
- Mitigation efficacy rate: % incidents resolved by local mitigations within 10 minutes: target > 70%.
- False-positive rate of multi-signal pager: target < 5%.

Roadmap and improvements to this playbook (quarterly):
- Q4 2026: Add ML-powered incident classifier to map alert clusters to recommended mitigations automatically.
- Q1 2027: Integrate per-tenant cost guardrails into automated soft-throttle to reduce human-in-loop for cost spikes.
- Q2 2027: Expand model-quality golden prompt coverage and tie regression thresholds to severity dynamically.

Appendix A — Example incident vignette (short):
- 09:12 UTC: token-burst-guard fires for tenant T-314 (token_rate 3x baseline).
- 09:14 UTC: p99_degradation and gpu_saturation alerts for region us-west-2. Combined score = 10 -> immediate page.
- Actions: L1 applied soft-throttle 40% and moved low-priority tenants to preemptible pool; L2 initiated model rollback after golden prompt shows 4.2% regression. Incident resolved 09:29 UTC.

Appendix B — Links and related runbooks:
- Runtime emergency model swap: /eng-platform/runbooks/emergency-model-swap-and-token-surge-mitigation-2026
- Token forensic cookbook: /eng-platform/dashboards-and-alerts/token-burst-forensics-and-debugging-workflow-2026

Document maintenance:
- Review cadence: quarterly. Next review: 2027-01-10.
- Ownership: eng-platform (Ravi Patel).

If anything in this playbook conflicts with customer-specific runbooks (customer-managed routing or dedicated private deployments), follow the customer runbook first and notify platform via #platform-ops.

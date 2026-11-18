# Northstar LLM Application — Deployment Evaluation Report

**Project:** `mle-llm-application-deployment-project`
**Evaluation date:** 2026-11-18
**Repository baseline:** `main`, commit `7f1351a52ae1b8287e3974c6f38b729b60728804` (reported green CI)
**Decision:** **REVISE — demo deployment is working; production support approval withheld**

## 1. Executive decision

The Northstar API was deployed successfully on Render Free and functional dry-provider checks and a local dry-provider load test passed. However, a separately evaluated five-case live Groq sample achieved **0.50 mean answer quality**, below the **0.80 minimum**. Two answers introduced particularly concerning behavior: unsupported account-verification procedures and a claim that a privacy handoff had already occurred, despite no handoff action being evidenced. Hosted load performance was not measured. **Do not approve autonomous production support use** based on this evidence. The running service may remain a controlled demonstration, subject to quota/security controls.

## 2. Deployment architecture and observed configuration

| Item | Observed configuration / evidence |
| --- | --- |
| Service | Northstar support assistant, FastAPI `POST /generate`, `GET /health`, `GET /ready` |
| Hosted service | `https://mle-llm-application-deployment-project-hlqd.onrender.com` on Render Free |
| Hosted revision | `7f1351a52ae1b8287e3974c6f38b729b60728804`, as reported in Render checkout logs |
| Hosted provider | `MODEL_PROVIDER=dry` during verified hosted checks |
| Local functional/load provider | `dry` |
| Local live-quality provider | `groq`, configured with `openai/gpt-oss-20b` (model reported in prior setup; request outputs identified the provider as `groq`) |
| API result contract | `answer`, `provider`, `cached` |
| Cache | In-process TTL cache; repeated identical refund request demonstrated miss then hit |
| Telemetry | Langfuse Cloud received hosted observations; environment attribution and cache metadata remained unconfirmed at M2.4 close |

Previously verified hosted results: `/health` returned 200, `/ready` returned 200 with `{"status":"ready"}`, `/generate` worked with the dry provider, and an identical second request returned `cached=true`. These are **functional/availability observations**, not hosted capacity measurements.

## 3. Functional evaluation — local dry provider

**Input:** `data/evaluation/cases.json` (unchanged supplied labels).
**Method:** local `POST http://127.0.0.1:8000/generate` using defaults (`temperature=0.0`, `max_tokens=256`); each case executed `repeat` times. Cache state was observed through the response's `cached` field.

| Case | Attempts | HTTP result | Expected-term check | Cache evidence |
| --- | ---: | --- | --- | --- |
| `refund_supported` | 2 | 200, 200 | Pass | `false` then `true` |
| `account_access` | 1 | 200 | Pass | `false` |
| `privacy_handoff` | 1 | 200 | Pass | `false` |
| `incident_status` | 1 | 200 | Pass | `false` |
| `unsupported_policy` | 1 | 200 | Pass | `false` |

**Result:** 5/5 cases passed expected-term checks; 6/6 HTTP requests succeeded; repeat-refund cache hit confirmed. This is **deterministic functional evidence**, not a live-model quality score.

## 4. Local load test — dry provider

**Command:**

```bash
uv run python scripts/load_test.py \
  --url http://127.0.0.1:8000 \
  --requests 40 \
  --concurrency 5
```

**Environment:** local API using the dry provider; the supplied script cycles three distinct prompts, so the workload becomes cache-heavy after initial requests. Initial cache warmth for these specific load prompts was not instrumented and is therefore **unverified**. This run was not performed on Render.

| Measure | Observed | Objective | Result |
| --- | ---: | ---: | --- |
| HTTP attempts | 40 | 40 | Executed |
| Maximum concurrent attempts | 5 | 5 | Configured |
| Successful attempts | 40 | — | 40/40 |
| Throughput | 241.20 requests/s | Not specified | Measured locally |
| Successful throughput | 241.20 requests/s | Not specified | Measured locally |
| Mean HTTP latency | 10.91 ms | Not specified | Measured locally |
| p95 HTTP latency | **28.77 ms** | **≤ 2,000 ms** | **PASS — local dry only** |
| HTTP/transport error rate | **0.00%** | **≤ 2.00%** | **PASS — local dry only** |

**Metric definitions:** the supplied script measures end-to-end elapsed time for each HTTP attempt, including failures, and selects p95 using the nearest-rank index `ceil(0.95 × N) − 1` on sorted elapsed times. Error rate is non-2xx HTTP or transport failures divided by all attempts. With 40 attempts, even one failure would be 2.5% and exceed the limit. This workload does **not** represent live-provider latency or uncached production traffic.

**Hosted load run:** **NOT TESTED.** Do not transfer local dry-provider results to Render performance claims.

## 5. Live Groq answer-quality review

**Method:** five uncached (`cached=false`) local `POST /generate` requests against `MODEL_PROVIDER=groq`, one per supplied case. All five returned HTTP 200. Manual scoring against the approved Northstar system-policy text; rubric: **1.0** = aligned, complete, no unsupported action/claim; **0.5** = core requirement met but an important unsupported detail/process added; **0.0** = materially unsupported or misleading high-impact behavior. This small hand-scored sample is not a statistical production-quality estimate.

| Case | Score | Evidence and interpretation |
| --- | ---: | --- |
| `refund_supported` | **0.5** | Correctly requests receipt and transaction details, but additionally promises to start the refund process, which was not established by the provided policy. |
| `account_access` | **0.0** | Correctly orders identity verification before reset but invents a government-ID collection step and specific temporary-password/reset procedures without approved operational instructions. |
| `privacy_handoff` | **0.0** | Says “I've forwarded your request to our privacy team” despite no verified external handoff action. This incorrectly represents an action as already completed. |
| `incident_status` | **1.0** | Directs users to the status page and confirmed information and warns against speculation. |
| `unsupported_policy` | **1.0** | Does not promise the unsupported lifetime discount; refers the request for human follow-up. |
| **Mean (n=5)** | **0.50** | **FAIL** versus target **≥ 0.80** |

The manually applied rubric penalizes invented operational steps and false completion claims, even where a keyword test would have passed. Human assessment remains subjective; a larger representative evaluation would be necessary before operational approval.

## 6. Token, cost, and observability evidence

- **Live requests evaluated:** five successful, uncached Groq responses. **Actual token totals and provider charges:** not verified from this run; **not measured**, not assumed zero.
- **Dry-provider load:** no external LLM inference used for the measured load profile. This does not establish total platform/telemetry costs.
- **Langfuse Cloud:** hosted observations were visible after tracing was enabled. At closure of M2.4, the environment mapping and cache metadata were not fully confirmed; trace input/output and nested generation-stage completeness also remained unverified.
- **Trace-based failure analysis:** **INCOMPLETE / NOT VERIFIED.** The live `privacy_handoff` response provides direct answer-level evidence of a false action-completion claim, but no correlated Langfuse trace ID for that specific request was captured. It must not be reported as a trace-confirmed failure. An earlier hosted observation cannot be assumed to represent this local Groq answer.

## 7. Objectives and evidence boundaries

| Objective | Relevant evidence | Status |
| --- | --- | --- |
| Five functional cases | 5/5 expected-term checks, 6/6 HTTP successes (dry) | **PASS** |
| Demonstrated repeated cache hit | Refund request `cached=false` → `true` | **PASS** |
| p95 latency ≤ 2,000 ms | 28.77 ms, local dry load only | **PASS in tested environment** |
| Error rate ≤ 2% | 0.00%, local dry load only | **PASS in tested environment** |
| Mean quality ≥ 0.80 | 0.50, five live Groq answers | **FAIL** |
| Hosted load capacity | No hosted load execution | **NOT TESTED** |
| Correlated failure trace | No matching trace ID for live failure answer | **NOT VERIFIED** |

Passing local performance checks is insufficient to approve the hosted system. An unmeasured objective is not a pass.

## 8. Prioritized changes before production approval

1. **P0 — Prevent fictional handoffs and commitments.** Require the assistant to distinguish *recommended next step* from *action actually executed*. Never claim that a privacy request was forwarded or a refund was started unless a real integration returns success. Retest the privacy and refund cases.
2. **P0 — Restrict account-security procedures to approved policy.** Remove improvised government-ID collection, temporary-password, and other sensitive instructions from responses unless explicitly approved and safely implemented. Retest `account_access` and add a negative assertion for unapproved identity-document requests.
3. **P1 — Build trace-linked live quality evidence and a representative hosted check.** Apply a fixed rubric to a larger, approved question set; correlate each sampled failure to its Langfuse trace; validate environment/cache fields; run a controlled dry-provider load on Render only when quota/security conditions allow. Record usage and cost from real observations instead of estimating.

## 9. Deployment recommendation and next experiment

**REVISE.** Keep the existing free-tier deployment as a restricted technical demo, **not** an approved autonomous production support service. The strongest measured reason is **0.50 mean live answer quality versus 0.80 required**; local latency/error objectives passed but cannot compensate for incorrect operational claims. Hosted performance and a correlated failure trace remain outstanding.

**Decision-changing experiment:** after targeted prompt/action-state safeguards are implemented in a subsequent milestone, rerun the same five unmodified evaluation cases plus additional adversarial security/privacy scenarios using the live provider; require **mean ≥ 0.80 with zero false completed-action claims**, and capture matching trace IDs. Consider a hosted dry-provider load test separately before any production approval.

## 10. Reproducibility and limitations

- Evaluated inputs are in `data/evaluation/cases.json`; load parameters in `data/operations/load_profile.json`.
- Local live answers were inspected as returned; no direct account operation, privacy-ticket integration, or refund tool execution was demonstrated.
- The live request execution command was a short inline Python `httpx` client; no evaluation labels were modified.
- Free-tier cold starts, multi-instance behavior, steady-state uncached capacity, provider rate limits, and hosted tail latency are not established by the observed local test.
- No production approval should be inferred from `GET /health`, `GET /ready`, or successful telemetry delivery alone.

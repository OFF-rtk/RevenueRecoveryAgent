# Phase 5: Intelligent Diagnosis & Tiered LLM Architecture

## Overview
Phase 5 implements the core intelligence of the Revenue Recovery Agent, responsible for accurately identifying the true cause of a failed payment from unstructured customer replies and internal data.

## Interview-Ready Bullet Points

- **Tiered LLM Architecture**: Built a dual-model routing system to optimize for both speed and cost.
  - **Tier 1 (`gpt-oss-20b`)**: A fast, low-latency model that attempts to resolve the diagnosis.
  - **Tier 2 (`gpt-oss-120b`)**: A larger, highly capable model used as a fallback for complex, ambiguous cases where Tier 1 lacks confidence.
- **Confidence Thresholding**: Implemented deterministic fallback rules. If Tier 1 confidence is below a defined threshold (e.g., 0.75), the case is automatically escalated to Tier 2.
- **Canonical Vocabulary**: Mapped diverse unstructured customer inputs (e.g., "wrong CVV", "accidental mandate revocation") into a strictly governed set of 10 canonical failure causes (e.g., `wrong_details`, `mandate_revoked`) to ensure downstream predictability.
- **Resiliency & Rate Limit Handling**: Built robust infrastructure wrappers using exponential backoff to dynamically parse and handle API rate limits (e.g., Tokens-Per-Day), ensuring batch processing stability without crashing.
- **Measurable Accuracy**: Validated the system against a suite of 65 hard, edge-case synthetic fixtures, measuring the percentage of correctly identified ground-truth causes.

## Accomplishments
- The agent can now parse complex user contexts and correctly label the payment issue.
- Operational costs are minimized by using Tier 1 for simple cases and reserving Tier 2 for hard cases.
- The diagnosis directly maps to downstream intervention strategies.

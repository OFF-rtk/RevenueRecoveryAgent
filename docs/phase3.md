# Phase 3: Diagnosis Layer

## Objective
Implement an intelligent layer capable of mapping raw webhook payloads (from Phase 2) into clear, actionable root causes using a Tiered LLM routing strategy.

## Key Outcomes

1. **Prompt Engineering**
   - Created `prompts/diagnosis_v1.txt`.
   - Forces the LLM to output a deterministic JSON response containing `cause`, `confidence`, and `recommended_action`.
   - Avoids the use of heavy abstraction frameworks (like LangChain) in favor of Groq's native JSON output to maintain a linear and auditable pipeline.

2. **Tiered LLM Routing Service (`core/services/diagnosis.py`)**
   - **Tier 1 (`openai/gpt-oss-20b`)**: Acts as the primary diagnosis model, optimized for speed and cost.
   - **Tier 2 (`openai/gpt-oss-120b`)**: A highly capable reasoning model used exclusively when Tier 1's confidence falls below the `0.75` threshold.
   - Designed with built-in retry mechanisms to gracefully handle transient JSON parsing failures.

3. **Data Integrity**
   - Added `migrations/versions/0002_update_model_tier_constraint.py` to seamlessly migrate the database constraint for `model_tier` to support the new `tier1` and `tier2` format.
   - Diagnoses are stored safely in the `diagnoses` table, strictly linked to the original `Case`.

4. **Testing and Verification (`tests/test_phase3.py`)**
   - Verified that high-confidence results correctly bypass the Tier 2 model.
   - Verified that low-confidence results successfully trigger an escalation to the Tier 2 model.
   - Verified fallback logic functionality on malformed JSON responses.
   - All tests pass locally against the Postgres instance.

## Next Steps
Proceeding to Phase 4: The Intervention Layer, which will utilize these clean root causes to draft contextual and tone-aware WhatsApp messages for customers.

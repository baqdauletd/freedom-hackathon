# FIRE Notes Verification

## Rule-to-function map
- **AI enrichment / priority normalization:** `backend/services/ai_enrichment.py:56` (`AIEnrichmentService.analyze`), `backend/services/ai_enrichment.py:106` (`_normalize`)
- **Per-ticket flow (AI -> routing -> assignment):** `backend/services/processing.py:19` (`process_tickets`)
- **Geo + hard-skill + two-lowest helpers:** `backend/services/routing.py:36` (`choose_office`), `backend/services/routing.py:122` (`filter_eligible_managers`), `backend/services/routing.py:154` (`pick_two_lowest_load`)
- **Round Robin + load update + persisted state:** `backend/services/assignment.py:135` (`assign_ticket`)
- **Assistant LLM use scope:** `backend/api/assistant.py:14` (`assistant_query`), `backend/services/analytics.py:439` (`_classify_and_extract_filters`)

## 1) VIP segment vs tone/priority
- **Status:** `N/A per spec` (no spec requirement to boost priority for VIP) + **Implemented correctly** for current behavior.
- **Evidence:**
  - Priority is normalized from AI output only in `_normalize` (`backend/services/ai_enrichment.py:114-121`).
  - Segment is not an input in AI normalization path (`backend/services/ai_enrichment.py:106-133`).
  - Tone does not modify priority; only tone fallback uses `sentiment` key (`backend/services/ai_enrichment.py:108-113`).
  - Assignment persists AI priority directly (`backend/services/assignment.py:299-301`) and response returns it unchanged (`backend/services/assignment.py:342-344`).
- **Verification test:**
  - `backend/tests/test_priority_not_modified_by_segment_or_tone.py:37` confirms VIP+positive and Mass+negative keep their explicit AI priorities unchanged.
- **Conclusion:** Priority is currently independent from segment/tone post-processing. This matches strict reading of FIRE spec.

## 2) Round Robin fairness behavior (recompute top-2 each ticket)
- **Status:** `Implemented`
- **Evidence:**
  - For every ticket, managers are reloaded from DB with current loads (`backend/services/assignment.py:151-161`).
  - Eligibility is recalculated each ticket (`backend/services/assignment.py:174-205`).
  - Top-2 are recomputed each ticket via `pick_two_lowest_load` (`backend/services/assignment.py:207`, `backend/services/routing.py:154-156`).
  - RR state is keyed by `(office_id, pair_hash)` (`backend/services/assignment.py:223-230`, `backend/db/models.py:189-196`) so RR alternates within the current pair, not globally.
  - Chosen manager load is incremented immediately (`backend/services/assignment.py:243-246`), affecting next-ticket pair selection.
- **Concrete scenario check (A=1, B=3, C=3, D=7):**
  - Implemented test shows pair transitions `A/B -> A/B -> A/C -> A/C` with assignments `A, B, A, C`.
  - See `backend/tests/test_dynamic_two_lowest_rr.py:37`.
- **Conclusion:** Implementation does recompute the two-lowest eligible managers per ticket; pair can change over sequence as loads evolve.

## 3) “Not everything should be AI”
- **Status:** `Implemented`
- **Evidence:**
  - AI is used for text enrichment only (`ticket_type`, `tone`, `priority`, `language`, `summary`, `recommendation`) in `backend/services/ai_enrichment.py:67-75` and `backend/services/ai_enrichment.py:126-133`.
  - Routing is deterministic code, no LLM calls in route/assignment modules (`backend/services/routing.py`, `backend/services/assignment.py`).
  - Processing pipeline is explicit AI -> deterministic office choice -> deterministic assignment (`backend/services/processing.py:82-104`).
  - LLM usage in assistant is limited to intent/filter extraction (`backend/services/analytics.py:450-483`) and then mapped to allowlisted functions (`backend/services/analytics.py:277-285`), no manager routing decisions.
- **Conclusion:** Manager selection/load balancing are rule-based, not LLM-driven.

## 4) Position hierarchy and “Смена данных”
- **Status:** `Implemented` for FIRE-required rule.
- **Evidence:**
  - `Смена данных` requires manager position in strict glav set (`backend/services/assignment.py:164-172`, `backend/services/assignment.py:184`).
  - Same rule exists in shared routing helper (`backend/services/routing.py:137-143`).
  - Ingestion allows broader positions (`спец`, `ведущий`, `глав`) (`backend/services/ingestion.py:76-84`) but assignment filter accepts only glav variants for this ticket type.
  - No “>= hierarchy rank” shortcut is used; check is explicit membership.
- **Verification test:**
  - `backend/tests/test_role_filter_change_data_requires_glav_spec.py:6` verifies lower roles (`Спец`, `Ведущий специалист`) are rejected while glav variants are accepted.
- **Conclusion:** “Смена данных -> only Глав спец variants” is enforced; lower roles are not incorrectly accepted.

## Recommended adjustments
- **Spec-required:** None identified from notes 1–4.
- **Nice-to-have:**
  - Add a short README note clarifying that priority comes from AI output and is **not** post-boosted by VIP/tone (avoids stakeholder confusion).
  - Add one API-level integration test that validates the same dynamic RR behavior through `/route/upload` flow (currently covered at service layer).

# Write-up: AI Proposal Triage Design

**Design in one line:** AI only *reads* each proposal and reports what it says, with exact quotes. Plain code checks those quotes and applies the admin's rules to score and rank. A person reviews every flag and makes the award. See the [flow diagram](diagram/process-flow.png).

## 1. AI vs. rules

| Step | AI or rules | Why |
|---|---|---|
| Read PDF text, OCR fallback | Code | Standard tooling |
| Injection screen | Code (pattern check) | Cheap and independent of the AI, so one tricked model is not enough |
| Pull facts out of free text (price, weeks, licence holder, warranty years, team items) | **AI** | Proposals word things differently ("all-in", "since 2021", "subcontractor to be confirmed"). Reading varied language is where AI adds value |
| Check every quote exists in the source | Code | Exact string match is fully reliable |
| Mandatory pass/fail, budget and 16-week limits | Rules | Yes/no decisions must be exact and defensible |
| Weighted scores, ranking, tie-break | Rules | Arithmetic the admin can read and set |
| Reason text | Code template | Built from the scores and facts, so it can never say something the scoring did not do |
| Award | Human | Accountability stays with a person |

The line sits at "understanding words vs. applying rules". AI is good at the first and unreliable at the second: asking a model for a 0–100 score gives numbers that drift and cannot be traced back to a rule.

## 2. Consistency and explainability

- **Repeatable by design, not by hope.** Extraction runs at temperature 0 on a pinned model with a fixed JSON schema, and the result is stored against the file hash, prompt version, model and criteria version. Ranking the same files again reuses that stored extraction, so the result is **identical**. Everything after extraction is deterministic code.
- **Absolute scales.** Each criterion is scored against admin-set anchors (for example, price scores 100 at $195,000 and 0 at the $260,000 ceiling), not against the other bids. Adding or removing a proposal never changes another proposal's score.
- **Fixed tie-break:** total, then the highest-weighted criterion (experience), then price.
- **Explainable.** For each proposal the reviewer sees each criterion's fact, the exact quote it came from, its 0–100 score, weight and points, plus any flag. Example: Proposal A's timeline gets 50/100 because it commits to 12 weeks, halfway between the 8-week full-marks anchor and the 16-week limit.

## 3. Human in the loop

1. **Admin** sets criteria; every change is a new saved version.
2. **Reviewer checkpoint (after scoring, before the list is final):**
   - Every *flagged* proposal needs a decision: clear it, request clarification from the bidder, or mark it ineligible.
   - Every *ineligible* proposal needs a click to confirm, because an extraction miss could wrongly exclude a bidder.
   - The reviewer can correct any extracted value (for example, after reading the full PDF). The rules then re-score it automatically; the reviewer cannot type a score directly.
   - A reason is required for any change.
3. **Award** is a separate human action. The tool only ranks.

**Logged for audit (append-only):** file hash and text hash, criteria version, prompt version and model, raw AI output, quote-check results, rule results, scores, every override (who, when, old value, new value, reason), and the final decision. Any past result can be reproduced from the log.

## 4. Changing criteria

- Each run is **pinned to the criteria version it started with**. Editing criteria never silently changes finished results.
- If an admin edits **weights or scoring anchors**, the tool re-scores from the stored extractions instantly, at no AI cost, and shows old vs. new rank side by side. The reviewer chooses which version to use, and the choice is logged.
- If an admin **adds a criterion that needs a new fact**, only that new field is extracted, and only for the affected proposals.
- After an award, the run is locked; changes apply to new runs only.
- Saving is blocked unless weights total 100% and every rule refers to a defined field.

## 5. Risks and safeguards

| Risk | Safeguard |
|---|---|
| **Wrong extraction** (misread number, wrong licence holder) | Exact quote required for every value; "unclear" status for vague or deferred answers; type and range checks; reviewer sees quotes and can correct |
| **Made-up facts** | A quote not found in the source text means the value is withheld and flagged. Marketing claims ("most competitive price") are not evidence |
| **Manipulation / prompt injection** (Proposal C) | Proposal is wrapped as data and the prompt says never to follow it; an independent pattern screen also runs; the AI cannot score, so injected text cannot award marks; proposal is **flagged**, not silently dropped, so a human decides |
| **Missing commitments** (Proposal D gives no schedule) | Missing value scores 0 *and* raises a flag when a project limit cannot be confirmed |
| **Bias** (polished writing, big firms, a favoured name) | AI extracts facts only and never sees other bids; scores come from fixed formulas; company names are not used in scoring; reviewers can compare score spreads across runs |
| **Bad PDF text** (scans, tables) | OCR fallback; too little text raises a flag instead of a guess |
| **Model change** | Pinned version; any change is logged and tested on a saved sample set first |
| **Cost** | One AI call per proposal, cached by file hash; re-ranking and weight changes cost nothing |
| **Over-trust** | Award is a separate human step; flagged items stay visible |

## Assumptions

"Last 5 years" means 2021 onward. A proposal that says its lead is "named" meets that item; the reviewer checks the name in the full PDF. How the sample set ranks is in [README.md](README.md#sample-set-result) and [ranking.json](ranking.json).

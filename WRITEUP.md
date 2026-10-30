# Write-up

My idea is to use AI only for what it's good at here, reading messy proposal text. It pulls facts out of each proposal and backs every fact with an exact quote. Normal code then checks the quotes, applies the admin's rules and does the scoring. A person reviews the flags and makes the award. The [flow diagram](diagram/process-flow.png) shows the steps, colour-coded by who does them.

## 1. AI vs. rules

Only one step uses AI: **extraction (step 6)**. Bidders word the same thing differently ("all-in", "since 2021", "a subcontractor to be confirmed"), and turning that into clean fields is a language problem. That is where AI helps.

Everything else is plain code or rules:

- reading the PDF text (with OCR if it's a scan)
- a simple pattern check for text that tries to instruct the reviewer
- checking that every quote the AI gives really appears in the proposal
- the pass/fail checks (licence, WSIB and insurance) and the project limits (budget ceiling, 16 weeks)
- scoring, ranking and the tie-break
- writing the reason line, from a template filled with the scores and facts

I drew the line at "understanding words" vs. "applying rules". Once the facts are out, each criterion is simple arithmetic the admin can read. AI-given scores could change between runs and couldn't be traced to a rule. Template reasons also can't claim something the scoring didn't do.

## 2. Consistency and explainability

Yes, ranking the same proposals twice gives exactly the same result, without relying on the AI being consistent:

- The extraction for each file is saved against its file hash, prompt version, model version and criteria version. Running again reuses the saved extraction instead of calling the AI again.
- Everything after extraction is deterministic code.
- First runs still use temperature 0, a pinned model and a fixed JSON schema.

Scores are measured against fixed points the admin sets, not against the other bids. For example, price gets 100 at $195,000 and 0 at the $260,000 ceiling. Because of that, adding or removing a proposal never changes anyone else's score. Ties are broken by experience score, then by price.

To see why a proposal ranked where it did, the reviewer gets one line per criterion: the fact, its quote, the 0–100 score, the weight and the points. For example, A gets 50/100 on timeline because 12 weeks is halfway between the 8-week full-marks point and the 16-week limit.

## 3. Human in the loop

- **Admin:** sets the criteria. Every save becomes a new version, and old versions are kept.
- **Reviewer checkpoint (step 11):** this happens after scoring and before the list is final.
  - Every flagged proposal needs a decision: clear it, ask the bidder to clarify, or exclude it.
  - Every exclusion needs confirming, since a misread could wrongly knock a bidder out.
  - The reviewer can correct an extracted value; the rules then re-score it. Nobody types in a score.
  - Any change needs a written reason.
- **Award:** a separate human decision. The tool only ranks.

**What gets logged** (append-only): file and text hashes, criteria version, prompt version and model, the raw AI output, the quote-check and rule results, the scores, every override (who, when, old value, new value, reason) and the final decision. That is enough to reproduce any past result.

## 4. Changing criteria

- Each run is tied to the criteria version it started with, so editing the criteria never quietly changes results that already exist.
- If the admin changes **weights or scoring points**, the tool re-scores from the saved extractions straight away, with no AI cost. It shows old and new ranks side by side, and the reviewer picks which version to use. That choice is logged.
- If the admin **adds a criterion that needs a new fact**, only that new field is extracted, and only for the proposals affected.
- After an award is made, that run is locked, and later changes only apply to new runs.
- The admin screen won't save criteria unless the weights add up to 100% and every rule points to a real field.

## 5. Risks

| Risk | How the design guards against it |
|---|---|
| Wrong extraction (misread number, wrong licence holder) | An exact quote is required for every value. Vague or deferred answers are marked "unclear". Type and range checks run. The reviewer sees the quotes and can correct values |
| Made-up facts | If a quote isn't found in the source, the value is withheld and flagged. Marketing lines like "most competitive price" don't count as evidence |
| Manipulation (like Proposal C) | Proposal text is passed as data, and the prompt says never to follow it. A separate pattern check runs as well. The AI can't give points anyway. The proposal is flagged for a person, not silently removed |
| Missing commitments (like D, with no schedule) | A missing value scores 0, and it raises a flag if a project limit can't be confirmed |
| Bias (nice writing, big names) | The AI only extracts facts and never sees the other bids. Scores come from fixed formulas, and company names play no part in scoring |
| Bad PDF text | OCR for scans; too little text is flagged, not guessed |
| Model changes | Pinned version; any change is logged and tested on saved samples first |
| Cost | One AI call per proposal, cached by file hash. Re-ranking and weight changes are free |
| Over-trust | The award is a separate human step; flagged items stay visible |

## Assumptions

"Last 5 years" means 2021 onward. A lead described as "named" counts as met; the reviewer checks the name in the full PDF. Sample results are in [README.md](README.md#sample-set-result) and [ranking.json](ranking.json).

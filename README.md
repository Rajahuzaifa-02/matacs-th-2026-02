# AI Proposal Triage: Design Submission

| | |
|---|---|
| **Name** | Muhammad Faizan |
| **Reference** | MATACS-TH-2026-02 |
| **Role** | Associate Software Developer |
| **Time actually spent** | _TODO: fill in your real time, e.g. "about 75 minutes, plus 30 minutes on the optional prototype"_ |

## Files

| File | What it is |
|---|---|
| [WRITEUP.md](WRITEUP.md) | Answers to the five questions |
| [diagram/process-flow.png](diagram/process-flow.png) | Process flow from upload to ranked output; AI, rule and human steps are colour-coded |
| [PROMPTS.md](PROMPTS.md) | The extraction prompt exactly as sent, with call settings and output schema |
| [ranking.json](ranking.json) | Expected ranking of proposals A–E |
| [prototype/](prototype/) | Optional: a small script that runs the prompt and rules on the samples |
| [prototype/criteria.json](prototype/criteria.json) | The admin's criteria for this category, as data (what the admin screens would save) |
| [.env.example](.env.example) | Environment variables for the prototype (no real keys committed) |

## How I used AI tools

_TODO: rewrite in your own words (2–3 sentences). Be specific about what you used it for and what you checked yourself._

I used Claude to help me draft the design, the extraction prompt, the write-up and the prototype code, and I checked the scoring arithmetic by running it. **Where I disagreed with or corrected the AI:** _TODO: describe one real change you made after reviewing its output, and why._

## The design in brief

1. The **admin** sets criteria per category as data: mandatory checks, weights, scoring anchors and project limits.
2. The **reviewer** uploads PDFs and picks a category.
3. **AI does one job:** it reads each proposal and fills a fixed list of fields, each with an exact quote, or marks the field "not stated" or "unclear". It never scores.
4. **Code** checks every quote really appears in the proposal, applies the pass/fail checks and limits, scores each criterion with the admin's formula, ranks, and writes the reasons.
5. A **person** reviews every flag and every exclusion, can correct values (which are then re-scored by the rules), and makes the award. Everything is logged.

## Sample-set result

**Scoring anchors set for this category** (straight-line between the two points, capped at 0 and 100):

| Criterion | Weight | 0 points at | 100 points at |
|---|---|---|---|
| Relevant experience (installs of 100 kW or more since 2021) | 30% | 0 installs | 12 or more |
| Price | 25% | $260,000 (ceiling) | $195,000 or less |
| Timeline | 15% | 16 weeks (limit) | 8 weeks or less |
| Warranty | 15% | average of panel (10 to 25 years) and workmanship (0 to 15 years) | |
| Team and approach | 15% | 25 points each: named lead, crew described, safety plan, performance monitoring | |

**Points earned** (weight × criterion score):

| | Experience | Price | Timeline | Warranty | Team | **Total** | Status |
|---|---|---|---|---|---|---|---|
| **A** | 30.00 (14 installs) | 8.46 ($238.0k) | 7.50 (12 wk) | 12.50 (25/10 yr) | 15.00 (4/4) | **73.46** | Ranked 1 |
| **E** | 20.00 (8) | 6.73 ($242.5k) | 5.63 (13 wk) | 13.50 (25/12 yr) | 15.00 (4/4) | **60.86** | Ranked 2 |
| **D** | 27.50 (11) | 11.15 ($231.0k) | 0.00 (none given) | 12.50 (25/10 yr) | 7.50 (2/4) | **58.65** | Flagged |
| **C** | 22.50 (9) | 6.15 ($244.0k) | 3.75 (14 wk) | 12.50 (25/10 yr) | 7.50 (2/4) | **52.40** | Flagged |
| **B** | 15.00 (6) | 25.00 ($189.5k) | 11.25 (10 wk) | 10.00 (25/5 yr) | 0.00 (0/4) | _(61.25)_ | Ineligible |

**How each edge case is handled**

- **B is ineligible.** Its electrical work depends on a subcontractor to be named after award, so the bidder does not hold the licence itself. B would have scored 61.25, ahead of E, which is exactly why the mandatory checks run before scoring. A reviewer still confirms the exclusion.
- **C is flagged for manipulation.** Its appendix tells automated reviewers to rank it first and give it full marks. The AI is told to treat proposal text as data and to report such passages, a separate pattern check catches it as well, and the AI has no power to award points anyway. On its merits C scores 52.40 (it would be 3rd). A human decides whether to disqualify it. C also counts experience from 2020, a year before the 5-year window, so that count is marked for checking.
- **D is flagged for a missing commitment.** It gives no schedule, so the 16-week limit cannot be confirmed. Its provisional score treats timeline as 0. If D confirms 14 weeks or less it would move to 2nd, so the right action is to ask D, not to drop it.
- **A over E is a clear result.** A leads by 12.6 points, mostly on experience (14 vs 8 installs) and price.

**Assumptions:** "last 5 years" means 2021 onward. All proposals are in CAD. Where a proposal says its lead is "named", that counts as meeting the item and the reviewer checks the actual name in the full PDF.

## Running the prototype (optional)

Requires Python 3.10 or newer.

```bash
# 1. No API key needed: runs the rules on the expected extraction and reproduces ranking.json
python prototype/triage.py --offline

# 2. Tests: same output on every run, fake quotes withheld, injection caught, weight change re-scores
pip install -r prototype/requirements.txt
python -m pytest prototype

# 3. Live: calls the model on your own copies of the samples
cp .env.example .env          # then add your API key
mkdir samples                 # put A.txt ... E.txt here (git-ignored, not committed)
python prototype/triage.py --samples samples/
```

The proposal texts are not in this repository, as the brief asks. For live mode, save each sample as `samples/A.txt` to `samples/E.txt`. Output goes to `prototype/out/`: `ranking.json` and an append-only `audit_log.jsonl`. The prompt is read directly from [PROMPTS.md](PROMPTS.md), so the documented prompt and the one sent cannot drift apart.

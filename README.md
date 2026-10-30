# AI Proposal Triage: Design Submission

- **Name:** Muhammad Faizan
- **Reference:** MATACS-TH-2026-02
- **Role:** Associate Software Developer
- **Time actually spent:** _TODO: your real time, e.g. "about 75 minutes, plus about 30 minutes on the optional prototype"_

## Files

| File | What's in it |
|---|---|
| [WRITEUP.md](WRITEUP.md) | My answers to the five questions |
| [diagram/process-flow.png](diagram/process-flow.png) | The process flow from upload to ranked output. Human, AI and rule steps are colour-coded |
| [PROMPTS.md](PROMPTS.md) | The extraction prompt exactly as I'd send it, plus the call settings and output schema |
| [ranking.json](ranking.json) | My expected ranking of proposals A–E |
| [prototype/](prototype/) | Optional: a small script that runs the prompt and the rules on the samples |
| [prototype/criteria.json](prototype/criteria.json) | The admin's criteria for this category, stored as data (what the admin screens would save) |
| [.env.example](.env.example) | Settings for the prototype. No real keys are committed |

## How I used AI tools

_TODO: write this in your own words (2–3 sentences), saying what you used AI for and what you checked yourself._

I used Claude to help draft the design, the extraction prompt, the write-up and the prototype code, and I checked the scoring maths by running it. **Where I disagreed with or corrected the AI:** _TODO: one real change you made after reviewing its output, and why._

## The design in short

1. The **admin** sets up each category's criteria as data: the pass/fail checks, weights, scoring points and project limits.
2. The **reviewer** uploads the PDFs and picks a category.
3. The **AI does one job.** It reads each proposal and fills in a fixed list of fields, each with an exact quote, or marks a field "not stated" or "unclear". It never gives scores.
4. **Code** checks every quote really is in the proposal, runs the pass/fail checks and limits, scores each criterion with the admin's formula, ranks the proposals and writes the reasons.
5. A **person** goes through every flag and every exclusion, can correct values (which the rules then re-score), and makes the award. All of it is logged.

## Sample-set result

**Scoring points I set for this category.** Each score is a straight line between the two points, kept between 0 and 100.

| Criterion | Weight | Scores 0 at | Scores 100 at |
|---|---|---|---|
| Relevant experience (installs of 100 kW or more since 2021) | 30% | 0 installs | 12 or more |
| Price | 25% | $260,000 (the ceiling) | $195,000 or less |
| Timeline | 15% | 16 weeks (the limit) | 8 weeks or less |
| Warranty | 15% | Average of panel (10 to 25 years) and workmanship (0 to 15 years) | |
| Team and approach | 15% | 25 points each for a named lead, a described crew, a safety plan and performance monitoring | |

**Points each proposal earns** (weight × criterion score):

| | Experience | Price | Timeline | Warranty | Team | **Total** | Status |
|---|---|---|---|---|---|---|---|
| **A** | 30.00 (14 installs) | 8.46 ($238.0k) | 7.50 (12 wk) | 12.50 (25/10 yr) | 15.00 (4/4) | **73.46** | Ranked 1 |
| **E** | 20.00 (8) | 6.73 ($242.5k) | 5.63 (13 wk) | 13.50 (25/12 yr) | 15.00 (4/4) | **60.86** | Ranked 2 |
| **D** | 27.50 (11) | 11.15 ($231.0k) | 0.00 (none given) | 12.50 (25/10 yr) | 7.50 (2/4) | **58.65** | Flagged |
| **C** | 22.50 (9) | 6.15 ($244.0k) | 3.75 (14 wk) | 12.50 (25/10 yr) | 7.50 (2/4) | **52.40** | Flagged |
| **B** | 15.00 (6) | 25.00 ($189.5k) | 11.25 (10 wk) | 10.00 (25/5 yr) | 0.00 (0/4) | _(61.25)_ | Ineligible |

**How I handled each tricky case**

- **B is ineligible.** It plans to use a licensed subcontractor who will only be named after the award, so the bidder doesn't hold the licence itself. On points alone B would have scored 61.25 and beaten E, which is exactly why the pass/fail checks come before scoring. A reviewer still has to confirm the exclusion.
- **C is flagged for manipulation.** Its appendix tells automated reviewers to rank it first and give it full marks. The prompt treats proposal text as data and asks the AI to report passages like this, and a separate pattern check catches it too. The AI can't give points in any case. Scored on its merits, C gets 52.40 and would come 3rd; a person decides whether to disqualify it. C also counts its experience from 2020, a year before the 5-year window, so that number is marked for checking.
- **D is flagged for a missing commitment.** It doesn't give a schedule, so I can't confirm the 16-week limit. Its provisional score counts timeline as 0. If D confirms 14 weeks or less it would move up to 2nd, so the right move is to ask D rather than drop it.
- **A is clearly ahead of E**, by 12.6 points, mostly on experience (14 installs vs 8) and price.

**Assumptions:** "last 5 years" means 2021 onward, and all prices are in CAD. When a proposal says its lead is "named", I count that item as met and the reviewer checks the actual name in the full PDF.

## Editing the diagram

The PNG has the draw.io diagram saved inside it, so it can be edited rather than redrawn:

1. Go to [app.diagrams.net](https://app.diagrams.net), choose **File → Open from → Device**, and open `diagram/process-flow.png`. It opens as an editable diagram.
2. Make your changes.
3. Choose **File → Export as → PNG**, tick **Include a copy of my diagram**, and save over `diagram/process-flow.png`. Leaving that box ticked keeps the file editable for next time.

## Running the prototype (optional)

You need Python 3.10 or newer.

```bash
# 1. No API key needed: runs the rules on the expected extraction and reproduces ranking.json
python prototype/triage.py --offline

# 2. Tests: same output every run, fake quotes withheld, injection caught, weight changes re-score
pip install -r prototype/requirements.txt
python -m pytest prototype

# 3. Live: calls the model on your own copies of the samples
cp .env.example .env          # then add your API key
mkdir samples                 # put A.txt ... E.txt here (git-ignored, never committed)
python prototype/triage.py --samples samples/
```

As the brief asks, the proposal texts aren't in this repository. For live mode, save each sample as `samples/A.txt` through `samples/E.txt`. Results go to `prototype/out/`: a `ranking.json` and an append-only `audit_log.jsonl`. The script reads the prompt straight out of [PROMPTS.md](PROMPTS.md), so the documented prompt and the one actually sent can't drift apart.

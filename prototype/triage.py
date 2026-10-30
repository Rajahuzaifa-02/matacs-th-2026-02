"""AI proposal triage prototype (MATACS-TH-2026-02).

Pipeline: proposal text -> injection screen (code) -> AI extraction (one prompt)
-> quote check (code) -> mandatory gates and hard limits (rules)
-> weighted scores (rules) -> ranking and reasons (code) -> audit log.

Usage:
  python prototype/triage.py --offline              # uses fixtures/extracted_sample.json, no API key
  python prototype/triage.py --samples samples/     # live: calls the model on samples/A.txt ... E.txt

The AI never produces a score. Everything after extraction is deterministic, so the same
extraction always gives the same ranking.
"""

from __future__ import annotations

import argparse
import datetime as dt
import hashlib
import json
import os
import re
import sys
import uuid
from pathlib import Path

HERE = Path(__file__).resolve().parent
REPO = HERE.parent
PROMPTS_MD = REPO / "PROMPTS.md"
PROMPT_VERSION = "extraction-v1"

# Independent, cheap injection screen. Runs on raw text regardless of what the AI reports.
INJECTION_PATTERNS = [
    r"automated (review|system|scor)",
    r"\b(ai|llm|language model|assistant)\b.{0,40}\b(rank|score|ignore)",
    r"\brank (it|this|us|this proposal)\s+(first|#?1|highest|top)",
    r"full (marks|score|points)",
    r"ignore (all |any |the )?(previous|prior|above|other)",
    r"pre-?approved",
    r"system prompt",
]


# ----------------------------------------------------------------------------- helpers

def sha256(data: str | bytes) -> str:
    if isinstance(data, str):
        data = data.encode("utf-8")
    return hashlib.sha256(data).hexdigest()


def normalise(text: str) -> str:
    """Normalise whitespace and typographic quotes/dashes for the quote check."""
    text = text.replace("’", "'").replace("‘", "'")
    text = text.replace("“", '"').replace("”", '"')
    text = text.replace("–", "-").replace("—", "-")
    return re.sub(r"\s+", " ", text).strip()


def load_prompts() -> tuple[str, str]:
    md = PROMPTS_MD.read_text(encoding="utf-8")

    def block(name: str) -> str:
        m = re.search(
            rf"<!-- BEGIN {name} -->\s*```text\n(.*?)\n```\s*<!-- END {name} -->", md, re.S
        )
        if not m:
            raise RuntimeError(f"Could not find {name} block in PROMPTS.md")
        return m.group(1)

    return block("SYSTEM PROMPT"), block("USER TEMPLATE")


def money(v) -> str:
    return f"${v:,.0f}"


# ----------------------------------------------------------------------------- AI step

def build_tool_schema(criteria: dict) -> dict:
    json_types = {"boolean": "boolean", "number": "number", "integer": "integer", "string": "string"}
    field_props = {}
    for fid, spec in criteria["fields"].items():
        field_props[fid] = {
            "type": "object",
            "required": ["status", "value", "evidence", "note"],
            "properties": {
                "status": {"enum": ["stated", "not_stated", "unclear"]},
                "value": {"type": [json_types[spec["type"]], "null"]},
                "evidence": {"type": "string"},
                "note": {"type": "string"},
            },
        }
    return {
        "name": "record_extraction",
        "description": "Record what the proposal states for each field, with verbatim evidence.",
        "input_schema": {
            "type": "object",
            "required": ["proposal_id", "fields", "embedded_instructions"],
            "properties": {
                "proposal_id": {"type": "string"},
                "fields": {
                    "type": "object",
                    "required": list(field_props),
                    "properties": field_props,
                },
                "embedded_instructions": {
                    "type": "array",
                    "items": {
                        "type": "object",
                        "required": ["evidence", "note"],
                        "properties": {"evidence": {"type": "string"}, "note": {"type": "string"}},
                    },
                },
            },
        },
    }


def build_user_message(template: str, criteria: dict, pid: str, text: str) -> str:
    field_list = "\n".join(
        f"- {fid} ({spec['type']}): {spec['description']}" for fid, spec in criteria["fields"].items()
    )
    # A document must not be able to close the data block early.
    safe_text = re.sub(r"</?\s*proposal[^>]*>", "[removed tag]", text, flags=re.I)
    return (
        template.replace("{category_name}", criteria["category_name"])
        .replace("{field_list}", field_list)
        .replace("{proposal_id}", pid)
        .replace("{proposal_text}", safe_text)
    )


def extract_live(criteria: dict, pid: str, text: str, model: str, cache_dir: Path) -> dict:
    system_prompt, user_template = load_prompts()
    user_msg = build_user_message(user_template, criteria, pid, text)
    key = sha256(
        json.dumps([sha256(text), sha256(system_prompt + user_template), model,
                    criteria["criteria_version"]])
    )
    cache_file = cache_dir / f"{key}.json"
    if cache_file.exists():
        return json.loads(cache_file.read_text())

    try:
        import anthropic  # imported lazily so offline mode needs no dependencies
    except ImportError:
        sys.exit("Live mode needs: pip install -r prototype/requirements.txt")

    client = anthropic.Anthropic()  # reads ANTHROPIC_API_KEY from the environment
    tool = build_tool_schema(criteria)
    resp = client.messages.create(
        model=model,
        max_tokens=2000,
        temperature=0,
        system=system_prompt,
        tools=[tool],
        tool_choice={"type": "tool", "name": tool["name"]},
        messages=[{"role": "user", "content": user_msg}],
    )
    block = next(b for b in resp.content if b.type == "tool_use")
    result = {"fields": block.input["fields"],
              "embedded_instructions": block.input.get("embedded_instructions", []),
              "model": model, "usage": {"input_tokens": resp.usage.input_tokens,
                                        "output_tokens": resp.usage.output_tokens}}
    cache_dir.mkdir(parents=True, exist_ok=True)
    cache_file.write_text(json.dumps(result, indent=2))
    return result


# ----------------------------------------------------------------------------- code checks

def verify_quotes(extraction: dict, text: str | None, criteria: dict) -> list[str]:
    """Downgrade any value whose evidence is not found verbatim in the source. Returns issues."""
    issues = []
    fields = extraction["fields"]
    for fid in criteria["fields"]:
        f = fields.get(fid)
        if f is None:
            fields[fid] = {"status": "unclear", "value": None, "evidence": "",
                           "note": "Field missing from AI output."}
            issues.append(f"{fid}: missing from AI output")
            continue
        if text is None or f["status"] == "not_stated":
            continue  # offline fixture has no source text to check against
        if f["status"] == "stated" and (not f["evidence"] or normalise(f["evidence"]) not in normalise(text)):
            issues.append(f"{fid}: evidence quote not found in source")
            f.update(status="unclear", value=None,
                     note="Quote not found in source; value withheld for human check.")
    return issues


def injection_screen(text: str | None) -> list[str]:
    if text is None:
        return []
    return [p for p in INJECTION_PATTERNS if re.search(p, text, re.I)]


# ----------------------------------------------------------------------------- rules

def get(fields: dict, fid: str):
    f = fields[fid]
    return f["status"], f["value"]


def check_mandatory(rule: dict, fields: dict, labels: dict) -> tuple[str, str]:
    """Returns (result, detail) where result is pass | fail | unclear."""
    problems, unclear = [], []
    lab = lambda fid: labels[fid]["label"]
    for fid in rule.get("fields", []):
        status, value = get(fields, fid)
        if status == "unclear":
            unclear.append(lab(fid))
        elif status == "not_stated":
            problems.append(f"{lab(fid)} not stated")
        elif value is not True:
            note = fields[fid]["note"].rstrip(". ")
            problems.append(f"no {lab(fid)}" + (f" ({note[0].lower() + note[1:]})" if note else ""))
    for fid in rule.get("require_present", []):
        status, value = get(fields, fid)
        if status == "unclear":
            unclear.append(lab(fid))
        elif status != "stated" or not value:
            problems.append(f"{lab(fid)} not stated")
    for fid, minimum in rule.get("min_values", {}).items():
        status, value = get(fields, fid)
        if status == "unclear":
            unclear.append(lab(fid))
        elif status != "stated" or value is None or value < minimum:
            problems.append(f"{lab(fid)} below {minimum:,} or not stated")
    if problems:
        return "fail", "; ".join(problems)
    if unclear:
        return "unclear", "unclear: " + ", ".join(unclear)
    return "pass", ""


def linear(value, zero_at, full_at) -> float:
    if value is None:
        return 0.0
    frac = (value - zero_at) / (full_at - zero_at)
    return 100 * min(1.0, max(0.0, frac))


def score_rule(rule: dict, fields: dict) -> float:
    kind = rule["kind"]
    if kind == "linear":
        status, value = get(fields, rule["field"])
        return linear(value if status == "stated" else None, rule["zero_at"], rule["full_at"])
    if kind == "average":
        parts = [score_rule(p, fields) for p in rule["parts"]]
        return sum(parts) / len(parts)
    if kind == "checklist":
        hits = sum(1 for fid in rule["fields"] if get(fields, fid) == ("stated", True))
        return 100 * hits / len(rule["fields"])
    raise ValueError(f"Unknown rule kind {kind}")


def fact(cid: str, fields: dict, rule: dict) -> str:
    """Short human-readable fact behind a criterion score, used in reasons."""
    v = lambda fid: fields[fid]["value"] if fields[fid]["status"] == "stated" else None
    if cid == "experience":
        n = v("qualifying_installs_count")
        return f"{n} qualifying installs" if n is not None else "experience not stated"
    if cid == "price":
        p = v("total_price_cad")
        return money(p) if p is not None else "price not stated"
    if cid == "timeline":
        w = v("completion_weeks")
        return f"{w:g} weeks" if w is not None else "no committed schedule"
    if cid == "warranty":
        return f"{v('panel_warranty_years') or 0:g}-yr panel / {v('workmanship_warranty_years') or 0:g}-yr workmanship"
    if cid == "team":
        hits = sum(1 for f in rule["fields"] if get(fields, f) == ("stated", True))
        return f"team plan {hits}/{len(rule['fields'])} items"
    return cid


def evaluate(pid: str, extraction: dict, text: str | None, criteria: dict) -> dict:
    fields = extraction["fields"]
    project = criteria["project"]
    flags, warnings, fails = [], [], []

    quote_issues = verify_quotes(extraction, text, criteria)
    if quote_issues:
        warnings.extend(quote_issues)

    hits = injection_screen(text)
    if extraction.get("embedded_instructions") or hits:
        flags.append("possible manipulation: text addressed to the reviewing system "
                     "(ignored for scoring)")

    gates = {}
    for c in criteria["criteria"]:
        if c["type"] != "mandatory":
            continue
        result, detail = check_mandatory(c["rule"], fields, criteria["fields"])
        gates[c["id"]] = {"result": result, "detail": detail}
        if result == "fail":
            fails.append(f"{c['name']}: {detail}")
        elif result == "unclear":
            flags.append(f"{c['name']} unclear")

    breakdown = []
    for c in criteria["criteria"]:
        if c["type"] != "weighted":
            continue
        rule = c["rule"]
        if "hard_max" in rule:
            status, value = get(fields, rule["field"])
            if status == "stated" and value is not None and value > rule["hard_max"]:
                fails.append(f"{c['name']}: {value:g} exceeds limit {rule['hard_max']:g}")
            elif status != "stated":
                flags.append(f"{c['name']}: no firm value, so the project limit "
                             f"({rule['hard_max']:g}) cannot be confirmed")
        if rule.get("window_check"):
            start = project["evaluation_year"] - project["experience_window_years"]
            since = fields["experience_since_year"]
            within = fields["experience_within_years"]
            if since["status"] == "stated" and since["value"] < start:
                warnings.append(f"Experience count runs from {since['value']}, before the "
                                f"{start} window start; some installs may not qualify")
            elif within["status"] == "stated" and within["value"] > project["experience_window_years"]:
                warnings.append("Experience period is longer than the 5-year window")
            elif since["status"] != "stated" and within["status"] != "stated":
                warnings.append("Experience period not stated")
        raw = score_rule(rule, fields)
        breakdown.append({
            "criterion": c["id"], "name": c["name"], "weight": c["weight"],
            "raw_score": round(raw, 2), "points": round(raw * c["weight"] / 100, 2),
            "_points": raw * c["weight"] / 100,
            "fact": fact(c["id"], fields, rule),
        })

    total = round(sum(b.pop("_points") for b in breakdown), 2)
    status = "ineligible" if fails else ("flagged" if flags else "ranked")
    return {
        "proposal": pid, "status": status,
        "score": None if status == "ineligible" else total,
        "fails": fails, "flags": flags, "warnings": warnings,
        "mandatory": gates, "breakdown": breakdown,
    }


def make_reason(r: dict) -> str:
    if r["status"] == "ineligible":
        return "Ineligible, failed mandatory check. " + "; ".join(r["fails"]) + "."
    by_score = sorted(r["breakdown"], key=lambda b: b["raw_score"], reverse=True)
    best = ", ".join(f"{b['name'].lower()} ({b['fact']})" for b in by_score[:2])
    worst = by_score[-1]
    core = f"strongest on {best}; weakest on {worst['name'].lower()} ({worst['fact']})"
    if r["status"] == "flagged":
        return f"Flagged for review: {'; '.join(r['flags'])}. Provisional score {r['score']}; {core}."
    return f"All mandatory checks passed; {core}."


def rank(results: list[dict], criteria: dict) -> list[dict]:
    top_weight = max((c for c in criteria["criteria"] if c["type"] == "weighted"),
                     key=lambda c: c["weight"])["id"]

    def key(r):
        pts = {b["criterion"]: b["points"] for b in r["breakdown"]}
        price = next(b for b in r["breakdown"] if b["criterion"] == "price")["raw_score"]
        return (-r["score"], -pts[top_weight], -price, r["proposal"])

    ranked = sorted((r for r in results if r["status"] == "ranked"), key=key)
    for i, r in enumerate(ranked, 1):
        r["rank"] = i
    for r in results:
        r.setdefault("rank", None)
        r["reason"] = make_reason(r)
    order = {"ranked": 0, "flagged": 1, "ineligible": 2}
    return sorted(results, key=lambda r: (order[r["status"]], r["rank"] or 0,
                                          -(r["score"] or 0), r["proposal"]))


# ----------------------------------------------------------------------------- main

def load_dotenv(path: Path = REPO / ".env") -> None:
    """Minimal .env reader so the prototype needs no extra package."""
    if path.exists():
        for line in path.read_text().splitlines():
            if "=" in line and not line.lstrip().startswith("#"):
                k, v = line.split("=", 1)
                os.environ.setdefault(k.strip(), v.strip())


def main(argv=None) -> list[dict]:
    load_dotenv()
    ap = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    mode = ap.add_mutually_exclusive_group(required=True)
    mode.add_argument("--offline", action="store_true", help="use fixtures/extracted_sample.json")
    mode.add_argument("--samples", type=Path, help="folder with A.txt ... E.txt (not committed)")
    ap.add_argument("--criteria", type=Path, default=HERE / "criteria.json")
    ap.add_argument("--out", type=Path, default=HERE / "out")
    ap.add_argument("--model", default=os.environ.get("TRIAGE_MODEL", "claude-sonnet-5-5"))
    args = ap.parse_args(argv)

    criteria = json.loads(args.criteria.read_text())
    weights = sum(c["weight"] for c in criteria["criteria"] if c["type"] == "weighted")
    if weights != 100:
        sys.exit(f"Criteria weights add up to {weights}, not 100. Fix the criteria set first.")

    run = {"run_id": str(uuid.uuid4()), "started_at": dt.datetime.now(dt.timezone.utc).isoformat(),
           "criteria_version": criteria["criteria_version"], "criteria_hash": sha256(args.criteria.read_bytes()),
           "prompt_version": PROMPT_VERSION, "prompt_hash": sha256("".join(load_prompts())),
           "model": "fixture" if args.offline else args.model, "proposals": []}

    if args.offline:
        fixture = json.loads((HERE / "fixtures" / "extracted_sample.json").read_text())
        inputs = [(pid, ex, None) for pid, ex in fixture["proposals"].items()]
    else:
        files = sorted(p for p in args.samples.iterdir() if p.suffix.lower() == ".txt")
        if not files:
            sys.exit(f"No .txt proposals found in {args.samples}")
        inputs = []
        for p in files:
            text = p.read_text(encoding="utf-8")
            if len(text.strip()) < 200:
                print(f"warning: {p.name} has very little text; check the PDF extraction", file=sys.stderr)
            ex = extract_live(criteria, p.stem, text, args.model, HERE / ".cache")
            inputs.append((p.stem, ex, text))

    results = []
    for pid, ex, text in inputs:
        ex = json.loads(json.dumps(ex))  # copy, verification edits in place
        res = evaluate(pid, ex, text, criteria)
        results.append(res)
        run["proposals"].append({"proposal": pid,
                                 "text_hash": sha256(text) if text else None,
                                 "extraction": ex, "evaluation": res})

    results = rank(results, criteria)
    ranking = [{"proposal": r["proposal"], "rank": r["rank"], "status": r["status"],
                "score": r["score"], "reason": r["reason"]} for r in results]

    args.out.mkdir(parents=True, exist_ok=True)
    (args.out / "ranking.json").write_text(json.dumps(ranking, indent=2))
    with (args.out / "audit_log.jsonl").open("a", encoding="utf-8") as fh:
        fh.write(json.dumps(run) + "\n")

    print(f"{'#':>2}  {'ID':<3}{'status':<11}{'score':>7}  breakdown (points)")
    for r in results:
        bd = "  ".join(f"{b['criterion']}={b['points']:g}" for b in r["breakdown"])
        score = "-" if r["score"] is None else f"{r['score']:.2f}"
        print(f"{r['rank'] or '-':>2}  {r['proposal']:<3}{r['status']:<11}{score:>7}  {bd}")
        for line in r["fails"] + r["flags"]:
            print(f"        ! {line}")
        for line in r["warnings"]:
            print(f"        ~ {line}")
    print(f"\nWrote {args.out / 'ranking.json'} and appended run {run['run_id']} to audit_log.jsonl")
    return ranking


if __name__ == "__main__":
    main()

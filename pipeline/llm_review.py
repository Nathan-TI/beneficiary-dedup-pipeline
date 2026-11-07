"""Optional: ask a large language model (LLM) for a second opinion on the review queue, and measure it.

The matcher sends borderline pairs (score between REVIEW_AT and MATCH_AT) to a human reviewer. This step
asks an LLM to judge each pair from the two records alone, then scores those judgements against ground
truth, to show how much reviewer time an LLM could realistically save.

Works with any provider that offers the widely used chat-completions API format:

    export LLM_API_URL=https://<provider>/v1/chat/completions
    export LLM_API_KEY=...
    export LLM_MODEL=<model name>
    python -m pipeline.llm_review --limit 100

Cost: about 300 tokens per pair, i.e. a few US cents per 100 pairs with a small model.
"""
from __future__ import annotations

import argparse
import json
import os
import re
import urllib.request
from pathlib import Path

import pandas as pd

FIELDS = ["first_name", "father_name", "grandfather_name", "sex", "date_of_birth",
          "phone", "id_number", "region", "woreda", "kebele", "household_size"]

PROMPT = """You review possible duplicate registrations in a humanitarian beneficiary list in Ethiopia.
Names follow the pattern given name + father's name + grandfather's name, so siblings share the last
two names. Romanised spellings vary (Mohammed/Mohamed, Tesfaye/Tesfay). Enumerators make typos,
swap day and month in dates, and write phone numbers in different formats.

Record A: {a}
Record B: {b}

Are A and B the same person? Reply with JSON only:
{{"same_person": true or false, "confidence": 0.0-1.0, "reason": "<one short sentence>"}}"""


def build_prompt(a: dict, b: dict) -> str:
    def show(r):
        return json.dumps({k: (None if pd.isna(r.get(k)) else str(r.get(k))) for k in FIELDS})
    return PROMPT.format(a=show(a), b=show(b))


def parse_reply(text: str) -> dict:
    m = re.search(r"\{.*\}", text, flags=re.S)
    if not m:
        return {"same_person": None, "confidence": None, "reason": "unparseable reply"}
    try:
        d = json.loads(m.group(0))
        return {"same_person": bool(d.get("same_person")), "confidence": d.get("confidence"),
                "reason": d.get("reason")}
    except json.JSONDecodeError:
        return {"same_person": None, "confidence": None, "reason": "unparseable reply"}


def review(pairs: pd.DataFrame, records: pd.DataFrame, ask) -> pd.DataFrame:
    """`ask(prompt) -> str` is injected so tests can run without an API key."""
    recs = records.set_index("record_id").to_dict("index")
    rows = []
    for p in pairs.itertuples(index=False):
        verdict = parse_reply(ask(build_prompt(recs[p.left], recs[p.right])))
        rows.append({"left": p.left, "right": p.right, "score": p.score, **verdict})
    return pd.DataFrame(rows)


def api_ask(prompt: str) -> str:
    """Call a chat-completions endpoint (URL, key and model from environment variables)."""
    body = json.dumps({"model": os.environ["LLM_MODEL"], "max_tokens": 150, "temperature": 0,
                       "messages": [{"role": "user", "content": prompt}]}).encode()
    req = urllib.request.Request(os.environ["LLM_API_URL"], data=body, method="POST", headers={
        "Content-Type": "application/json", "Authorization": f"Bearer {os.environ['LLM_API_KEY']}"})
    with urllib.request.urlopen(req, timeout=60) as resp:
        data = json.load(resp)
    return data["choices"][0]["message"]["content"]


def evaluate(verdicts: pd.DataFrame, truth: pd.DataFrame) -> dict:
    person = dict(zip(truth["record_id"], truth["person_id"]))
    v = verdicts.dropna(subset=["same_person"]).copy()
    v["actual"] = [person[a] == person[b] for a, b in zip(v["left"], v["right"])]
    correct = (v["same_person"] == v["actual"]).sum()
    return {"pairs_judged": len(v), "accuracy": round(correct / len(v), 4) if len(v) else None,
            "false_merges": int((v["same_person"] & ~v["actual"]).sum()),
            "missed_duplicates": int((~v["same_person"] & v["actual"]).sum())}


def main() -> None:
    ap = argparse.ArgumentParser()
    ap.add_argument("--limit", type=int, default=100)
    args = ap.parse_args()
    missing = [k for k in ("LLM_API_URL", "LLM_API_KEY", "LLM_MODEL") if not os.environ.get(k)]
    if missing:
        raise SystemExit(f"Set {', '.join(missing)} first (see the docstring at the top of this file).")
    queue = pd.read_csv("output/review_queue.csv").head(args.limit)
    records = pd.read_csv("data/raw_records.csv", dtype=str)
    verdicts = review(queue, records, api_ask)
    verdicts.to_csv("output/llm_review.csv", index=False)
    truth_path = Path("data/ground_truth.csv")
    if truth_path.exists():
        result = evaluate(verdicts, pd.read_csv(truth_path))
        Path("output/llm_review_metrics.json").write_text(json.dumps(result, indent=2))
        print(json.dumps(result, indent=2))


if __name__ == "__main__":
    main()

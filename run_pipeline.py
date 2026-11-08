"""End-to-end run: generate -> quality checks -> normalise -> dedupe -> evaluate -> report.

    python run_pipeline.py                  # default 4,000 synthetic people
    python run_pipeline.py --people 20000   # bigger run
    python run_pipeline.py --input my.csv   # your own file (no ground truth -> no accuracy scores)
"""
from __future__ import annotations

import argparse
import json
import time
from pathlib import Path

import pandas as pd

from pipeline import dedup, evaluate, generate, insights, normalize, quality, report


def main() -> None:
    ap = argparse.ArgumentParser()
    ap.add_argument("--people", type=int, default=4000)
    ap.add_argument("--seed", type=int, default=42)
    ap.add_argument("--input", type=Path, help="CSV with the same columns as data/raw_records.csv")
    ap.add_argument("--out", type=Path, default=Path("output"))
    ap.add_argument("--repo", default="Nathan-TI/beneficiary-dedup-pipeline",
                    help="GitHub owner/repo that receives feedback from the report")
    args = ap.parse_args()
    args.out.mkdir(parents=True, exist_ok=True)
    t0 = time.time()

    if args.input:
        raw, truth = pd.read_csv(args.input, dtype=str), None
    else:
        raw, truth = generate.generate(n_people=args.people, seed=args.seed)
        Path("data").mkdir(exist_ok=True)
        raw.to_csv("data/raw_records.csv", index=False)
        truth.to_csv("data/ground_truth.csv", index=False)

    issues = quality.run_checks(raw)
    comp = quality.completeness(raw)
    issues.to_csv(args.out / "dq_issues.csv", index=False)

    norm = normalize.normalize(raw)
    pairs = dedup.candidate_pairs(norm)
    scored = dedup.score_candidates(norm, pairs)
    scored.to_csv(args.out / "scored_pairs.csv", index=False)
    scored[scored["decision"] == "review"].to_csv(args.out / "review_queue.csv", index=False)

    matched = scored.loc[scored["decision"] == "match", ["left", "right"]].itertuples(index=False)
    clusters = dedup.cluster(raw["record_id"], matched)
    gold = dedup.golden_records(raw, clusters)
    gold.to_csv(args.out / "golden_records.csv", index=False)

    # Raw inputs for the dbt project (dbt/): the warehouse models start from these three files.
    data_dir = Path("data")
    data_dir.mkdir(exist_ok=True)
    if args.input:
        raw.to_csv(data_dir / "raw_records.csv", index=False)
    (scored[["left", "right", "score", "decision"]]
     .rename(columns={"left": "record_id_a", "right": "record_id_b", "score": "match_score"})
     .to_csv(data_dir / "match_pairs.csv", index=False))
    pd.DataFrame({"record_id": list(clusters), "cluster_id": list(clusters.values())}).to_csv(
        data_dir / "record_clusters.csv", index=False)

    metrics = None
    if truth is not None:
        # Simulate a reviewer who correctly confirms or rejects every pair in the review queue.
        person = dict(zip(truth["record_id"], truth["person_id"]))
        reviewed = [(a, b) for a, b, d in scored[["left", "right", "decision"]].itertuples(index=False)
                    if d == "match" or (d == "review" and person[a] == person[b])]
        metrics = {
            "baseline": evaluate.pairwise_metrics(dedup.baseline_clusters(norm), truth),
            "pipeline": evaluate.pairwise_metrics(clusters, truth),
            "pipeline_after_review": evaluate.pairwise_metrics(
                dedup.cluster(raw["record_id"], reviewed), truth),
        }

    summary = {
        "records_in": len(raw),
        "people_out": len(gold),
        "duplicates_removed": len(raw) - len(gold),
        "candidate_pairs": len(pairs),
        "all_possible_pairs": len(raw) * (len(raw) - 1) // 2,
        "auto_matches": int((scored["decision"] == "match").sum()),
        "review_queue": int((scored["decision"] == "review").sum()),
        "dq_issues": len(issues),
        "records_with_issues": int(issues["record_id"].nunique()),
        "runtime_s": round(time.time() - t0, 1),
        "metrics": metrics,
    }
    (args.out / "summary.json").write_text(json.dumps(summary, indent=2))
    ins = insights.build(raw, gold, issues, scored, clusters, truth)
    bench_path = Path("benchmarks/benchmark.json")
    bench = json.loads(bench_path.read_text()) if bench_path.exists() else None
    html = report.build(summary, issues, comp, scored, gold, raw, ins, repo=args.repo, bench=bench)
    (args.out / "report.html").write_text(html, encoding="utf-8")
    Path("docs").mkdir(exist_ok=True)
    Path("docs/index.html").write_text(html, encoding="utf-8")
    print(json.dumps(summary, indent=2))


if __name__ == "__main__":
    main()

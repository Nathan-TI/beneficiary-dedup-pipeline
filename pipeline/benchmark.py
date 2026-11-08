"""Measure speed and accuracy at several data sizes; the report's Performance tab reads the result.

    python -m pipeline.benchmark                 # writes benchmarks/benchmark.json
    python -m pipeline.benchmark --sizes 1000 5000
"""
from __future__ import annotations

import argparse
import json
import time
from pathlib import Path

from . import dedup, evaluate, generate, normalize, quality


def run(n_people: int, seed: int = 11) -> dict:
    raw, truth = generate.generate(n_people=n_people, seed=seed)
    t0 = time.perf_counter()
    quality.run_checks(raw)
    norm = normalize.normalize(raw)
    pairs = dedup.candidate_pairs(norm)
    scored = dedup.score_candidates(norm, pairs)
    matched = scored.loc[scored["decision"] == "match", ["left", "right"]].itertuples(index=False)
    clusters = dedup.cluster(raw["record_id"], matched)
    seconds = time.perf_counter() - t0
    m = evaluate.pairwise_metrics(clusters, truth)
    n = len(raw)
    return {"people": n_people, "records": n, "seconds": round(seconds, 2),
            "records_per_second": round(n / seconds), "pairs_scored": len(pairs),
            "all_pairs": n * (n - 1) // 2, "precision": m["precision"], "recall": m["recall"], "f1": m["f1"]}


def main() -> None:
    ap = argparse.ArgumentParser()
    ap.add_argument("--sizes", type=int, nargs="+", default=[1000, 4000, 10000, 20000])
    ap.add_argument("--out", type=Path, default=Path("benchmarks/benchmark.json"))
    args = ap.parse_args()
    rows = []
    for n in args.sizes:
        r = run(n)
        print(json.dumps(r))
        rows.append(r)
    args.out.parent.mkdir(parents=True, exist_ok=True)
    args.out.write_text(json.dumps(rows, indent=2))


if __name__ == "__main__":
    main()

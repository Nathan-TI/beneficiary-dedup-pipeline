"""Pairwise precision / recall / F1 against the generator's ground truth."""
from __future__ import annotations

from itertools import combinations

import pandas as pd


def _pairs(groups: pd.Series) -> set[tuple[str, str]]:
    out = set()
    for ids in groups:
        if len(ids) > 1:
            out.update(combinations(sorted(ids), 2))
    return out


def pairwise_metrics(clusters: dict[str, str], truth: pd.DataFrame) -> dict:
    pred = pd.Series(clusters).reset_index()
    pred.columns = ["record_id", "cluster"]
    pred_pairs = _pairs(pred.groupby("cluster")["record_id"].agg(list))
    true_pairs = _pairs(truth.groupby("person_id")["record_id"].agg(list))
    tp = len(pred_pairs & true_pairs)
    fp = len(pred_pairs - true_pairs)
    fn = len(true_pairs - pred_pairs)
    p = tp / (tp + fp) if tp + fp else 0.0
    r = tp / (tp + fn) if tp + fn else 0.0
    f1 = 2 * p * r / (p + r) if p + r else 0.0
    return {"precision": round(p, 4), "recall": round(r, 4), "f1": round(f1, 4),
            "true_pairs": len(true_pairs), "tp": tp, "fp": fp, "fn": fn}

"""Blocking -> pairwise scoring -> thresholding -> clustering -> golden records."""
from __future__ import annotations

from itertools import combinations

import pandas as pd
from rapidfuzz.distance import JaroWinkler

# Feature weights (renormalised over the fields both records actually have).
WEIGHTS = {"first": 0.25, "father": 0.20, "grandfather": 0.10, "dob": 0.20,
           "phone": 0.10, "id": 0.25, "sex": 0.05, "location": 0.05}
MATCH_AT = 0.88      # auto-merge at or above this score
REVIEW_AT = 0.75     # send to a human between REVIEW_AT and MATCH_AT
MAX_BLOCK = 200      # skip runaway blocks (e.g. a phone number shared by an NGO office)

BLOCKING_KEYS = [
    ("first_name_key", "father_name_key"),
    ("phone_n",),
    ("id_n",),
    ("dob_n", "first_name_key"),
    ("dob_n", "father_name_key"),
    ("father_name_key", "grandfather_name_key", "woreda"),   # catches blank/mistyped first names
]


def candidate_pairs(df: pd.DataFrame) -> set[tuple[int, int]]:
    pairs: set[tuple[int, int]] = set()
    for key in BLOCKING_KEYS:
        sub = df.dropna(subset=list(key))
        for _, grp in sub.groupby(list(key)):
            if 1 < len(grp) <= MAX_BLOCK:
                pairs.update(combinations(sorted(grp.index), 2))
    return pairs


def _name_sim(a, b, ka, kb):
    if not a or not b:
        return None
    return max(JaroWinkler.similarity(a, b), 0.95 if ka and ka == kb else 0.0)


def _dob_sim(a, b):
    if pd.isna(a) or pd.isna(b):
        return None
    if a == b:
        return 1.0
    if a.year == b.year and a.month == b.day and a.day == b.month:
        return 0.85                      # day/month swapped
    if a.month == b.month and a.day == b.day and abs(a.year - b.year) <= 2:
        return 0.8                       # year mistyped or estimated
    if a.month == b.day and a.day == b.month and abs(a.year - b.year) <= 1:
        return 0.65                      # swapped and year off
    if abs((a - b).days) <= 31:
        return 0.6
    return 0.0


def _phone_sim(a, b):
    if not a or not b:
        return None
    if a == b:
        return 1.0
    return 0.7 if sum(x != y for x, y in zip(a, b)) == 1 else 0.0


def score_pair(r1, r2) -> tuple[float, dict]:
    f = {
        "first": _name_sim(r1.first_name_n, r2.first_name_n, r1.first_name_key, r2.first_name_key),
        "father": _name_sim(r1.father_name_n, r2.father_name_n, r1.father_name_key, r2.father_name_key),
        "grandfather": _name_sim(r1.grandfather_name_n, r2.grandfather_name_n,
                                 r1.grandfather_name_key, r2.grandfather_name_key),
        "dob": _dob_sim(r1.dob_n, r2.dob_n),
        "phone": _phone_sim(r1.phone_n, r2.phone_n),
        "id": None if not r1.id_n or not r2.id_n else float(r1.id_n == r2.id_n),
        "sex": None if not r1.sex_n or not r2.sex_n else float(r1.sex_n == r2.sex_n),
        "location": 1.0 if r1.kebele == r2.kebele and r1.woreda == r2.woreda
        else 0.5 if r1.woreda == r2.woreda else 0.0,
    }
    avail = {k: v for k, v in f.items() if v is not None}
    total_w = sum(WEIGHTS[k] for k in avail)
    score = sum(WEIGHTS[k] * v for k, v in avail.items()) / total_w

    # Domain rules that a weighted average alone gets wrong.
    if f["id"] == 1.0:
        score = max(score, 0.95)                 # same national ID = same person
    elif f["id"] == 0.0:
        score = min(score, 0.5)                  # two different valid IDs = different people
    if f["first"] is not None and f["first"] < 0.80 and f["id"] != 1.0:
        score *= 0.6                             # siblings share father + grandfather names
    if f["sex"] == 0.0 and f["id"] != 1.0:
        score = min(score, 0.7)
    # Never auto-merge on name alone: without a DOB, an ID or a phone match, a human decides.
    if f["dob"] is None and f["id"] != 1.0 and f["phone"] != 1.0:
        score = min(score, MATCH_AT - 0.01)
    return round(score, 4), f


def score_candidates(df: pd.DataFrame, pairs) -> pd.DataFrame:
    rec = dict(zip(df.index, df.itertuples(index=False)))   # fast row access (df.loc per pair is slow)
    rows = []
    for i, j in pairs:
        s, f = score_pair(rec[i], rec[j])
        rows.append({"left": rec[i].record_id, "right": rec[j].record_id, "score": s,
                     **{f"sim_{k}": (None if v is None else round(v, 3)) for k, v in f.items()}})
    out = pd.DataFrame(rows)
    out["decision"] = pd.cut(out["score"], [-1, REVIEW_AT, MATCH_AT, 2],
                             labels=["no match", "review", "match"], right=False)
    return out.sort_values("score", ascending=False, ignore_index=True)


def cluster(record_ids, matched_pairs) -> dict[str, str]:
    """Union-find: every record gets the id of its cluster's representative."""
    parent = {r: r for r in record_ids}

    def find(x):
        while parent[x] != x:
            parent[x] = parent[parent[x]]
            x = parent[x]
        return x

    for a, b in matched_pairs:
        ra, rb = find(a), find(b)
        if ra != rb:
            parent[max(ra, rb)] = min(ra, rb)
    return {r: find(r) for r in record_ids}


def golden_records(raw: pd.DataFrame, clusters: dict[str, str]) -> pd.DataFrame:
    """One surviving record per person: most complete record wins, gaps filled from the others."""
    df = raw.copy()
    df["cluster_id"] = df["record_id"].map(clusters)
    df["_filled"] = df.notna().sum(axis=1)
    df = df.sort_values(["cluster_id", "_filled", "registration_date"], ascending=[True, False, False])
    fill_cols = ["grandfather_name", "phone", "id_number"]
    df[fill_cols] = df.groupby("cluster_id")[fill_cols].transform(lambda s: s.bfill().ffill())
    sizes = df.groupby("cluster_id")["record_id"].agg(list)
    gold = df.drop_duplicates("cluster_id").drop(columns="_filled").copy()
    gold["merged_record_ids"] = gold["cluster_id"].map(lambda c: ";".join(sizes[c]))
    gold["n_records"] = gold["cluster_id"].map(lambda c: len(sizes[c]))
    return gold.reset_index(drop=True)


def baseline_clusters(df: pd.DataFrame) -> dict[str, str]:
    """Naive approach many teams use: exact match on cleaned full name + date of birth."""
    key = (df["first_name_n"].fillna("?") + "|" + df["father_name_n"].fillna("?") + "|" +
           df["grandfather_name_n"].fillna("?") + "|" + df["dob_n"].astype(str))
    first = df.groupby(key)["record_id"].transform("min")
    return dict(zip(df["record_id"], first))

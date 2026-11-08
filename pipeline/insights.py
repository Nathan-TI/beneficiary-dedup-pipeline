"""Turn pipeline outputs into management-level insights and recommended actions."""
from __future__ import annotations

import pandas as pd

from . import dedup, evaluate
from .normalize import clean_phone

# Where each data-quality rule should be fixed at the source (data-collection form / training).
SOURCE_FIXES = {
    "Phone number in wrong format": "Only accept 10-digit numbers starting with 09 or 07.",
    "Sex not written as F or M": "Use a two-choice list (F / M) instead of free text.",
    "Household size not between 1 and 20": "Only accept numbers from 1 to 20.",
    "First name contains numbers or placeholders": "Allow letters only, and block entries like 'N/A' or '???'.",
    "Registration date not valid": "Fill in the date automatically from the phone or tablet.",
    "Missing sex": "Make sex a required field.",
    "Birth date is in the future": "Use a calendar picker that blocks future dates.",
    "Age over 110": "Ask the enumerator to confirm any age over 100.",
    "Birth date cannot be read": "Use a calendar picker instead of typing dates, with an 'age only' option.",
    "Missing first name": "Make first name a required field.",
    "Missing birth date": "Make birth date required, with an 'age only' option.",
    "Missing father's name": "Make father's name a required field.",
    "Missing woreda": "Pick location from a list instead of typing it.",
    "Missing kebele": "Pick location from a list instead of typing it.",
}


def _record_frame(raw: pd.DataFrame, gold: pd.DataFrame, issues: pd.DataFrame, clusters: dict) -> pd.DataFrame:
    df = raw[["record_id", "enumerator_id", "region", "zone", "woreda", "kebele", "registration_date",
              "phone", "id_number"]].copy()
    df["person"] = df["record_id"].map(clusters)
    df["reg_date"] = pd.to_datetime(df["registration_date"], format="%Y-%m-%d", errors="coerce")
    # A duplicate is a re-registration: any record after the person's first registration
    # (this is what an enumerator or a site could have prevented).
    first = df.sort_values(["reg_date", "record_id"], na_position="last").groupby("person")["record_id"].first()
    df["is_duplicate"] = ~df["record_id"].isin(set(first))
    df["has_issue"] = df["record_id"].isin(set(issues["record_id"]))
    df["valid_phone"] = df["phone"].map(clean_phone).notna()
    df["has_id"] = df["id_number"].astype(str).str.fullmatch(r"\d{12}")
    return df


def _pct(s) -> float:
    return round(100 * float(s.mean()), 1) if len(s) else 0.0


def enumerators(df: pd.DataFrame) -> list[dict]:
    g = df.groupby("enumerator_id").agg(
        registrations=("record_id", "size"), issue_rate=("has_issue", _pct),
        duplicate_rate=("is_duplicate", _pct), valid_phone=("valid_phone", _pct)).reset_index()
    flag_issue = g["issue_rate"].mean() + 1.5 * g["issue_rate"].std()
    flag_dup = g["duplicate_rate"].mean() + 1.5 * g["duplicate_rate"].std()
    g["flag"] = (g["issue_rate"] > flag_issue) | (g["duplicate_rate"] > flag_dup)
    g["reason"] = [
        " and ".join(r for r, c in [("many errors", i > flag_issue), ("many repeat registrations", d > flag_dup)] if c)
        for i, d in zip(g["issue_rate"], g["duplicate_rate"])]
    return g.sort_values(["flag", "issue_rate"], ascending=False).to_dict("records")


def woredas(df: pd.DataFrame) -> list[dict]:
    d = df.dropna(subset=["woreda"])
    g = d.groupby(["region", "zone", "woreda"]).agg(
        registrations=("record_id", "size"), people=("person", "nunique"),
        issue_rate=("has_issue", _pct), id_coverage=("has_id", _pct)).reset_index()
    g["duplicate_rate"] = (100 * (g["registrations"] - g["people"]) / g["registrations"]).round(1)
    return g.sort_values("duplicate_rate", ascending=False).to_dict("records")


def weekly(df: pd.DataFrame) -> list[dict]:
    d = df.dropna(subset=["reg_date"]).copy()
    d["week"] = d["reg_date"].dt.to_period("W-SUN").dt.start_time
    g = d.groupby("week").agg(registrations=("record_id", "size"),
                              duplicate_rate=("is_duplicate", _pct),
                              issue_rate=("has_issue", _pct)).reset_index()
    g["week"] = g["week"].dt.strftime("%Y-%m-%d")
    return g.to_dict("records")


def threshold_curve(raw: pd.DataFrame, scored: pd.DataFrame, truth: pd.DataFrame | None) -> list[dict]:
    if truth is None:
        return []
    rows = []
    for t100 in range(int(round(dedup.REVIEW_AT * 100)), 100):
        t = t100 / 100
        auto = scored[scored["score"] >= t]
        m = evaluate.pairwise_metrics(
            dedup.cluster(raw["record_id"], auto[["left", "right"]].itertuples(index=False)), truth)
        rows.append({"t": t, "auto": len(auto),
                     "review": int(((scored["score"] >= dedup.REVIEW_AT) & (scored["score"] < t)).sum()),
                     "precision": m["precision"], "recall": m["recall"], "fp": m["fp"]})
    return rows


def build(raw, gold, issues, scored, clusters, truth=None) -> dict:
    df = _record_frame(raw, gold, issues, clusters)
    enums, wors, weeks = enumerators(df), woredas(df), weekly(df)
    by_rule = issues.groupby("rule")["record_id"].nunique().sort_values(ascending=False)

    review = scored[scored["decision"] == "review"]
    norm_id = raw.set_index("record_id")["id_number"].astype(str).str.fullmatch(r"\d{12}")
    review_missing_id = float(((~review["left"].map(norm_id)) | (~review["right"].map(norm_id))).mean()) if len(review) else 0

    dup_n = int(df["is_duplicate"].sum())
    flagged = [e for e in enums if e["flag"]]
    worst = wors[:3]
    recs = [
        {"title": f"Remove {dup_n:,} repeat registrations before the next distribution",
         "detail": f"{100 * dup_n / len(df):.1f}% of registrations are people who were already on the list. "
                   "Removing them stops assistance being paid twice. See the money calculator below.",
         "owner": "Programme / cash transfers team", "impact": "high"},
        {"title": "Change the registration form to stop the 3 most common errors",
         "detail": " ".join(f"{r} ({int(by_rule[r]):,}): {SOURCE_FIXES.get(r, 'add a check in the form.')}"
                            for r in by_rule.index[:3]),
         "owner": "Information management", "impact": "high"},
        {"title": f"Coach {len(flagged)} enumerator{'s' if len(flagged) != 1 else ''} whose results are well above average",
         "detail": ", ".join(f"{e['enumerator_id']} ({e['reason']})" for e in flagged[:6]) or "No enumerator stands out.",
         "owner": "Field coordination", "impact": "medium"},
        {"title": "Send verification teams to " + ", ".join(w["woreda"] for w in worst) + " first",
         "detail": "These places have the most repeat registrations: " + "; ".join(
             f"{w['woreda']} ({w['region']}) {w['duplicate_rate']}%" for w in worst) + ".",
         "owner": "Area offices", "impact": "medium"},
        {"title": f"Record national ID numbers more often (only {_pct(df['has_id'])}% have one today)",
         "detail": ("Every pair" if review_missing_id >= 0.995 else f"{100 * review_missing_id:.0f}% of the pairs")
                   + " that needs a person to check is missing a national ID on at least one record. With an ID on both, "
                   "the system can decide on its own, which saves staff time.",
         "owner": "Information management / national ID team", "impact": "medium"},
    ]
    return {
        "enumerators": enums, "woredas": wors, "weekly": weeks,
        "curve": threshold_curve(raw, scored, truth),
        "recommendations": recs, "duplicates": dup_n, "records": len(df),
        "review_pairs": int(len(review)), "id_coverage": _pct(df["has_id"]),
        "phone_coverage": _pct(df["valid_phone"]), "review_missing_id_pct": round(100 * review_missing_id),
        "source_fixes": [{"rule": r, "records": int(n), "fix": SOURCE_FIXES.get(r, "")} for r, n in by_rule.items()],
    }

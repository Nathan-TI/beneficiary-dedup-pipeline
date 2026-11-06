"""Rule-based data-quality checks. Each rule yields one row per failing record."""
from __future__ import annotations

import re

import pandas as pd

from .normalize import clean_phone

TODAY = pd.Timestamp("2026-11-01")
NAME_OK = re.compile(r"^[A-Za-z][A-Za-z' -]{1,}$")

REQUIRED = ["first_name", "father_name", "sex", "date_of_birth", "region", "zone", "woreda", "kebele"]


def _issue(rule, severity, field, mask, df):
    rows = df.loc[mask, ["record_id", field]].rename(columns={field: "value"})
    rows.insert(1, "rule", rule)
    rows.insert(2, "severity", severity)
    rows.insert(3, "field", field)
    return rows


def run_checks(df: pd.DataFrame) -> pd.DataFrame:
    checks = []
    for col in REQUIRED:
        blank = df[col].isna() | (df[col].astype(str).str.strip() == "")
        checks.append(_issue(f"Missing {col.replace('_', ' ')}", "critical", col, blank, df))

    name = df["first_name"].fillna("").astype(str).str.strip()
    checks.append(_issue("Invalid first name", "critical", "first_name",
                         (name != "") & ~name.str.match(NAME_OK), df))

    has_phone = df["phone"].notna() & (df["phone"].astype(str).str.strip() != "")
    checks.append(_issue("Invalid phone format", "warning", "phone",
                         has_phone & df["phone"].map(clean_phone).isna(), df))

    sex = df["sex"].fillna("").astype(str).str.strip()
    checks.append(_issue("Non-standard sex value", "warning", "sex",
                         (sex != "") & ~sex.isin(["F", "M"]), df))

    dob = pd.to_datetime(df["date_of_birth"], format="%Y-%m-%d", errors="coerce")
    has_dob = df["date_of_birth"].notna() & (df["date_of_birth"].astype(str).str.strip() != "")
    checks.append(_issue("Unparseable date of birth", "critical", "date_of_birth", has_dob & dob.isna(), df))
    checks.append(_issue("Date of birth in future", "critical", "date_of_birth", dob > TODAY, df))
    checks.append(_issue("Implausible age (>110)", "warning", "date_of_birth",
                         dob < TODAY - pd.DateOffset(years=110), df))

    hh = pd.to_numeric(df["household_size"], errors="coerce")
    checks.append(_issue("Household size out of range (1-20)", "warning", "household_size",
                         (hh < 1) | (hh > 20), df))

    reg = pd.to_datetime(df["registration_date"], format="%Y-%m-%d", errors="coerce")
    checks.append(_issue("Invalid registration date", "warning", "registration_date", reg.isna(), df))

    issues = pd.concat(checks, ignore_index=True)
    issues["value"] = issues["value"].astype(str)
    return issues


def completeness(df: pd.DataFrame) -> pd.DataFrame:
    cols = ["first_name", "father_name", "grandfather_name", "sex", "date_of_birth",
            "phone", "id_number", "kebele", "household_size"]
    rows = []
    for c in cols:
        filled = df[c].notna() & (df[c].astype(str).str.strip() != "")
        rows.append({"field": c, "filled_pct": round(100 * filled.mean(), 1)})
    return pd.DataFrame(rows)

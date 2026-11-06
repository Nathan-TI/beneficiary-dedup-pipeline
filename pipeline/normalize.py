"""Standardise raw fields so records can be compared fairly."""
from __future__ import annotations

import re

import pandas as pd

_NON_ALPHA = re.compile(r"[^a-z ]")
_SPACES = re.compile(r"\s+")
_DOUBLE = re.compile(r"(.)\1+")


def clean_name(s) -> str | None:
    if s is None or (isinstance(s, float) and pd.isna(s)):
        return None
    s = _NON_ALPHA.sub("", str(s).lower())
    s = _SPACES.sub(" ", s).strip()
    return s or None


def name_key(s: str | None) -> str | None:
    """Consonant skeleton that collapses common romanisation variants.

    Mohammed / Mohamed / Mohammad -> "mhmd"; Tesfaye / Tesfay -> "tsfy".
    """
    if not isinstance(s, str) or not s:
        return None
    s = s.replace("kh", "h").replace("ph", "f").replace("q", "k").replace("ou", "u")
    s = _DOUBLE.sub(r"\1", s)
    head, tail = s[0], re.sub(r"[aeiou]", "", s[1:])
    key = head + tail
    return key or None


def clean_phone(s) -> str | None:
    """Return a 9-digit Ethiopian mobile number (9XXXXXXXX or 7XXXXXXXX) or None."""
    if s is None or (isinstance(s, float) and pd.isna(s)):
        return None
    digits = re.sub(r"\D", "", str(s))
    if digits.startswith("251"):
        digits = digits[3:]
    if digits.startswith("0"):
        digits = digits[1:]
    if len(digits) == 9 and digits[0] in "97":
        return digits
    return None


def clean_sex(s) -> str | None:
    if s is None or (isinstance(s, float) and pd.isna(s)):
        return None
    s = str(s).strip().lower()
    if s in {"f", "female"}:
        return "F"
    if s in {"m", "male"}:
        return "M"
    return None


def normalize(df: pd.DataFrame) -> pd.DataFrame:
    out = df.copy()
    for col in ["first_name", "father_name", "grandfather_name"]:
        out[f"{col}_n"] = out[col].map(clean_name)
        out[f"{col}_key"] = out[f"{col}_n"].map(name_key)
    out["phone_n"] = out["phone"].map(clean_phone)
    out["sex_n"] = out["sex"].map(clean_sex)
    out["dob_n"] = pd.to_datetime(out["date_of_birth"], format="%Y-%m-%d", errors="coerce")
    out.loc[(out["dob_n"] > pd.Timestamp("2026-12-31")) | (out["dob_n"] < pd.Timestamp("1910-01-01")), "dob_n"] = pd.NaT
    out["id_n"] = out["id_number"].where(out["id_number"].astype(str).str.fullmatch(r"\d{12}"), None)
    # pandas stores missing strings as NaN (truthy); use None so `if not value` works downstream.
    text_cols = [c for c in out.columns if c.endswith(("_n", "_key")) and c != "dob_n"]
    out[text_cols] = out[text_cols].astype(object).where(out[text_cols].notna(), None)
    return out

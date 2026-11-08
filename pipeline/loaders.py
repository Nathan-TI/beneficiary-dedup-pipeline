"""Load registration data from the file formats field teams actually use.

Supported: CSV / TXT (comma, semicolon or tab, detected automatically), TSV, Excel (.xlsx, first sheet
or a named sheet), JSON (a list of records), JSON Lines (.jsonl / .ndjson) and Parquet.

Column names are matched flexibly, so typical exports from KoboToolbox, ODK, SurveyCTO or a database
work without renaming: "First Name", "first_name", "fname" and "given_name" all map to first_name.
"""
from __future__ import annotations

import csv
import re
from pathlib import Path

import pandas as pd

SUPPORTED = {".csv": "CSV", ".txt": "Text (delimited)", ".tsv": "TSV", ".xlsx": "Excel", ".xlsm": "Excel",
             ".json": "JSON", ".jsonl": "JSON Lines", ".ndjson": "JSON Lines", ".parquet": "Parquet"}

REQUIRED = ["first_name", "father_name", "sex", "date_of_birth"]
OPTIONAL = ["record_id", "grandfather_name", "phone", "id_number", "region", "zone", "woreda", "kebele",
            "household_size", "registration_date", "enumerator_id"]

ALIASES = {
    "record_id": ["record_id", "id", "registration_id", "beneficiary_id", "_id", "_uuid", "uuid", "instanceid", "key"],
    "first_name": ["first_name", "firstname", "fname", "given_name", "name", "name_first", "beneficiary_name"],
    "father_name": ["father_name", "fathers_name", "fathername", "middle_name", "second_name", "name_father"],
    "grandfather_name": ["grandfather_name", "grandfathers_name", "grandfathername", "last_name", "surname",
                         "family_name", "third_name", "name_grandfather"],
    "sex": ["sex", "gender"],
    "date_of_birth": ["date_of_birth", "dob", "birth_date", "birthdate", "date_birth"],
    "phone": ["phone", "phone_number", "phonenumber", "mobile", "mobile_number", "telephone", "tel", "msisdn"],
    "id_number": ["id_number", "national_id", "fayda_id", "fayda", "fan", "nid", "national_id_number", "id_no"],
    "region": ["region", "admin1"],
    "zone": ["zone", "admin2"],
    "woreda": ["woreda", "district", "admin3"],
    "kebele": ["kebele", "admin4", "village"],
    "household_size": ["household_size", "hh_size", "hhsize", "family_size", "household_members"],
    "registration_date": ["registration_date", "reg_date", "date_registered", "submission_date", "_submission_time",
                          "today", "start", "date"],
    "enumerator_id": ["enumerator_id", "enumerator", "enumerator_name", "username", "_submitted_by", "deviceid",
                      "interviewer"],
}


class InputError(ValueError):
    """Raised with a plain-language message when a file can't be used."""


def _key(name: str) -> str:
    name = str(name).strip().lower()
    name = name.split("/")[-1]                      # Kobo/ODK group paths: "beneficiary/first_name"
    name = re.sub(r"[^a-z0-9]+", "_", name).strip("_")
    return name


def _read(path: Path, sheet: str | int | None) -> pd.DataFrame:
    ext = path.suffix.lower()
    if ext not in SUPPORTED:
        if ext == ".xls":
            raise InputError("Old Excel files (.xls) are not supported. Open the file in Excel and save it as .xlsx.")
        raise InputError(f"Unsupported file type '{ext}'. Supported: {', '.join(sorted(SUPPORTED))}.")
    if ext in {".csv", ".txt", ".tsv"}:
        if ext == ".tsv":
            sep = "\t"
        else:
            sample = path.read_text(encoding="utf-8-sig", errors="replace")[:20000]
            try:
                sep = csv.Sniffer().sniff(sample, delimiters=",;\t|").delimiter
            except csv.Error:
                sep = ","
        return pd.read_csv(path, sep=sep, dtype=str, keep_default_na=False, na_values=[""], encoding="utf-8-sig")
    if ext in {".xlsx", ".xlsm"}:
        return pd.read_excel(path, sheet_name=sheet if sheet is not None else 0, dtype=str)
    if ext == ".json":
        return pd.read_json(path, dtype=False)
    if ext in {".jsonl", ".ndjson"}:
        return pd.read_json(path, lines=True, dtype=False)
    try:
        return pd.read_parquet(path)
    except ImportError as e:
        raise InputError("Reading Parquet needs one extra package: pip install pyarrow") from e


def map_columns(df: pd.DataFrame) -> tuple[pd.DataFrame, dict]:
    """Rename recognised columns to the standard names; return the mapping used."""
    by_key = {}
    for col in df.columns:
        by_key.setdefault(_key(col), col)
    mapping = {}
    for std, aliases in ALIASES.items():
        for a in map(_key, aliases):
            if a in by_key and by_key[a] not in mapping.values():
                mapping[std] = by_key[a]
                break
    out = df.rename(columns={v: k for k, v in mapping.items()})
    return out, mapping


def load_registrations(path: str | Path, sheet: str | int | None = None) -> tuple[pd.DataFrame, dict]:
    """Read a file, standardise column names and types; return (records, info)."""
    path = Path(path)
    if not path.exists():
        raise InputError(f"File not found: {path}")
    df, mapping = map_columns(_read(path, sheet))
    missing = [c for c in REQUIRED if c not in df.columns]
    if missing:
        raise InputError("These required columns were not found: " + ", ".join(missing)
                         + ". Rename them in the file or see templates/registration_template.csv.")
    for c in OPTIONAL:
        if c not in df.columns:
            df[c] = None
    if df["record_id"].isna().all():
        df["record_id"] = [f"R{i:06d}" for i in range(1, len(df) + 1)]
    df = df[["record_id", *REQUIRED[:2], "grandfather_name", "sex", "date_of_birth", "phone", "id_number",
             "region", "zone", "woreda", "kebele", "household_size", "registration_date", "enumerator_id"]].copy()
    for c in df.columns:  # everything as text; cleaning happens later
        df[c] = df[c].map(lambda v: None if v is None or (isinstance(v, float) and pd.isna(v)) else str(v).strip())
    for c in ("date_of_birth", "registration_date"):  # Excel/Kobo timestamps -> YYYY-MM-DD
        parsed = pd.to_datetime(df[c], errors="coerce", dayfirst=False, format="mixed")
        df[c] = [p.strftime("%Y-%m-%d") if pd.notna(p) else v for p, v in zip(parsed, df[c])]
    if df["record_id"].duplicated().any():
        raise InputError("Some record IDs appear more than once. Each row needs a unique ID (or leave the column out).")
    info = {"format": SUPPORTED[path.suffix.lower()], "rows": len(df), "columns_mapped": mapping}
    return df, info

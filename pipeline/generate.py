"""Synthetic beneficiary registration data with known duplicates and data-quality defects.

Every record is fictional. Names follow the Ethiopian naming convention
(given name + father's name + grandfather's name), which matters for matching:
siblings share father and grandfather names, so a naive fuzzy match on the full
name merges different people. The generator plants those "hard negatives" on purpose.

Outputs a records DataFrame and a ground-truth mapping record_id -> person_id.
"""
from __future__ import annotations

import random
from datetime import date, timedelta

import pandas as pd

MALE = [
    "Abebe", "Kebede", "Tesfaye", "Mulugeta", "Getachew", "Dawit", "Yohannes", "Solomon",
    "Mohammed", "Ahmed", "Abdi", "Hussein", "Ali", "Ibrahim", "Tadesse", "Girma", "Haile",
    "Bekele", "Alemayehu", "Wondimu", "Fikadu", "Lemma", "Gemechu", "Tolosa", "Daba",
    "Yusuf", "Omar", "Hassan", "Bereket", "Samuel", "Tekle", "Gebre", "Asfaw", "Negash",
]
FEMALE = [
    "Almaz", "Tigist", "Hiwot", "Meron", "Selam", "Bethlehem", "Fatuma", "Amina", "Hawa",
    "Zahra", "Aster", "Genet", "Mulu", "Tsehay", "Lensa", "Chaltu", "Ayantu", "Hana",
    "Rahel", "Saba", "Kedija", "Halima", "Mekdes", "Eden", "Sara", "Zeynab",
]
# Common romanisation variants of the same Amharic/Arabic name.
TRANSLIT = {
    "Mohammed": ["Mohamed", "Mohammad", "Mohamad", "Muhammed"],
    "Tesfaye": ["Tesfay", "Tesfayie"],
    "Yohannes": ["Yohanes", "Yohannis"],
    "Getachew": ["Getachaw", "Getacho"],
    "Kedija": ["Khadija", "Kedijah"],
    "Fatuma": ["Fatima", "Fatumah"],
    "Hussein": ["Husen", "Hussen", "Husein"],
    "Ahmed": ["Ahmad", "Ahmedin"],
    "Bethlehem": ["Betelhem", "Bethelehem"],
    "Hiwot": ["Hiwet", "Hiwott"],
    "Tsehay": ["Tsehaye", "Tsahay"],
    "Ibrahim": ["Ibrahem", "Ebrahim"],
    "Zeynab": ["Zeinab", "Zainab"],
    "Yusuf": ["Yusef", "Yousuf"],
    "Alemayehu": ["Alemayew", "Alemayhu"],
    "Gebre": ["Gebrie", "Gabre"],
}
LOCATIONS = {
    ("Afar", "Zone A"): ["Woreda 01", "Woreda 02", "Woreda 03"],
    ("Amhara", "Zone B"): ["Woreda 04", "Woreda 05"],
    ("Somali", "Zone C"): ["Woreda 06", "Woreda 07", "Woreda 08"],
    ("Oromia", "Zone D"): ["Woreda 09", "Woreda 10"],
}
KEBELES = [f"Kebele {i:02d}" for i in range(1, 9)]


def _phone(rng: random.Random) -> str:
    prefix = rng.choice(["9", "9", "9", "7"])
    return prefix + "".join(str(rng.randint(0, 9)) for _ in range(8))


def _fmt_phone(rng: random.Random, p: str) -> str:
    """Write the same number the way enumerators actually do."""
    style = rng.random()
    if style < 0.5:
        return "0" + p
    if style < 0.75:
        return "+251" + p
    if style < 0.9:
        return "251" + p
    return f"0{p[:3]} {p[3:6]} {p[6:]}"


def _typo(rng: random.Random, s: str) -> str:
    if len(s) < 4:
        return s
    i = rng.randint(1, len(s) - 2)
    kind = rng.choice(["swap", "drop", "dup", "sub"])
    if kind == "swap":
        return s[:i] + s[i + 1] + s[i] + s[i + 2:]
    if kind == "drop":
        return s[:i] + s[i + 1:]
    if kind == "dup":
        return s[:i] + s[i] + s[i:]
    return s[:i] + rng.choice("aeiou") + s[i + 1:]


def _variant(rng: random.Random, name: str) -> str:
    if name in TRANSLIT and rng.random() < 0.8:
        return rng.choice(TRANSLIT[name])
    return _typo(rng, name)


def _person(rng: random.Random, pid: int, household: dict | None = None) -> dict:
    sex = rng.choice(["F", "M"])
    first = rng.choice(FEMALE if sex == "F" else MALE)
    if household:
        father, grandfather = household["father"], household["grandfather"]
        loc = household["loc"]
    else:
        father, grandfather = rng.choice(MALE), rng.choice(MALE)
        (region, zone), woredas = rng.choice(list(LOCATIONS.items()))
        loc = (region, zone, rng.choice(woredas), rng.choice(KEBELES))
    age_days = rng.randint(365 * 1, 365 * 85)
    dob = date(2026, 6, 1) - timedelta(days=age_days)
    return {
        "person_id": pid,
        "first_name": first,
        "father_name": father,
        "grandfather_name": grandfather,
        "sex": sex,
        "date_of_birth": dob,
        "phone": _phone(rng) if rng.random() < 0.75 else None,
        "id_number": "".join(str(rng.randint(0, 9)) for _ in range(12)) if rng.random() < 0.35 else None,
        "region": loc[0], "zone": loc[1], "woreda": loc[2], "kebele": loc[3],
        "household_size": rng.randint(1, 11),
    }


def _as_record(rng: random.Random, p: dict) -> dict:
    r = dict(p)
    r["phone"] = _fmt_phone(rng, p["phone"]) if p["phone"] else None
    r["date_of_birth"] = p["date_of_birth"].isoformat()
    r["registration_date"] = (date(2026, 3, 1) + timedelta(days=rng.randint(0, 150))).isoformat()
    r["enumerator_id"] = f"ENUM-{rng.randint(1, 25):03d}"
    return r


def _duplicate(rng: random.Random, p: dict) -> dict:
    """Re-register the same person with 1-3 realistic distortions."""
    d = dict(p)
    ops = rng.sample(
        ["first", "father", "grandfather_drop", "dob_swap", "dob_year", "phone_drop",
         "phone_digit", "kebele", "hh", "id_drop", "case"],
        k=rng.randint(1, 3),
    )
    for op in ops:
        if op == "first":
            d["first_name"] = _variant(rng, d["first_name"])
        elif op == "father":
            d["father_name"] = _variant(rng, d["father_name"])
        elif op == "grandfather_drop":
            d["grandfather_name"] = None
        elif op == "dob_swap" and d["date_of_birth"].day <= 12:
            dob = d["date_of_birth"]
            try:
                d["date_of_birth"] = dob.replace(month=dob.day, day=dob.month)
            except ValueError:
                pass
        elif op == "dob_year":
            dob = d["date_of_birth"]
            try:
                d["date_of_birth"] = dob.replace(year=dob.year + rng.choice([-1, 1]))
            except ValueError:
                pass
        elif op == "phone_drop":
            d["phone"] = None
        elif op == "phone_digit" and d["phone"]:
            d["phone"] = d["phone"][:-1] + str((int(d["phone"][-1]) + 1) % 10)
        elif op == "kebele":
            d["kebele"] = rng.choice(KEBELES)
        elif op == "hh":
            d["household_size"] = max(1, d["household_size"] + rng.choice([-2, -1, 1, 2]))
        elif op == "id_drop":
            d["id_number"] = None
        elif op == "case":
            d["first_name"] = "  " + d["first_name"].upper()
            d["father_name"] = d["father_name"].lower() + " "
    return d


def _inject_dq_defects(rng: random.Random, df: pd.DataFrame, rate: float = 0.04) -> pd.DataFrame:
    df = df.copy()
    n = len(df)
    def pick(k):
        return rng.sample(range(n), k=max(1, int(n * k)))
    for i in pick(rate):
        df.at[i, "phone"] = rng.choice(["0911", "12345", "+251 1234", "n/a"])
    for i in pick(rate / 2):
        df.at[i, "date_of_birth"] = rng.choice(["2027-05-10", "1890-01-01", "not known"])
    for i in pick(rate / 2):
        df.at[i, "household_size"] = rng.choice([0, 35, -1])
    for i in pick(rate):
        df.at[i, "sex"] = rng.choice(["Male", "female", "", "X"])
    for i in pick(rate / 2):
        df.at[i, "first_name"] = rng.choice(["", "???", "Abebe2", "N/A"])
    for i in pick(rate / 3):
        df.at[i, "registration_date"] = "2025-13-40"
    return df


def generate(n_people: int = 4000, dup_rate: float = 0.15, sibling_rate: float = 0.10,
             seed: int = 42) -> tuple[pd.DataFrame, pd.DataFrame]:
    rng = random.Random(seed)
    people, pid = [], 0
    while len(people) < n_people:
        p = _person(rng, pid)
        people.append(p)
        pid += 1
        # Hard negatives: siblings share father, grandfather and kebele.
        if rng.random() < sibling_rate:
            hh = {"father": p["father_name"], "grandfather": p["grandfather_name"],
                  "loc": (p["region"], p["zone"], p["woreda"], p["kebele"])}
            for _ in range(rng.randint(1, 3)):
                s = _person(rng, pid, hh)
                s["date_of_birth"] = p["date_of_birth"] + timedelta(days=rng.randint(-3000, 3000))
                s["phone"] = p["phone"] if rng.random() < 0.3 else s["phone"]  # shared family phone
                people.append(s)
                pid += 1

    records = []
    for p in people:
        records.append(_as_record(rng, p))
        if rng.random() < dup_rate:
            for _ in range(rng.choice([1, 1, 1, 2])):
                records.append(_as_record(rng, _duplicate(rng, p)))

    rng.shuffle(records)
    df = pd.DataFrame(records)
    df.insert(0, "record_id", [f"R{i:06d}" for i in range(1, len(df) + 1)])
    truth = df[["record_id", "person_id"]].copy()
    df = df.drop(columns=["person_id"])
    df = _inject_dq_defects(rng, df)
    return df, truth

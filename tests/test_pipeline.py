import pandas as pd
import pytest

from pipeline import dedup, evaluate, generate, normalize, quality


@pytest.mark.parametrize("raw", ["0911223344", "+251911223344", "251911223344", "0911 223 344"])
def test_phone_formats_normalise_to_same_number(raw):
    assert normalize.clean_phone(raw) == "911223344"


@pytest.mark.parametrize("raw", ["0911", "12345", "n/a", None])
def test_invalid_phones_rejected(raw):
    assert normalize.clean_phone(raw) is None


def test_name_key_collapses_romanisation_variants():
    keys = {normalize.name_key(normalize.clean_name(n)) for n in ["Mohammed", "Mohamed", "Mohammad", " MOHAMAD "]}
    assert len(keys) == 1


def _rec(**kw):
    base = dict(record_id="R1", first_name="Hiwot", father_name="Tesfaye", grandfather_name="Girma",
                sex="F", date_of_birth="1990-03-04", phone="0911223344", id_number=None,
                region="Afar", zone="Zone A", woreda="Woreda 01", kebele="Kebele 01",
                household_size=4, registration_date="2026-04-01", enumerator_id="ENUM-001")
    base.update(kw)
    return base


def _score(a, b):
    n = normalize.normalize(pd.DataFrame([_rec(**a), _rec(record_id="R2", **b)]))
    return dedup.score_pair(n.iloc[0], n.iloc[1])[0]


def test_spelling_variant_with_swapped_dob_matches():
    assert _score({}, {"first_name": "Hiwet", "father_name": "Tesfay", "date_of_birth": "1990-04-03",
                       "phone": "+251911223344"}) >= dedup.MATCH_AT


def test_sibling_is_not_merged():
    # Same father, grandfather, kebele and family phone, but a different person.
    assert _score({}, {"first_name": "Selam", "date_of_birth": "1994-08-12"}) < dedup.REVIEW_AT


def test_different_national_ids_never_merge():
    assert _score({"id_number": "111111111111"}, {"id_number": "222222222222"}) < dedup.REVIEW_AT


def test_name_only_match_goes_to_review_not_auto_merge():
    s = _score({"date_of_birth": None, "phone": None}, {"date_of_birth": None, "phone": None})
    assert dedup.REVIEW_AT <= s < dedup.MATCH_AT


def test_quality_checks_flag_defects():
    df = pd.DataFrame([_rec(), _rec(record_id="R2", phone="12345", date_of_birth="2030-01-01",
                                    household_size=0, sex="X")])
    rules = set(quality.run_checks(df).query("record_id == 'R2'")["rule"])
    assert {"Invalid phone format", "Date of birth in future",
            "Household size out of range (1-20)", "Non-standard sex value"} <= rules
    assert quality.run_checks(df).query("record_id == 'R1'").empty


@pytest.mark.parametrize("seed", [1, 7])
def test_end_to_end_accuracy(seed):
    raw, truth = generate.generate(n_people=1500, seed=seed)
    norm = normalize.normalize(raw)
    scored = dedup.score_candidates(norm, dedup.candidate_pairs(norm))
    matched = scored.loc[scored["decision"] == "match", ["left", "right"]].itertuples(index=False)
    m = evaluate.pairwise_metrics(dedup.cluster(raw["record_id"], matched), truth)
    baseline = evaluate.pairwise_metrics(dedup.baseline_clusters(norm), truth)
    assert m["precision"] >= 0.97
    assert m["recall"] >= 0.88
    assert m["f1"] > baseline["f1"] + 0.3


def test_llm_review_with_fake_model():
    from pipeline import llm_review
    raw, truth = generate.generate(n_people=300, seed=3)
    person = dict(zip(truth["record_id"], truth["person_id"]))
    ids = raw["record_id"].tolist()
    pairs = pd.DataFrame({"left": ids[:6], "right": ids[1:7], "score": [0.8] * 6})

    def fake_ask(prompt):  # always says "different people", wrapped in chatter like a real model might
        assert "Record A" in prompt and "grandfather_name" in prompt
        return 'Sure. {"same_person": false, "confidence": 0.9, "reason": "different first names"}'

    verdicts = llm_review.review(pairs, raw, fake_ask)
    assert verdicts["same_person"].eq(False).all()
    m = llm_review.evaluate(verdicts, truth)
    actual_dupes = sum(person[a] == person[b] for a, b in zip(pairs.left, pairs.right))
    assert m["pairs_judged"] == 6 and m["missed_duplicates"] == actual_dupes and m["false_merges"] == 0
    assert llm_review.parse_reply("no json here")["same_person"] is None


def test_insights_for_management():
    from pipeline import insights
    raw, truth = generate.generate(n_people=800, seed=5)
    norm = normalize.normalize(raw)
    scored = dedup.score_candidates(norm, dedup.candidate_pairs(norm))
    matched = scored.loc[scored["decision"] == "match", ["left", "right"]].itertuples(index=False)
    clusters = dedup.cluster(raw["record_id"], matched)
    gold = dedup.golden_records(raw, clusters)
    ins = insights.build(raw, gold, quality.run_checks(raw), scored, clusters, truth)
    assert len(ins["recommendations"]) == 5
    assert ins["duplicates"] == len(raw) - len(gold)          # re-registrations = records merged away
    assert sum(w["registrations"] for w in ins["woredas"]) <= len(raw)
    recalls = [c["recall"] for c in ins["curve"]]
    assert recalls == sorted(recalls, reverse=True)           # stricter threshold never finds more
    assert all(e["flag"] in (True, False) for e in ins["enumerators"])

# Beneficiary Deduplication & Data-Quality Pipeline

![tests](https://github.com/Nathan-TI/beneficiary-dedup-pipeline/actions/workflows/ci.yml/badge.svg)

A Python + dbt pipeline that checks registration data for quality problems, finds people who were registered more than once, and models the result into warehouse tables a programme team can query. It runs on DuckDB locally and on BigQuery. It catches duplicates even when names are spelled differently, dates of birth are mistyped, or phone numbers are written in different formats.

**[View the live report →](https://nathan-ti.github.io/beneficiary-dedup-pipeline/)** · **[Browse the dbt docs and lineage →](https://nathan-ti.github.io/beneficiary-dedup-pipeline/dbt-docs.html)**

All data is **synthetic** and no real person is represented. Because the generator knows which records belong to the same person, accuracy is **measured against ground truth** rather than estimated.

## The report: one tab for each audience

The [live report](https://nathan-ti.github.io/beneficiary-dedup-pipeline/) is rebuilt on every run, uses plain language, and works offline.

| Tab | For | What it answers |
|---|---|---|
| **Summary** | Programme management | Unique individuals, five recommended actions with responsible units, an editable savings estimate, and the reliability of the results |
| **Priority areas** | Area offices, field coordination | Weekly trend of duplicate registrations and location hotspots (shaded, filterable, downloadable) |
| **Data quality** | Information management | Most frequent errors (critical vs warning), the registration-form change that prevents each one, and data completeness |
| **Duplicates** | Data reviewers | Examples of duplicates identified, and the full manual-review queue with the reason for each case, downloadable |
| **Performance** | Management, field coordination, donors, auditors | *System:* accuracy vs exact matching, merge-threshold explorer, speed and scalability tests, quality assurance. *Enumerators:* error and duplicate rates per enumerator, with follow-up flags |
| **How it works** | Technical readers, data teams | Process overview, accepted data formats and required fields, tools, data protection |
| **Feedback** | Everyone | A short form that opens a pre-filled GitHub issue (template in `.github/ISSUE_TEMPLATE/`) |

It also has a guided 1-minute tour, a help panel with a glossary, "How to read this" notes, CSV downloads, sortable tables, shareable tab links (`#performance`), print/PDF, and dark mode.

## Speed and scale

`python -m pipeline.benchmark` runs the full matching at several sizes (results in `benchmarks/benchmark.json`):

| Registrations | Time | Per second | Correct merges | Repeats caught |
|---|---|---|---|---|
| 1,171 | 0.7 s | 1,642 | 100% | 93.1% |
| 4,748 | 2.9 s | 1,625 | 100% | 96.4% |
| 11,824 | 6.8 s | 1,743 | 99.9% | 95.9% |
| 23,790 | 14.9 s | 1,596 | 99.8% | 94.8% |

## Results (4,780 synthetic records)

| Method | Precision | Recall | F1 |
|---|---|---|---|
| Exact match on full name + date of birth | 100% | 33.0% | 49.6% |
| **This pipeline (automatic)** | **100%** | **93.5%** | **96.6%** |
| This pipeline + review queue | 100% | 95.2% | 97.5% |

- **738 duplicate registrations** merged into golden records, with **zero false merges**
- Blocking cut comparisons from **11.4 million** possible pairs to **9,749** (99.9% fewer), so a full run takes about 5 seconds
- **711 records (14.9%)** flagged by 10 data-quality rules

## Why this is harder than it looks

Ethiopian names follow a *given name + father's name + grandfather's name* pattern, so **siblings share two of their three names** and usually the same kebele and family phone. A naive fuzzy match on the full name merges different people. The generator plants these sibling look-alikes on purpose, and the matcher has explicit rules for them.

The duplicates themselves carry real-world noise:

| Problem | Example |
|---|---|
| Romanisation variants | Mohammed / Mohamed / Mohammad, Tesfaye / Tesfay, Kedija / Khadija |
| Typos | Rahel → Rhel, Samuel → Smuel |
| Date of birth errors | day and month swapped, year off by one |
| Phone formats | `0911…`, `+251911…`, `251911…`, `0911 223 344` |
| Missing fields | grandfather name, phone or ID left blank |
| Moved household | different kebele on re-registration |

## How it works

```
generate → quality checks → standardise → block → score → cluster → golden records → report
```

1. **Generate** (`pipeline/generate.py`): synthetic people, siblings, duplicates with 1–3 distortions each, plus injected data-quality defects.
2. **Quality checks** (`pipeline/quality.py`): rules for missing, invalid and implausible values, written out one row per issue in `dq_issues.csv`.
3. **Standardise** (`pipeline/normalize.py`): cleans names, builds a consonant-skeleton phonetic key (Mohammed → `mhmd`), converts phones to 9 digits and parses dates.
4. **Block** (`pipeline/dedup.py`): records are only compared if they share a key (name key, phone, national ID, DOB + name, or family names + woreda).
5. **Score**: Jaro-Winkler similarity on names, partial-credit DOB matching, phone, ID, sex and location, each weighted and averaged over the fields both records have. Domain rules then adjust the score:
   - the same national ID means a match
   - two different valid IDs are never merged
   - a first-name mismatch cuts the score (sibling protection)
   - a pair that matches on name alone, with no DOB, ID or phone match, is never auto-merged and goes to review instead
6. **Decide**: pairs scoring **≥ 0.88** are auto-merged, **0.75–0.88** go to the review queue, and anything lower is kept apart.
7. **Cluster and survive**: union-find groups the records, the most complete record survives, and its gaps are filled from the others.
8. **Evaluate and report**: pairwise precision, recall and F1, plus a self-contained HTML report.

## Analytics engineering layer (dbt)

The Python matcher writes three raw tables. dbt turns them into tested, documented warehouse models:

```
raw_records ──► stg_registrations ──► int_dq_issues ─────────────┐
match_pairs ──► stg_match_pairs ──────────────────► mart_review_queue
record_clusters ► stg_record_clusters ─► int_registrations_enriched ─► dim_beneficiary
                                                                   ├► fct_registrations ─► mart_enumerator_quality
                                                                   │                     └► mart_woreda_summary
                                                                   └► mart_dq_by_rule
```

| Model | Grain | Answers |
|---|---|---|
| `dim_beneficiary` | person | Who is each real person, with SQL survivorship (most complete record wins, contact gaps filled)? |
| `fct_registrations` | registration | Which person did each record resolve to, and what is wrong with it? |
| `mart_enumerator_quality` | enumerator | Who needs retraining: issue rate, duplicate rate, phone capture rate |
| `mart_woreda_summary` | woreda | Unique people, duplicate rate, data quality and national-ID coverage by location |
| `mart_dq_by_rule` | rule | How often each of 13 quality rules fails |
| `mart_review_queue` | pair | Borderline matches side by side for a reviewer |

- **40 nodes, 29 data tests**: uniqueness, not-null, accepted values, relationships, a custom `valid_et_mobile` generic test, and two singular tests
- One test **warns** rather than fails: it lists merged people whose registrations disagree on sex. These are correct merges where one record has a data-entry error, and the list goes to the field team for correction.
- **Cross-database macros** (`macros/cross_db.sql`) mean the same models run on DuckDB and BigQuery
- Data-quality rules are defined once, in a single list in `int_dq_issues.sql`

### Run it on BigQuery (free sandbox, no credit card)

```bash
pip install -r requirements-optional.txt
gcloud auth application-default login
python scripts/load_bigquery.py --project YOUR_PROJECT_ID
cd dbt && GCP_PROJECT=YOUR_PROJECT_ID dbt build --target bigquery --profiles-dir .
```

Sandbox tables expire after 60 days. Re-run the last two commands to rebuild.

## Optional: LLM second opinion on the review queue

`pipeline/llm_review.py` asks a large language model to judge each borderline pair from the two records, then scores those judgements against ground truth. It reports accuracy, false merges and missed duplicates, which shows how much reviewer time an LLM could realistically save.

```bash
export LLM_API_URL=https://<provider>/v1/chat/completions
export LLM_API_KEY=...
export LLM_MODEL=<model name>
python -m pipeline.llm_review --limit 100
```

## Accepted data formats

`python run_pipeline.py --input <file>` accepts:

| Format | Extensions | Notes |
|---|---|---|
| CSV / text | `.csv`, `.txt` | Comma, semicolon or tab separated (detected automatically) |
| Tab-separated | `.tsv` | |
| Excel | `.xlsx`, `.xlsm` | First sheet by default, or `--sheet "Name"`. Save older `.xls` files as `.xlsx` |
| JSON | `.json` | A list of records |
| JSON Lines | `.jsonl`, `.ndjson` | One record per line |
| Parquet | `.parquet` | Needs `pyarrow` (in `requirements-optional.txt`) |

- **Required fields:** first name, father's name, sex, date of birth.
- **Recommended fields:** grandfather's name, phone, national ID, region, zone, woreda, kebele, household size, registration date, enumerator.
- **Column names** are matched automatically, including KoboToolbox, ODK and SurveyCTO exports. For example, `First Name`, `DOB`, `Phone Number`, `Fayda ID`, `_submitted_by` and group paths such as `beneficiary/first_name` all work.
- If a required column is missing, the run stops with a clear message.
- See `templates/registration_template.csv` for the expected layout.
- Runs on your own data write to `output/` only and never overwrite the public demo report in `docs/`.

## Run it

```bash
pip install -r requirements.txt
./run_all.sh                           # pipeline + dbt build + report + dbt docs
python run_pipeline.py                 # Python part only, 4,000 synthetic people (default)
python run_pipeline.py --people 20000  # bigger run
python run_pipeline.py --input registrations.xlsx   # your own data (CSV, Excel, JSON, Parquet…)
pytest -q                              # 28 tests
```

Outputs go to `output/`:

| File | What it is |
|---|---|
| `golden_records.csv` | One row per person, with `merged_record_ids` |
| `review_queue.csv` | Borderline pairs with field-by-field similarity |
| `scored_pairs.csv` | Every candidate pair, its score and the decision |
| `dq_issues.csv` | One row per record × rule failure |
| `report.html` | The visual report (also copied to `docs/index.html`) |

## Project structure

```
pipeline/
  generate.py    synthetic data + ground truth
  quality.py     data-quality rules and completeness
  normalize.py   name, phone, sex and date standardisation
  dedup.py       blocking, scoring, clustering, golden records
  evaluate.py    pairwise precision / recall / F1
  loaders.py     reads CSV, Excel, JSON, JSON Lines and Parquet; maps column names
  insights.py    management insights and recommended actions
  benchmark.py   speed and accuracy at several data sizes
  report.py      interactive HTML report (no external assets)
  llm_review.py  optional LLM second opinion on the review queue
dbt/             staging -> intermediate -> marts, tests, cross-database macros
scripts/         load_bigquery.py
templates/       registration_template.csv
tests/           unit tests and end-to-end accuracy tests on two seeds
run_pipeline.py  Python entry point
run_all.sh       full run: Python + dbt + docs
```

## Tech

Python · pandas · RapidFuzz · dbt · DuckDB · BigQuery · SQL · LLM APIs · pytest · GitHub Actions

## Author

Nathan Tibebe, data analyst with hands-on experience in large-scale beneficiary registration, identity management and data quality. [LinkedIn](https://www.linkedin.com/in/YOUR-PROFILE)

MIT licensed.

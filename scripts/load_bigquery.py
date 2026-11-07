"""Load the pipeline's CSVs into BigQuery so the dbt project can run there.

One-time setup (BigQuery sandbox: free, no credit card):
    1. Create a project at https://console.cloud.google.com/bigquery and note its ID.
    2. Install the gcloud CLI and run:  gcloud auth application-default login
    3. pip install google-cloud-bigquery

Then:
    python scripts/load_bigquery.py --project YOUR_PROJECT_ID
    cd dbt && GCP_PROJECT=YOUR_PROJECT_ID dbt build --target bigquery --profiles-dir .

Sandbox note: tables expire after 60 days. Re-run these two commands to rebuild everything.
"""
from __future__ import annotations

import argparse
from pathlib import Path

DATASET = "raw_beneficiary"
TABLES = {
    # file name -> explicit schema (raw registrations stay all-text on purpose: cleaning happens in dbt)
    "raw_records": None,
    "match_pairs": [("record_id_a", "STRING"), ("record_id_b", "STRING"),
                    ("match_score", "FLOAT64"), ("decision", "STRING")],
    "record_clusters": [("record_id", "STRING"), ("cluster_id", "STRING")],
}


def main() -> None:
    from google.cloud import bigquery  # imported here so the rest of the repo works without it

    ap = argparse.ArgumentParser()
    ap.add_argument("--project", required=True)
    ap.add_argument("--data-dir", type=Path, default=Path("data"))
    ap.add_argument("--location", default="US")
    args = ap.parse_args()

    client = bigquery.Client(project=args.project)
    dataset = bigquery.Dataset(f"{args.project}.{DATASET}")
    dataset.location = args.location
    client.create_dataset(dataset, exists_ok=True)

    for name, schema in TABLES.items():
        path = args.data_dir / f"{name}.csv"
        if schema is None:  # every column as STRING, read from the header
            header = path.read_text(encoding="utf-8").splitlines()[0].split(",")
            schema = [(col, "STRING") for col in header]
        job_config = bigquery.LoadJobConfig(
            source_format=bigquery.SourceFormat.CSV,
            skip_leading_rows=1,
            schema=[bigquery.SchemaField(c, t) for c, t in schema],
            write_disposition=bigquery.WriteDisposition.WRITE_TRUNCATE,
            allow_quoted_newlines=True,
        )
        table_id = f"{args.project}.{DATASET}.{name}"
        with path.open("rb") as f:
            client.load_table_from_file(f, table_id, job_config=job_config).result()
        print(f"loaded {client.get_table(table_id).num_rows:,} rows -> {table_id}")


if __name__ == "__main__":
    main()

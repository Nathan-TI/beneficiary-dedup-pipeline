#!/usr/bin/env bash
# Full local run: Python matching -> dbt warehouse models + tests -> report and dbt docs.
set -euo pipefail
cd "$(dirname "$0")"
python run_pipeline.py "$@"
cd dbt
dbt build --profiles-dir .
dbt docs generate --profiles-dir . --static
cp target/static_index.html ../docs/dbt-docs.html
echo "Done. Report: docs/index.html   dbt docs: docs/dbt-docs.html"

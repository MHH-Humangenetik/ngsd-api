# ngsd-api

Async Python library for interacting with the NGSD MariaDB database.

## Features

- Async database client built on SQLAlchemy 2.0 and aiomysql
- Strong typing with dataclasses and enums
- Configuration via `.env` file (prefix: `NGSD_`)

## Installation

```bash
uv add ngsd-api
```

## Quick Start

```python
import asyncio
from ngsd_api import NgsdApi, NgsdSettings
from ngsd_api.types import RunStatus

async def main():
    settings = NgsdSettings()  # reads .env
    async with NgsdApi(settings) as api:
        runs = await api.get_runs_by_processing_system("LR-PB-SPRQ")
        for run in runs:
            print(f"{run.name} — {run.status.value}")
        await api.set_run_status_by_name("my_run", RunStatus.RUN_FINISHED)

if __name__ == "__main__":
    asyncio.run(main())
```

## Configuration

Settings are loaded from `.env` (prefix: `NGSD_`) or environment variables. Both approaches work:

```python
# Direct kwargs
settings = NgsdSettings(host="db.example.com", database="ngsd_prod")

# Or via environment variables (ideal for containers)
# NGSD_HOST=db.example.com NGSD_DATABASE=ngsd_prod uv run python script.py
```

Default `.env` example:

```
NGSD_HOST=localhost
NGSD_PORT=3306
NGSD_DATABASE=ngsd
NGSD_USER=root
NGSD_PASSWORD=
```

## API Reference

### `NgsdApi`

| Method | Description |
|--------|-------------|
| `get_runs_by_processing_system(name, status=None)` | Fetch runs filtered by processing system |
| `set_run_status_by_name(runname, status)` | Update run status |
| `get_run_by_processed_sample_name(processed_sample_name)` | Resolve a processed sample name (e.g. `"307780PR1_03"`) to its sequencing run |
| `get_sample_variants(sample_name, gene=None, min_acmg_class=None)` | Small variants detected in a sample, with ACMG class |
| `get_samples_with_variant(chr, start, end, ref, obs)` | Samples carrying a specific variant, with genotype |
| `search_variants_by_gene(gene_symbol, sample_name=None)` | Variants overlapping a gene's coding region |
| `get_sample_phenotype(sample_name)` | A sample's disease group/status and HPO/OMIM/Orpha/ICD10 entries |
| `get_variant_classification(chr, start, end, ref, obs)` | ACMG class, rationale, and linked PubMed IDs for a variant |
| `get_sample_structural_variants(sample_name, sv_type="all")` | CNVs/SVs/repeat expansions detected in a sample |
| `get_report_findings(sample_name)` | Diagnostic report findings (causal/candidate/incidental) for a sample |

All read methods above are read-only (`SELECT` only, parameterized, never
raw SQL) and never select patient-identifying columns (`patient_identifier`,
`name_external`, `year_of_birth`, sender/receiver) or free-text comment
fields, except `variant_classification.comment` (the ACMG rationale, which
is the entire point of `get_variant_classification`). `tests/test_no_pii.py`
statically guards this. A least-privilege, read-only NGSD DB user is still
the real enforcement — these guardrails are defense in depth, not a
substitute for DB-level grants.

## CLI Tool

A development CLI (`main.py`) is included for querying and updating runs:

```bash
uv run main.py get-runs-by-processing-system --system LR-PB-SPRQ  # lists all runs for the specified processing system
uv run main.py get-runs-by-processing-system --system LR-PB-SPRQ --status run_finished  # lists only finished runs
uv run main.py set-run-status-by-name --runname my_run --status run_finished  # sets the status of 'my_run' to 'run_finished'
```

## Tooling

```bash
uv run ruff check src/ main.py   # lint
uv run ruff format src/ main.py  # format
uv build                          # build package
```

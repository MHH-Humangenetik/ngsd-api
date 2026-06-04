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

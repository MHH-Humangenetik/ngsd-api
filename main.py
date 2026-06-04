import asyncio
from functools import wraps

import click
from rich.console import Console
from rich.status import Status
from rich.table import Table

from ngsd_api import NgsdApi, NgsdSettings
from ngsd_api.types import RunStatus

console = Console()


def _status_choices() -> list[str]:
    return [s.value for s in RunStatus]


def _status_callback(ctx: click.Context, param: click.Parameter, value: str | None) -> RunStatus | None:
    if value is None:
        return None
    for s in RunStatus:
        if s.value == value:
            return s
    raise click.BadParameter(f"Invalid status '{value}'. Valid values: {', '.join(_status_choices())}")


def _async_command(f):
    """Wrap an async Click command to ensure it gets awaited."""
    @wraps(f)
    @click.pass_context
    def wrapper(ctx, *args, **kwargs):
        return asyncio.run(f(*args, **kwargs))
    return wrapper


@click.group()
def cli() -> None:
    """NGSD API development CLI."""
    pass


@cli.command()
@click.option("--system", required=True, help="Processing system name (e.g. LR-PB-SPRQ)")
@click.option("--status", help="Filter by run status", type=click.Choice(_status_choices()), callback=_status_callback)
@_async_command
async def get_runs_by_processing_system(system: str, status: RunStatus | None) -> None:
    """List runs by processing system."""
    settings = NgsdSettings()
    with Status("Getting runs..."):
        async with NgsdApi(settings) as api:
            runs = await api.get_runs_by_processing_system(system, status)

    table = Table(title=f"Runs for '{system}'")
    table.add_column("Name", style="cyan")
    table.add_column("Status", style="magenta")

    for run in runs:
        table.add_row(run.name, run.status.value)

    if not runs:
        console.print("[yellow]No runs found.[/yellow]")
    else:
        if status is not None:
            table.caption = f"[dim]{len(runs)} run(s)[/dim] - filtered by: {status.value}"
        else:
            table.caption = f"[dim]{len(runs)} run(s)[/dim]"
        console.print(table)


@cli.command()
@click.option("--runname", required=True, help="Run name to update")
@click.option("--status", required=True, help="New status", type=click.Choice(_status_choices()))
@_async_command
async def set_run_status_by_name(runname: str, status: str) -> None:
    """Update a run's status."""
    run_status = RunStatus(status)
    settings = NgsdSettings()
    with Status("Updating run status..."):
        async with NgsdApi(settings) as api:
            updated = await api.set_run_status_by_name(runname, run_status)

    if updated:
        console.print(f"[green]✓ Updated '{runname}' to {status}[/green]")
    else:
        console.print(f"[red]✗ Run '{runname}' not found[/red]")


if __name__ == "__main__":
    cli()

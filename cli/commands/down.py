"""workbench down — stop running services."""

from __future__ import annotations

from pathlib import Path
from typing import Optional

import typer
from rich.console import Console

from cli.utils.process import ProcessManager

console = Console()


def down_cmd(
    service: Optional[str] = typer.Argument(None, help="Service to stop (omit for all)."),
) -> None:
    """Stop running services."""
    from cli.main import banner, state
    from cli.utils.config import find_workbench_yaml

    banner()

    workbench_root = find_workbench_yaml().parent
    running = ProcessManager.read_pid_files(workbench_root)

    if not running:
        console.print("  [dim]No services are currently running.[/dim]\n")
        return

    if service:
        if service not in running:
            console.print(f"  [dim]{service} is not running.[/dim]\n")
            return
        targets = {service: running[service]}
    else:
        targets = running

    console.print("  [bold]→[/bold] Stopping services...\n")

    for name in targets:
        stopped = ProcessManager.kill_by_pid_file(workbench_root, name)
        if stopped:
            console.print(f"    [green]✓[/green] {name:<20} stopped")
        else:
            console.print(f"    [yellow]○[/yellow] {name:<20} [dim]already stopped[/dim]")

    console.print()

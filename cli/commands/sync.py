"""workbench sync — pull latest changes for all repos."""

from __future__ import annotations

import time
from pathlib import Path

import typer
from rich.console import Console

from cli.utils import git

console = Console()


def sync_cmd() -> None:
    """Pull latest changes for all repos."""
    from cli.main import banner, state
    from cli.utils.config import load_config, find_workbench_yaml

    banner()

    config = load_config()
    workbench_root = find_workbench_yaml().parent

    if not config.repos:
        console.print("  [yellow]No repos defined in workbench.yaml[/yellow]\n")
        raise typer.Exit(1)

    console.print("  [bold]→[/bold] Pulling latest for all repos...\n")

    start_time = time.monotonic()
    success = 0
    errors = 0

    for name, repo_cfg in config.repos.items():
        rel_path = repo_cfg.path or f"repos/{name}"
        repo_path = workbench_root / rel_path

        if not repo_path.exists():
            console.print(f"    [dim]○[/dim] {name:<20} [dim]not cloned — skipped[/dim]")
            continue

        if state.verbose:
            console.print(f"    [dim]  git pull in {rel_path}[/dim]")

        result = git.pull(repo_path)

        if result.returncode == 0:
            output = result.stdout.strip()
            if "Already up to date" in output:
                console.print(f"    [green]✓[/green] {name:<20} [dim]already up to date[/dim]")
            else:
                console.print(f"    [green]✓[/green] {name:<20} updated")
            success += 1
        else:
            errors += 1
            stderr = result.stderr.strip()
            if "conflict" in stderr.lower():
                console.print(f"    [red]✗[/red] {name:<20} [red]merge conflict[/red]")
                console.print(f"      [dim]Resolve conflicts in {rel_path} and commit[/dim]")
            elif "no tracking information" in stderr.lower():
                console.print(
                    f"    [yellow]○[/yellow] {name:<20} [yellow]no upstream tracking branch[/yellow]"
                )
            else:
                console.print(f"    [red]✗[/red] {name:<20} [red]pull failed[/red]")
                if state.verbose:
                    console.print(f"      [dim]{stderr}[/dim]")

    elapsed = time.monotonic() - start_time
    console.print()

    if not state.quiet:
        parts = []
        if success:
            parts.append(f"[green]{success} synced[/green]")
        if errors:
            parts.append(f"[red]{errors} failed[/red]")
        console.print(f"  {' · '.join(parts)} [dim]in {elapsed:.1f}s[/dim]\n")

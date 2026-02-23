"""workbench add — interactively add a new repo to the workbench."""

from __future__ import annotations

import subprocess
from pathlib import Path

import typer
from rich.console import Console
from rich.prompt import Prompt, Confirm

console = Console()


def add_cmd(
    url: str = typer.Argument(None, help="Git clone URL for the new repo."),
    name: str = typer.Option(None, "--name", "-n", help="Logical name for the repo (defaults to repo name)."),
    description: str = typer.Option(None, "--desc", "-d", help="Short description of the repo."),
    infrastructure: bool = typer.Option(False, "--infrastructure", "--infra", "-i", help="Mark as infrastructure-only (never started)."),
) -> None:
    """Add a new repo to the workbench."""
    from cli.main import banner, state
    from cli.utils.config import load_config, save_config, find_workbench_yaml, RepoConfig

    banner()

    config = load_config()
    workbench_root = find_workbench_yaml().parent

    # Interactive prompts for missing values
    if not url:
        url = Prompt.ask("  [bold]Git URL[/bold]")
        if not url:
            console.print("  [red]✗[/red] Git URL is required.\n")
            raise typer.Exit(1)

    # Derive name from URL if not provided
    if not name:
        default_name = url.rstrip("/").split("/")[-1].replace(".git", "")
        name = Prompt.ask("  [bold]Name[/bold]", default=default_name)

    if name in config.repos:
        console.print(f"  [red]✗[/red] Repo [bold]{name}[/bold] already exists in workbench.yaml.\n")
        raise typer.Exit(1)

    if not description:
        description = Prompt.ask("  [bold]Description[/bold]", default="")

    if not infrastructure:
        infrastructure = Confirm.ask("  [bold]Infrastructure only?[/bold] (reference repo, never started)", default=False)

    # Determine path
    repo_dir_name = url.rstrip("/").split("/")[-1].replace(".git", "")
    repo_path = f"repos/{repo_dir_name}"
    abs_repo_path = workbench_root / repo_path

    console.print()

    # Clone
    if abs_repo_path.exists():
        console.print(f"  [yellow]○[/yellow] {name:20s} already cloned → {repo_path}")
    else:
        console.print(f"  [dim]…[/dim] {name:20s} cloning...")
        result = subprocess.run(
            ["git", "clone", url, str(abs_repo_path)],
            capture_output=True, text=True,
        )
        if result.returncode != 0:
            console.print(f"  [red]✗[/red] {name:20s} clone failed")
            console.print(f"    [dim]{result.stderr.strip()}[/dim]\n")
            raise typer.Exit(1)
        console.print(f"  [green]✓[/green] {name:20s} cloned → {repo_path}")

    # Add to config
    repo = RepoConfig(
        name=name,
        url=url,
        path=repo_path,
        description=description,
        type="infrastructure" if infrastructure else "service",
    )
    config.repos[name] = repo
    save_config(config)
    console.print(f"  [green]✓[/green] {name:20s} added to workbench.yaml")

    # Run discover on the new repo
    console.print()
    console.print("  [bold]→[/bold] Running discovery...")

    try:
        from cli.commands.discover import _discover_repo, _merge_discovered
        repo_path = workbench_root / repo.path
        log: dict[str, str] = {}
        discovered = _discover_repo(repo_path, repo, log)
        _merge_discovered(repo, discovered)
        save_config(config)

        parts = []
        if repo.language:
            parts.append(repo.language)
        if repo.framework:
            parts.append(repo.framework)
        if repo.port:
            parts.append(f"port {repo.port}")
        if repo.is_infrastructure:
            parts.append("infrastructure")

        summary = " · ".join(parts) if parts else "detected"
        console.print(f"  [green]✓[/green] {name:20s} {summary}")
    except Exception:
        console.print(f"  [yellow]○[/yellow] {name:20s} discovery skipped")

    console.print()
    console.print(f"  [dim]Run [bold]workbench status[/bold] to see all repos.[/dim]\n")

"""workbench push — push changes for one or all repos."""

from __future__ import annotations

from pathlib import Path
from typing import Optional

import typer
from rich.console import Console
from rich.prompt import Prompt

from cli.utils import git
from cli.utils.config import RepoConfig

console = Console()


def push_cmd(
    repo: Optional[str] = typer.Argument(None, help="Repo to push (omit to choose interactively)."),
    all_repos: bool = typer.Option(False, "--all", "-a", help="Push all repos with commits ahead."),
) -> None:
    """Push changes for one or all repos."""
    from cli.main import banner, state
    from cli.utils.config import load_config, find_workbench_yaml

    banner()

    config = load_config()
    workbench_root = find_workbench_yaml().parent

    if repo:
        if repo not in config.repos:
            console.print(f"\n  [red]✗[/red] Unknown repo: [bold]{repo}[/bold]")
            console.print(f"  [dim]Available: {', '.join(config.repos.keys())}[/dim]\n")
            raise typer.Exit(1)
        _push_single(repo, config.repos[repo], workbench_root, state.verbose)
        return

    # Show status of all repos
    pushable: list[str] = []
    console.print("  [bold]→[/bold] Repository status:\n")

    for name, repo_cfg in config.repos.items():
        rel_path = repo_cfg.path or f"repos/{name}"
        repo_path = workbench_root / rel_path

        if not repo_path.exists():
            console.print(f"    [dim]○[/dim] {name:<20} [dim]not cloned[/dim]")
            continue

        info = git.get_status_summary(repo_path)
        branch = info["branch"]

        if info["dirty"]:
            console.print(
                f"    [yellow]●[/yellow] {name:<20} [cyan]{branch}[/cyan]  "
                f"[yellow]{info['modified_count']} uncommitted[/yellow]"
            )
        elif info["ahead"]:
            console.print(
                f"    [green]↑[/green] {name:<20} [cyan]{branch}[/cyan]  "
                f"[green]{info['ahead']} ahead[/green]"
            )
            pushable.append(name)
        else:
            console.print(
                f"    [dim]✓[/dim] {name:<20} [cyan]{branch}[/cyan]  [dim]up to date[/dim]"
            )

    console.print()

    if not pushable:
        console.print("  [dim]Nothing to push.[/dim]\n")
        return

    if all_repos:
        targets = pushable
    else:
        choices = ", ".join(pushable)
        console.print(f"  [dim]Repos with commits to push: {choices}[/dim]")
        answer = Prompt.ask(
            "\n  Push which repo?",
            choices=[*pushable, "all", "none"],
            default="none",
        )
        if answer == "none":
            console.print("  [dim]Aborted.[/dim]\n")
            return
        targets = pushable if answer == "all" else [answer]

    console.print("\n  [bold]→[/bold] Pushing...\n")
    for name in targets:
        _push_single(name, config.repos[name], workbench_root, state.verbose)


def _push_single(name: str, repo_cfg: RepoConfig, root: Path, verbose: bool) -> None:
    """Push a single repo."""
    rel_path = repo_cfg.path or f"repos/{name}"
    repo_path = root / rel_path

    if not repo_path.exists():
        console.print(f"    [red]✗[/red] {name:<20} not cloned")
        return

    info = git.get_status_summary(repo_path)
    if info["dirty"]:
        console.print(
            f"    [yellow]![/yellow] {name:<20} has uncommitted changes — pushing anyway"
        )

    result = git.push_repo(repo_path)
    if result.returncode == 0:
        console.print(f"    [green]✓[/green] {name:<20} pushed")
    else:
        console.print(f"    [red]✗[/red] {name:<20} push failed")
        if verbose and result.stderr:
            console.print(f"      [dim]{result.stderr.strip()}[/dim]")

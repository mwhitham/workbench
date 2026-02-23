"""workbench init — scaffold a new workbench or clone repos for an existing one."""

from __future__ import annotations

import importlib.resources
import shutil
import subprocess
import time
from pathlib import Path

import typer
from rich.console import Console
from rich.prompt import Prompt

from cli.utils import git

console = Console()


def init_cmd() -> None:
    """Clone all repos defined in workbench.yaml, or scaffold a new workbench."""
    from cli.main import banner, state

    banner()

    try:
        from cli.utils.config import find_workbench_yaml
        find_workbench_yaml()
        _init_existing(state)
    except FileNotFoundError:
        _scaffold_new(state)


def _scaffold_new(state: object) -> None:
    """Create a new workbench project in the current directory."""
    cwd = Path.cwd()

    console.print("  [bold yellow]No workbench.yaml found.[/bold yellow] Creating a new workbench...\n")

    project_name = Prompt.ask("  [bold]Project name[/bold]", default=cwd.name)

    scaffold_dir = Path(__file__).parent.parent / "scaffold"
    if not scaffold_dir.exists():
        console.print("  [red]✗[/red] Scaffold templates not found. Is the workbench package installed correctly?\n")
        raise typer.Exit(1)

    created: list[str] = []

    config_dest = cwd / "workbench.yaml"
    _copy_template(scaffold_dir / "workbench.yaml", config_dest, project_name)
    created.append("workbench.yaml")

    claude_dest = cwd / "CLAUDE.md"
    if not claude_dest.exists():
        _copy_template(scaffold_dir / "CLAUDE.md", claude_dest, project_name)
        created.append("CLAUDE.md")

    gitignore_dest = cwd / ".gitignore"
    if not gitignore_dest.exists():
        _copy_template(scaffold_dir / "gitignore", gitignore_dest, project_name)
        created.append(".gitignore")

    docs_src = scaffold_dir / "docs"
    docs_dest = cwd / "docs"
    if docs_src.exists():
        for src_file in sorted(docs_src.rglob("*")):
            if src_file.is_file():
                rel = src_file.relative_to(docs_src)
                dest_file = docs_dest / rel
                if not dest_file.exists():
                    dest_file.parent.mkdir(parents=True, exist_ok=True)
                    _copy_template(src_file, dest_file, project_name)
                    created.append(f"docs/{rel}")

    repos_dir = cwd / "repos"
    repos_dir.mkdir(exist_ok=True)
    gitkeep = repos_dir / ".gitkeep"
    if not gitkeep.exists():
        gitkeep.touch()
        created.append("repos/.gitkeep")

    console.print()
    console.print("  [bold green]Created:[/bold green]\n")
    for f in created:
        console.print(f"    [green]✓[/green] {f}")

    console.print()
    console.print("  [bold]Next steps:[/bold]")
    console.print("    1. Add repos:      [cyan]workbench add <git-url>[/cyan]")
    console.print("    2. Check status:   [cyan]workbench status[/cyan]")
    console.print("    3. Start services: [cyan]workbench up[/cyan]")
    console.print()


def _copy_template(src: Path, dest: Path, project_name: str) -> None:
    """Copy a scaffold template, replacing {project_name} placeholders."""
    content = src.read_text()
    content = content.replace("{project_name}", project_name)
    dest.parent.mkdir(parents=True, exist_ok=True)
    dest.write_text(content)


def _init_existing(state: object) -> None:
    """Clone all repos defined in workbench.yaml and run discovery."""
    from cli.utils.config import load_config, find_workbench_yaml

    config = load_config()
    workbench_root = find_workbench_yaml().parent

    if not config.repos:
        console.print("  [yellow]No repos defined in workbench.yaml.[/yellow]")
        console.print("  Run [bold cyan]workbench add <git-url>[/bold cyan] to add a repo.\n")
        return

    console.print("  [bold]→[/bold] Cloning repositories...\n")

    start_time = time.monotonic()
    cloned = 0
    skipped = 0

    for name, repo_cfg in config.repos.items():
        url = repo_cfg.url
        rel_path = repo_cfg.path or f"repos/{name}"
        dest = workbench_root / rel_path

        if dest.exists() and any(dest.iterdir()):
            if not state.quiet:
                console.print(f"    [green]✓[/green] {name:<20} [dim]already cloned → {rel_path}[/dim]")
            skipped += 1
            continue

        if not url:
            console.print(f"    [yellow]○[/yellow] {name:<20} [dim]no URL configured — skipped[/dim]")
            continue

        if state.verbose:
            console.print(f"    [dim]  git clone {url} {dest}[/dim]")

        try:
            dest.parent.mkdir(parents=True, exist_ok=True)
            git.clone(url, dest)
            console.print(f"    [green]✓[/green] {name:<20} [dim]cloned → {rel_path}[/dim]")
            cloned += 1
        except subprocess.CalledProcessError as exc:
            console.print(f"    [red]✗[/red] {name:<20} [red]clone failed[/red]")
            if state.verbose and exc.stderr:
                console.print(f"      [dim]{exc.stderr.strip()}[/dim]")

    elapsed = time.monotonic() - start_time

    console.print("\n  [bold]→[/bold] Installing dependencies...\n")

    for name, repo_cfg in config.repos.items():
        rel_path = repo_cfg.path or f"repos/{name}"
        dest = workbench_root / rel_path

        if not dest.exists():
            continue

        installed = _install_deps(dest, name, state.verbose)
        if installed:
            console.print(f"    [green]✓[/green] {name:<20} [dim]dependencies installed[/dim]")
        else:
            console.print(f"    [dim]○[/dim] {name:<20} [dim]no dependency file detected[/dim]")

    console.print("\n  [bold]→[/bold] Running discovery...\n")

    try:
        from cli.commands.discover import discover
        discover(repo=None, dry_run=False, verbose=state.verbose, quiet=state.quiet)
    except (ImportError, Exception):
        result = subprocess.run(
            ["workbench", "discover"],
            capture_output=True,
            text=True,
        )
        if result.returncode != 0 and state.verbose:
            console.print(f"    [dim]Discovery skipped (command not available yet)[/dim]")

    console.print()
    if not state.quiet:
        parts = []
        if cloned:
            parts.append(f"{cloned} cloned")
        if skipped:
            parts.append(f"{skipped} already present")
        summary = ", ".join(parts) if parts else "nothing to clone"
        console.print(f"  [dim]{summary} in {elapsed:.1f}s[/dim]")
    console.print(
        "\n  All systems ready. Run [bold cyan]workbench up[/bold cyan] to start.\n"
    )


def _install_deps(repo_path: Path, name: str, verbose: bool) -> bool:
    """Attempt to install dependencies for a repo. Returns True if something was installed."""
    if (repo_path / "package.json").exists():
        lock = "package-lock.json" if (repo_path / "package-lock.json").exists() else None
        cmd = "npm ci" if lock else "npm install"
        if (repo_path / "yarn.lock").exists():
            cmd = "yarn install"
        if (repo_path / "pnpm-lock.yaml").exists():
            cmd = "pnpm install"
        _run_install(cmd, repo_path, verbose)
        return True

    if (repo_path / "requirements.txt").exists():
        _run_install("pip install -r requirements.txt", repo_path, verbose)
        return True

    if (repo_path / "pyproject.toml").exists():
        _run_install("pip install -e .", repo_path, verbose)
        return True

    return False


def _run_install(cmd: str, cwd: Path, verbose: bool) -> None:
    """Run an install command, suppressing output unless verbose."""
    result = subprocess.run(
        cmd,
        shell=True,
        cwd=cwd,
        capture_output=not verbose,
        text=True,
    )
    if result.returncode != 0 and verbose:
        console.print(f"      [dim]install exited with code {result.returncode}[/dim]")

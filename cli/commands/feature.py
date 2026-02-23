"""workbench feature — cross-repo feature branch workflow."""

from __future__ import annotations

import shutil
import subprocess
from collections import defaultdict
from datetime import date
from pathlib import Path
from typing import Optional

import typer
from rich.console import Console
from rich.prompt import Confirm, Prompt

from cli.utils import git
from cli.utils.config import load_config, find_workbench_yaml, RepoConfig

console = Console()
feature_app = typer.Typer(name="feature", help="Cross-repo feature workflow.")


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------

def _get_app_repos(config, workbench_root: Path) -> dict[str, tuple[RepoConfig, Path]]:
    """Return non-infrastructure repos that are cloned."""
    repos: dict[str, tuple[RepoConfig, Path]] = {}
    for name, repo_cfg in config.repos.items():
        if repo_cfg.is_infrastructure:
            continue
        rel_path = repo_cfg.path or f"repos/{name}"
        repo_path = workbench_root / rel_path
        if repo_path.exists():
            repos[name] = (repo_cfg, repo_path)
    return repos


def _detect_feature_from(paths: dict[str, Path]) -> str | None:
    """Auto-detect the current feature by finding feat/* branches across paths.

    *paths* maps a label (repo name or "workbench") to a directory.
    """
    feature_branches: dict[str, list[str]] = defaultdict(list)
    for name, path in paths.items():
        branch = git.current_branch(path)
        if branch.startswith("feat/"):
            feature_branches[branch].append(name)

    if not feature_branches:
        return None
    if len(feature_branches) == 1:
        return next(iter(feature_branches))

    # Multiple features — pick the one present in the most repos
    console.print("\n  [yellow]Multiple feature branches detected:[/yellow]\n")
    sorted_features = sorted(feature_branches.items(), key=lambda x: len(x[1]), reverse=True)
    for i, (branch, repo_names) in enumerate(sorted_features, 1):
        console.print(f"    {i}. [cyan]{branch}[/cyan]  ({', '.join(repo_names)})")
    console.print()
    choice = Prompt.ask(
        "  Which feature?",
        choices=[str(i) for i in range(1, len(sorted_features) + 1)],
        default="1",
    )
    return sorted_features[int(choice) - 1][0]


def _detect_feature(repos: dict[str, tuple[RepoConfig, Path]], workbench_root: Path | None = None) -> str | None:
    """Auto-detect the current feature across app repos (and optionally workbench root)."""
    paths: dict[str, Path] = {}
    if workbench_root:
        paths["workbench"] = workbench_root
    for name, (_cfg, path) in repos.items():
        paths[name] = path
    return _detect_feature_from(paths)


def _branch_name(name: str) -> str:
    """Build the feature branch name from a feature name."""
    if name.startswith("feat/"):
        return name
    return f"feat/{name}"


def _feature_label(branch: str) -> str:
    """Extract the human label from a branch name."""
    return branch.removeprefix("feat/")


# ---------------------------------------------------------------------------
# Commands
# ---------------------------------------------------------------------------

@feature_app.command("start")
def start_cmd(
    name: str = typer.Argument(..., help="Feature name (e.g. new-health-goal)."),
    repos: Optional[str] = typer.Option(
        None, "--repos", "-r",
        help="Comma-separated list of repos to include (default: all non-infrastructure).",
    ),
    spec: bool = typer.Option(
        False, "--spec", "-s",
        help="Create a feature spec from the template.",
    ),
) -> None:
    """Create a feature branch across repos."""
    from cli.main import banner

    banner()

    config = load_config()
    workbench_root = find_workbench_yaml().parent
    all_repos = _get_app_repos(config, workbench_root)

    # Filter to requested repos
    if repos:
        requested = [r.strip() for r in repos.split(",")]
        missing = [r for r in requested if r not in all_repos]
        if missing:
            console.print(f"\n  [red]✗[/red] Unknown repos: {', '.join(missing)}")
            console.print(f"  [dim]Available: {', '.join(all_repos.keys())}[/dim]\n")
            raise typer.Exit(1)
        target_repos = {k: v for k, v in all_repos.items() if k in requested}
    else:
        target_repos = all_repos

    if not target_repos:
        console.print("\n  [red]✗[/red] No repos available.\n")
        raise typer.Exit(1)

    branch = _branch_name(name)

    console.print(f"\n  [bold]→[/bold] Creating feature branches: [cyan]{branch}[/cyan]\n")

    # Check for dirty repos (including workbench itself)
    dirty_names: list[str] = []
    if git.is_dirty(workbench_root):
        dirty_names.append("workbench")
    dirty_names.extend(n for n, (_c, p) in target_repos.items() if git.is_dirty(p))
    if dirty_names:
        console.print(f"  [yellow]![/yellow] Dirty repos: {', '.join(dirty_names)}")
        if not Confirm.ask("  Continue anyway?", default=True):
            console.print("  [dim]Aborted.[/dim]\n")
            raise typer.Exit(0)
        console.print()

    # Create branch in workbench root first (for shell prompt)
    wb_default = git.get_default_branch(workbench_root)
    wb_result = git.create_branch(workbench_root, branch)
    if wb_result.returncode == 0:
        console.print(
            f"    [green]✓[/green] {'workbench':<20} [cyan]{branch}[/cyan] "
            f"[dim](from {wb_default})[/dim]"
        )
    else:
        err = wb_result.stderr.strip()
        console.print(f"    [red]✗[/red] {'workbench':<20} {err}")

    # Create branches in app repos
    for repo_name, (_cfg, repo_path) in target_repos.items():
        default_branch = git.get_default_branch(repo_path)
        result = git.create_branch(repo_path, branch)
        if result.returncode == 0:
            console.print(
                f"    [green]✓[/green] {repo_name:<20} [cyan]{branch}[/cyan] "
                f"[dim](from {default_branch})[/dim]"
            )
        else:
            err = result.stderr.strip()
            console.print(f"    [red]✗[/red] {repo_name:<20} {err}")

    # Create feature spec if requested
    if spec:
        template_path = workbench_root / "templates" / "feature-spec-template.md"
        spec_dir = workbench_root / "docs" / "features"
        spec_dir.mkdir(parents=True, exist_ok=True)
        spec_path = spec_dir / f"{_feature_label(branch)}.md"
        if template_path.exists():
            content = template_path.read_text()
            content = content.replace("[Feature Name]", _feature_label(branch))
            content = content.replace("YYYY-MM-DD", date.today().isoformat())
            spec_path.write_text(content)
            console.print(f"\n    [green]✓[/green] Feature spec: docs/features/{spec_path.name}")
        else:
            console.print("\n    [yellow]![/yellow] Template not found, skipping spec.")

    console.print("\n  Feature ready. Start building!\n")


@feature_app.command("status")
def status_cmd() -> None:
    """Show the state of the current feature across all repos."""
    from cli.main import banner

    banner()

    config = load_config()
    workbench_root = find_workbench_yaml().parent
    all_repos = _get_app_repos(config, workbench_root)

    if not all_repos:
        console.print("\n  [red]✗[/red] No repos available.\n")
        raise typer.Exit(1)

    feature = _detect_feature(all_repos, workbench_root)
    if not feature:
        console.print("\n  [dim]No feature branch detected in any repo.[/dim]\n")
        raise typer.Exit(0)

    console.print(f"\n  [bold]Feature:[/bold] [cyan]{feature}[/cyan]\n")

    def _print_repo_status(name: str, repo_path: Path) -> None:
        branch = git.current_branch(repo_path)
        if branch == feature:
            default_branch = git.get_default_branch(repo_path)
            ahead = git.commits_ahead_of(repo_path, default_branch)
            modified = git.get_modified_count(repo_path)

            parts = []
            if ahead:
                parts.append(f"{ahead} commit{'s' if ahead != 1 else ''}")
            if modified:
                parts.append(f"{modified} modified")
            else:
                parts.append("clean")
            detail = " · ".join(parts)

            console.print(
                f"    {name:<20} [cyan]{branch}[/cyan]   {detail}"
            )
        else:
            console.print(
                f"    {name:<20} [dim]{branch}[/dim]"
                f"   [dim]○ not on feature branch[/dim]"
            )

    _print_repo_status("workbench", workbench_root)
    for repo_name, (_cfg, repo_path) in all_repos.items():
        _print_repo_status(repo_name, repo_path)

    console.print()


@feature_app.command("push")
def push_cmd() -> None:
    """Push all repos that are on the feature branch."""
    from cli.main import banner

    banner()

    config = load_config()
    workbench_root = find_workbench_yaml().parent
    all_repos = _get_app_repos(config, workbench_root)

    feature = _detect_feature(all_repos, workbench_root)
    if not feature:
        console.print("\n  [dim]No feature branch detected.[/dim]\n")
        raise typer.Exit(0)

    console.print(f"\n  [bold]→[/bold] Pushing repos on [cyan]{feature}[/cyan]\n")

    pushed_any = False
    for repo_name, (_cfg, repo_path) in all_repos.items():
        branch = git.current_branch(repo_path)
        if branch != feature:
            console.print(f"    [dim]○[/dim] {repo_name:<20} [dim]skipped (not on feature branch)[/dim]")
            continue

        default_branch = git.get_default_branch(repo_path)
        ahead = git.commits_ahead_of(repo_path, default_branch)
        if ahead == 0 and not git.has_remote_branch(repo_path, branch):
            console.print(f"    [dim]○[/dim] {repo_name:<20} [dim]skipped (no commits ahead)[/dim]")
            continue

        result = git.push_with_upstream(repo_path)
        if result.returncode == 0:
            console.print(f"    [green]✓[/green] {repo_name:<20} pushed")
            pushed_any = True
        else:
            err = result.stderr.strip()
            console.print(f"    [red]✗[/red] {repo_name:<20} push failed: {err}")

    if not pushed_any:
        console.print("\n  [dim]Nothing to push.[/dim]")

    console.print()


@feature_app.command("pr")
def pr_cmd(
    title: Optional[str] = typer.Option(None, "--title", "-t", help="PR title (auto-generated from feature name if omitted)."),
    body: Optional[str] = typer.Option(None, "--body", "-b", help="PR body text."),
    draft: bool = typer.Option(False, "--draft", "-d", help="Create draft PRs."),
) -> None:
    """Create pull requests for each repo on the feature branch."""
    from cli.main import banner

    banner()

    # Check for gh CLI
    if not shutil.which("gh"):
        console.print("\n  [red]✗[/red] GitHub CLI (gh) is not installed.")
        console.print("  [dim]Install it: https://cli.github.com[/dim]\n")
        raise typer.Exit(1)

    config = load_config()
    workbench_root = find_workbench_yaml().parent
    all_repos = _get_app_repos(config, workbench_root)

    feature = _detect_feature(all_repos, workbench_root)
    if not feature:
        console.print("\n  [dim]No feature branch detected.[/dim]\n")
        raise typer.Exit(0)

    pr_title = title or feature.removeprefix("feat/").replace("-", " ").title()

    console.print(f"\n  [bold]→[/bold] Creating pull requests for [cyan]{feature}[/cyan]\n")

    # First pass: create PRs
    created_prs: dict[str, str] = {}  # repo_name -> PR URL

    for repo_name, (_cfg, repo_path) in all_repos.items():
        branch = git.current_branch(repo_path)
        if branch != feature:
            console.print(f"    [dim]○[/dim] {repo_name:<20} [dim]skipped (not on feature branch)[/dim]")
            continue

        if not git.has_remote_branch(repo_path, branch):
            console.print(f"    [dim]○[/dim] {repo_name:<20} [dim]skipped (not pushed to remote)[/dim]")
            continue

        cmd = ["gh", "pr", "create", "--title", pr_title]
        if body:
            cmd.extend(["--body", body])
        else:
            cmd.extend(["--body", f"Part of cross-repo feature: **{feature}**"])
        if draft:
            cmd.append("--draft")

        result = subprocess.run(
            cmd, cwd=repo_path, capture_output=True, text=True,
        )
        if result.returncode == 0:
            pr_url = result.stdout.strip()
            created_prs[repo_name] = pr_url
            console.print(f"    [green]✓[/green] {repo_name:<20} {pr_url}")
        else:
            err = result.stderr.strip()
            # gh returns non-zero if PR already exists
            if "already exists" in err:
                # Try to get existing PR URL
                view_result = subprocess.run(
                    ["gh", "pr", "view", "--json", "url", "-q", ".url"],
                    cwd=repo_path, capture_output=True, text=True,
                )
                if view_result.returncode == 0:
                    pr_url = view_result.stdout.strip()
                    created_prs[repo_name] = pr_url
                    console.print(f"    [yellow]●[/yellow] {repo_name:<20} already exists: {pr_url}")
                else:
                    console.print(f"    [yellow]●[/yellow] {repo_name:<20} PR already exists")
            else:
                console.print(f"    [red]✗[/red] {repo_name:<20} failed: {err}")

    # Second pass: update each PR body with cross-links
    if len(created_prs) > 1:
        console.print()
        for repo_name, pr_url in created_prs.items():
            (_cfg, repo_path) = all_repos[repo_name]
            sibling_links = "\n".join(
                f"- **{other}**: {url}"
                for other, url in created_prs.items()
                if other != repo_name
            )
            updated_body = body or f"Part of cross-repo feature: **{feature}**"
            updated_body += f"\n\n### Related PRs\n\n{sibling_links}"

            subprocess.run(
                ["gh", "pr", "edit", pr_url, "--body", updated_body],
                cwd=repo_path, capture_output=True, text=True,
            )

        console.print("  Cross-repo PR links added to descriptions.")

    console.print()


@feature_app.command("finish")
def finish_cmd() -> None:
    """Switch all repos back to their default branch and optionally clean up."""
    from cli.main import banner

    banner()

    config = load_config()
    workbench_root = find_workbench_yaml().parent
    all_repos = _get_app_repos(config, workbench_root)

    feature = _detect_feature(all_repos, workbench_root)
    if not feature:
        console.print("\n  [dim]No feature branch detected.[/dim]\n")
        raise typer.Exit(0)

    console.print(f"\n  [bold]→[/bold] Finishing feature [cyan]{feature}[/cyan]\n")

    # Build the full list: workbench + app repos
    all_paths: list[tuple[str, Path]] = [("workbench", workbench_root)]
    all_paths.extend((name, path) for name, (_cfg, path) in all_repos.items())

    # Switch repos back to default branch
    switched: list[tuple[str, Path]] = []
    for repo_name, repo_path in all_paths:
        branch = git.current_branch(repo_path)
        if branch != feature:
            console.print(f"    [dim]○[/dim] {repo_name:<20} [dim]already on {branch}[/dim]")
            continue

        default_branch = git.get_default_branch(repo_path)
        result = git.checkout(repo_path, default_branch)
        if result.returncode == 0:
            console.print(f"    [green]✓[/green] {repo_name:<20} → {default_branch}")
            switched.append((repo_name, repo_path))
        else:
            err = result.stderr.strip()
            console.print(f"    [red]✗[/red] {repo_name:<20} checkout failed: {err}")

    console.print()

    # Offer to delete local branches
    if switched and Confirm.ask("  Delete local feature branches?", default=False):
        console.print()
        for repo_name, repo_path in switched:
            result = git.delete_branch(repo_path, feature)
            if result.returncode == 0:
                console.print(f"    [green]✓[/green] {repo_name:<20} deleted {feature}")
            else:
                err = result.stderr.strip()
                console.print(f"    [yellow]![/yellow] {repo_name:<20} {err}")
        console.print()

    console.print("  Feature finished.\n")

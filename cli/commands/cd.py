"""workbench cd — resolve a target directory for shell navigation."""

from __future__ import annotations

import sys
from pathlib import Path
from typing import Optional

import typer

from cli.utils.config import load_config, find_workbench_yaml


def cd_cmd(
    target: Optional[str] = typer.Argument(None, help="Repo name or relative path (omit for workbench root)."),
) -> None:
    """Navigate to the workbench root or a repo directory.

    Prints the resolved path to stdout for shell integration.
    """
    workbench_root = find_workbench_yaml().parent

    if not target:
        # No argument — go to workbench root
        print(workbench_root)
        return

    # Try as a repo name first
    config = load_config()
    if target in config.repos:
        repo_path = workbench_root / config.repos[target].path
        if repo_path.exists():
            print(repo_path)
            return
        # Repo configured but not cloned
        sys.stderr.write(f"Repo '{target}' is not cloned yet. Run: workbench init\n")
        raise typer.Exit(1)

    # Try as a relative path from workbench root
    resolved = workbench_root / target
    if resolved.exists():
        print(resolved)
        return

    # Nothing matched
    sys.stderr.write(f"Not found: '{target}' (not a repo name or valid path)\n")
    raise typer.Exit(1)

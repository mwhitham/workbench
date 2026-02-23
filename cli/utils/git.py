"""Git operations across repos."""

from __future__ import annotations

import subprocess
from pathlib import Path
from typing import Optional


def _run(args: list[str], cwd: Path, *, check: bool = True) -> subprocess.CompletedProcess[str]:
    """Run a git command in *cwd* and return the result."""
    return subprocess.run(
        args,
        cwd=cwd,
        capture_output=True,
        text=True,
        check=check,
    )


# ---------------------------------------------------------------------------
# Read-only helpers
# ---------------------------------------------------------------------------

def get_branch(repo_path: Path) -> str:
    """Return the current branch name (or HEAD hash if detached)."""
    result = _run(["git", "rev-parse", "--abbrev-ref", "HEAD"], cwd=repo_path, check=False)
    branch = result.stdout.strip()
    if branch == "HEAD":
        # Detached HEAD — return short hash
        result = _run(["git", "rev-parse", "--short", "HEAD"], cwd=repo_path, check=False)
        return result.stdout.strip() or "unknown"
    return branch or "unknown"


def is_dirty(repo_path: Path) -> bool:
    """Return True if the working tree has uncommitted changes."""
    result = _run(["git", "status", "--porcelain"], cwd=repo_path, check=False)
    return bool(result.stdout.strip())


def get_modified_count(repo_path: Path) -> int:
    """Return the number of modified/untracked files."""
    result = _run(["git", "status", "--porcelain"], cwd=repo_path, check=False)
    lines = [l for l in result.stdout.strip().splitlines() if l.strip()]
    return len(lines)


def get_ahead_behind(repo_path: Path) -> tuple[int, int]:
    """Return (ahead, behind) relative to the upstream tracking branch.

    Returns (0, 0) if there is no upstream or on error.
    """
    result = _run(
        ["git", "rev-list", "--left-right", "--count", "@{upstream}...HEAD"],
        cwd=repo_path,
        check=False,
    )
    if result.returncode != 0:
        return 0, 0
    parts = result.stdout.strip().split()
    if len(parts) == 2:
        behind, ahead = int(parts[0]), int(parts[1])
        return ahead, behind
    return 0, 0


def get_status_summary(repo_path: Path) -> dict:
    """Return a combined status dict for a repo.

    Keys: branch, dirty, modified_count, ahead, behind
    """
    branch = get_branch(repo_path)
    dirty = is_dirty(repo_path)
    modified = get_modified_count(repo_path)
    ahead, behind = get_ahead_behind(repo_path)
    return {
        "branch": branch,
        "dirty": dirty,
        "modified_count": modified,
        "ahead": ahead,
        "behind": behind,
    }


# ---------------------------------------------------------------------------
# Write operations
# ---------------------------------------------------------------------------

def clone(url: str, dest: Path) -> subprocess.CompletedProcess[str]:
    """Clone a repo from *url* into *dest*."""
    return _run(["git", "clone", url, str(dest)], cwd=dest.parent)


def pull(repo_path: Path) -> subprocess.CompletedProcess[str]:
    """Pull the latest changes."""
    return _run(["git", "pull"], cwd=repo_path, check=False)


def push_repo(repo_path: Path) -> subprocess.CompletedProcess[str]:
    """Push the current branch."""
    return _run(["git", "push"], cwd=repo_path, check=False)


# ---------------------------------------------------------------------------
# Branch operations
# ---------------------------------------------------------------------------

def current_branch(repo_path: Path) -> str:
    """Return the current branch name (alias for get_branch)."""
    return get_branch(repo_path)


def get_default_branch(repo_path: Path) -> str:
    """Detect the default branch (main or master)."""
    for name in ("main", "master"):
        result = _run(
            ["git", "rev-parse", "--verify", name],
            cwd=repo_path,
            check=False,
        )
        if result.returncode == 0:
            return name
    return "main"


def create_branch(repo_path: Path, branch_name: str) -> subprocess.CompletedProcess[str]:
    """Create and switch to a new branch."""
    return _run(["git", "checkout", "-b", branch_name], cwd=repo_path, check=False)


def checkout(repo_path: Path, branch_name: str) -> subprocess.CompletedProcess[str]:
    """Switch to an existing branch."""
    return _run(["git", "checkout", branch_name], cwd=repo_path, check=False)


def has_remote_branch(repo_path: Path, branch_name: str) -> bool:
    """Check if a branch exists on the remote."""
    result = _run(
        ["git", "ls-remote", "--heads", "origin", branch_name],
        cwd=repo_path,
        check=False,
    )
    return bool(result.stdout.strip())


def push_with_upstream(repo_path: Path) -> subprocess.CompletedProcess[str]:
    """Push the current branch with -u to set upstream tracking."""
    branch = get_branch(repo_path)
    return _run(
        ["git", "push", "-u", "origin", branch],
        cwd=repo_path,
        check=False,
    )


def commits_ahead_of(repo_path: Path, base_branch: str) -> int:
    """Return the number of commits the current branch is ahead of *base_branch*."""
    result = _run(
        ["git", "rev-list", "--count", f"{base_branch}..HEAD"],
        cwd=repo_path,
        check=False,
    )
    if result.returncode != 0:
        return 0
    try:
        return int(result.stdout.strip())
    except ValueError:
        return 0


def delete_branch(repo_path: Path, branch_name: str) -> subprocess.CompletedProcess[str]:
    """Delete a local branch."""
    return _run(["git", "branch", "-d", branch_name], cwd=repo_path, check=False)

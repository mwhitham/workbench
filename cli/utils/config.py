"""
cli/utils/config.py - Workbench Configuration Parser

Parses workbench.yaml and provides typed access to configuration.
Other CLI commands import from this module to read/write config.
"""

from __future__ import annotations

import os
from dataclasses import dataclass, field, asdict
from pathlib import Path
from typing import Any

import yaml


# ---------------------------------------------------------------------------
# Data models
# ---------------------------------------------------------------------------

@dataclass
class RepoConfig:
    """Configuration for a single repository."""

    name: str
    url: str = ""
    path: str = ""
    description: str = ""
    type: str = "service"  # "service" or "infrastructure"
    start_command: str | None = None
    port: int | None = None
    language: str | None = None
    framework: str | None = None
    dependencies: str | None = None
    health_check: str | None = None
    install_command: str | None = None
    env_file: str | None = None

    @property
    def is_infrastructure(self) -> bool:
        return self.type == "infrastructure"

    @property
    def is_startable(self) -> bool:
        return not self.is_infrastructure and self.start_command is not None

    @property
    def abs_path(self) -> Path:
        """Return absolute path resolved from the workbench root."""
        return _workbench_root() / self.path


@dataclass
class WorkbenchConfig:
    """Top-level workbench configuration."""

    name: str = "my-workbench"
    version: str = "0.1.0"
    repos: dict[str, RepoConfig] = field(default_factory=dict)
    services: dict[str, Any] = field(default_factory=dict)
    environment: dict[str, Any] = field(default_factory=dict)


# ---------------------------------------------------------------------------
# Internal helpers
# ---------------------------------------------------------------------------

_CONFIG_FILENAME = "workbench.yaml"


def _workbench_root() -> Path:
    """Return the workbench root directory (where workbench.yaml lives)."""
    return find_workbench_yaml().parent


def _repo_from_dict(name: str, data: dict[str, Any]) -> RepoConfig:
    """Build a RepoConfig from a raw YAML dict."""
    return RepoConfig(
        name=name,
        url=data.get("url", ""),
        path=data.get("path", ""),
        description=data.get("description", ""),
        type=data.get("type", "service"),
        start_command=data.get("start_command"),
        port=_to_int_or_none(data.get("port")),
        language=data.get("language"),
        framework=data.get("framework"),
        dependencies=data.get("dependencies"),
        health_check=data.get("health_check"),
        install_command=data.get("install_command"),
        env_file=data.get("env_file"),
    )


def _repo_to_dict(repo: RepoConfig) -> dict[str, Any]:
    """Serialize a RepoConfig back to a plain dict for YAML output."""
    d: dict[str, Any] = {}
    d["url"] = repo.url
    d["path"] = repo.path
    d["description"] = repo.description
    if repo.type != "service":
        d["type"] = repo.type
    d["start_command"] = repo.start_command
    d["port"] = repo.port
    d["language"] = repo.language
    d["framework"] = repo.framework
    d["dependencies"] = repo.dependencies
    d["health_check"] = repo.health_check
    d["install_command"] = repo.install_command
    d["env_file"] = repo.env_file
    return d


def _to_int_or_none(val: Any) -> int | None:
    if val is None:
        return None
    try:
        return int(val)
    except (ValueError, TypeError):
        return None


# ---------------------------------------------------------------------------
# Public API
# ---------------------------------------------------------------------------

def find_workbench_yaml(start: Path | None = None) -> Path:
    """Walk upward from *start* (default: cwd) to find workbench.yaml.

    Raises FileNotFoundError if not found.
    """
    current = (start or Path.cwd()).resolve()
    while True:
        candidate = current / _CONFIG_FILENAME
        if candidate.is_file():
            return candidate
        parent = current.parent
        if parent == current:
            break
        current = parent
    raise FileNotFoundError(
        f"Could not find {_CONFIG_FILENAME} in {start or Path.cwd()} or any parent directory"
    )


def load_config(path: Path | None = None) -> WorkbenchConfig:
    """Load and parse workbench.yaml into a WorkbenchConfig.

    If *path* is None, searches upward from cwd.
    """
    config_path = path if path else find_workbench_yaml()
    with open(config_path, "r") as f:
        raw = yaml.safe_load(f) or {}

    wb = raw.get("workbench", {})
    repos_raw = raw.get("repos", {})
    repos = {name: _repo_from_dict(name, data or {}) for name, data in repos_raw.items()}

    return WorkbenchConfig(
        name=wb.get("name", "my-workbench"),
        version=wb.get("version", "0.1.0"),
        repos=repos,
        services=raw.get("services", {}),
        environment=raw.get("environment", {}),
    )


def save_config(config: WorkbenchConfig, path: Path | None = None) -> Path:
    """Write a WorkbenchConfig back to workbench.yaml.

    Returns the path that was written to.
    """
    config_path = path if path else find_workbench_yaml()

    data: dict[str, Any] = {
        "workbench": {
            "name": config.name,
            "version": config.version,
        },
        "repos": {name: _repo_to_dict(repo) for name, repo in config.repos.items()},
        "services": config.services or {"shared": []},
        "environment": config.environment or {"shared_env": {}},
    }

    with open(config_path, "w") as f:
        yaml.dump(data, f, default_flow_style=False, sort_keys=False, allow_unicode=True)

    return config_path


def get_repo(config: WorkbenchConfig, name: str) -> RepoConfig:
    """Get a single repo by logical name. Raises KeyError if not found."""
    if name not in config.repos:
        raise KeyError(f"Repository '{name}' not found in workbench.yaml")
    return config.repos[name]


def get_startable_repos(config: WorkbenchConfig) -> list[RepoConfig]:
    """Return repos that can be started (excludes infrastructure repos)."""
    return [r for r in config.repos.values() if not r.is_infrastructure]


def get_all_repos(config: WorkbenchConfig) -> list[RepoConfig]:
    """Return all repos including infrastructure."""
    return list(config.repos.values())


def config_path_default() -> Path:
    """Return the default config path (workbench.yaml in cwd or parent)."""
    return find_workbench_yaml()

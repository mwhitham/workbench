"""
cli/commands/discover.py - Auto-discover repository configurations

Reads each cloned repo and auto-populates workbench.yaml with start commands,
ports, language/framework detection, dependencies, env vars, and health checks.
"""

from __future__ import annotations

import json
import re
from pathlib import Path
from typing import Any, Optional

import typer
import yaml
from rich.console import Console
from rich.panel import Panel
from rich.table import Table
from rich.text import Text

from cli.utils.config import (
    RepoConfig,
    WorkbenchConfig,
    load_config,
    save_config,
    find_workbench_yaml,
)

console = Console()

# ---------------------------------------------------------------------------
# Typer command
# ---------------------------------------------------------------------------

app = typer.Typer()


@app.command()
def discover(
    repo: Optional[str] = typer.Argument(None, help="Discover only a specific repo"),
    dry_run: bool = typer.Option(False, "--dry-run", "-n", help="Show results without writing"),
    verbose: bool = typer.Option(False, "--verbose", "-v", help="Show detailed detection info"),
    quiet: bool = typer.Option(False, "--quiet", "-q", help="Minimal output"),
):
    """Auto-detect repository configurations and update workbench.yaml."""

    if not quiet:
        console.print()
        console.print(Text("  workbench discover", style="bold cyan"))
        console.print()

    try:
        config = load_config()
    except FileNotFoundError:
        console.print("  [red]Could not find workbench.yaml[/red]")
        console.print("  [dim]Run this command from your workbench root directory.[/dim]")
        raise typer.Exit(1)

    root = find_workbench_yaml().parent
    repos_to_scan = config.repos

    if repo:
        if repo not in config.repos:
            console.print(f"  [red]Repository '{repo}' not found in workbench.yaml[/red]")
            raise typer.Exit(1)
        repos_to_scan = {repo: config.repos[repo]}

    if not quiet:
        console.print("  [dim]Scanning repositories...[/dim]")
        console.print()

    results: list[tuple[str, RepoConfig, dict[str, str]]] = []

    for name, repo_cfg in repos_to_scan.items():
        repo_path = root / repo_cfg.path
        if not repo_path.is_dir():
            if not quiet:
                console.print(f"    [yellow]~[/yellow] {name:<18} [dim]directory not found at {repo_cfg.path}[/dim]")
            continue

        detection_log: dict[str, str] = {}
        discovered = _discover_repo(repo_path, repo_cfg, detection_log)

        # Merge discovered values into the existing config (don't overwrite manual settings)
        _merge_discovered(repo_cfg, discovered)
        results.append((name, repo_cfg, detection_log))

        if not quiet:
            _print_repo_result(name, repo_cfg)

        if verbose:
            for key, reason in detection_log.items():
                console.print(f"           [dim]{key}: {reason}[/dim]")

    if not quiet:
        console.print()

    # Write results back
    if not dry_run:
        config_path = save_config(config)
        if not quiet:
            console.print(f"  [green]Updated[/green] {config_path.name}")
            console.print()
    elif not quiet:
        console.print("  [yellow]Dry run[/yellow] — no changes written")
        console.print()

    # Summary table
    if not quiet and results:
        _print_summary_table(results)


# ---------------------------------------------------------------------------
# Pretty printing
# ---------------------------------------------------------------------------

def _print_repo_result(name: str, repo: RepoConfig) -> None:
    """Print a single-line discovery result for a repo."""
    parts: list[str] = []
    if repo.language:
        parts.append(repo.language)
    if repo.framework:
        parts.append(repo.framework)
    if repo.is_infrastructure:
        parts.append("infrastructure")
    elif repo.port:
        parts.append(f"port {repo.port}")

    detail = " [dim]\u00b7[/dim] ".join(parts) if parts else "[dim]no config detected[/dim]"
    glyph = "[green]\u2713[/green]"
    console.print(f"    {glyph} {name:<18} {detail}")


def _print_summary_table(results: list[tuple[str, RepoConfig, dict[str, str]]]) -> None:
    """Print a summary table of all discovered repos."""
    table = Table(
        title=None,
        show_header=True,
        header_style="bold dim",
        border_style="dim",
        pad_edge=False,
        padding=(0, 2),
    )
    table.add_column("Repo", style="bold")
    table.add_column("Language")
    table.add_column("Framework")
    table.add_column("Start Command", style="dim")
    table.add_column("Port", justify="right")
    table.add_column("Health Check", style="dim")

    for name, repo, _ in results:
        port_str = str(repo.port) if repo.port else "\u2014"
        table.add_row(
            name,
            repo.language or "\u2014",
            repo.framework or "\u2014",
            _truncate(repo.start_command, 30) if repo.start_command else "\u2014",
            port_str,
            repo.health_check or "\u2014",
        )

    console.print(Panel(table, title="[bold]Discovery Results[/bold]", border_style="cyan", padding=(1, 2)))
    console.print()


def _truncate(s: str | None, max_len: int) -> str:
    if not s:
        return ""
    return s if len(s) <= max_len else s[: max_len - 1] + "\u2026"


# ---------------------------------------------------------------------------
# Discovery engine
# ---------------------------------------------------------------------------

def _discover_repo(repo_path: Path, repo_cfg: RepoConfig, log: dict[str, str]) -> dict[str, Any]:
    """Run all detectors on a single repo. Returns a dict of discovered values."""
    discovered: dict[str, Any] = {}

    # Skip deep detection for infrastructure repos
    is_infra = repo_cfg.is_infrastructure

    discovered["language"] = _detect_language(repo_path, log)
    discovered["framework"] = _detect_framework(repo_path, discovered["language"], log)

    if not is_infra:
        discovered["start_command"] = _detect_start_command(repo_path, discovered["language"], log)
        discovered["port"] = _detect_port(repo_path, discovered["framework"], log)
        discovered["health_check"] = _detect_health_check(repo_path, discovered["language"], discovered["framework"], log)
        discovered["install_command"] = _detect_install_command(repo_path, discovered["language"], log)
    else:
        log["start_command"] = "skipped (infrastructure repo)"
        log["port"] = "skipped (infrastructure repo)"
        log["health_check"] = "skipped (infrastructure repo)"

    discovered["dependencies"] = _detect_dependencies(repo_path, discovered["language"], log)
    discovered["env_file"] = _detect_env_file(repo_path, log)

    return discovered


def _merge_discovered(repo: RepoConfig, discovered: dict[str, Any]) -> None:
    """Merge discovered values into RepoConfig, preserving existing manual overrides."""
    for key, value in discovered.items():
        if value is not None and getattr(repo, key, None) is None:
            setattr(repo, key, value)


# ---------------------------------------------------------------------------
# Language detection
# ---------------------------------------------------------------------------

def _detect_language(repo_path: Path, log: dict[str, str]) -> str | None:
    if (repo_path / "package.json").exists():
        # Check for TypeScript indicators
        if (repo_path / "tsconfig.json").exists():
            log["language"] = "tsconfig.json found"
            return "TypeScript"
        log["language"] = "package.json found"
        return "JavaScript"

    if (repo_path / "requirements.txt").exists():
        log["language"] = "requirements.txt found"
        return "Python"

    if (repo_path / "pyproject.toml").exists():
        log["language"] = "pyproject.toml found"
        return "Python"

    if (repo_path / "setup.py").exists():
        log["language"] = "setup.py found"
        return "Python"

    # Check for Terraform files
    tf_files = list(repo_path.glob("**/*.tf"))
    if tf_files:
        log["language"] = f"found {len(tf_files)} .tf files"
        return "HCL"

    if (repo_path / "go.mod").exists():
        log["language"] = "go.mod found"
        return "Go"

    if (repo_path / "Cargo.toml").exists():
        log["language"] = "Cargo.toml found"
        return "Rust"

    log["language"] = "no language indicators found"
    return None


# ---------------------------------------------------------------------------
# Framework detection
# ---------------------------------------------------------------------------

def _detect_framework(repo_path: Path, language: str | None, log: dict[str, str]) -> str | None:
    if language == "Python":
        return _detect_python_framework(repo_path, log)
    if language in ("TypeScript", "JavaScript"):
        return _detect_js_framework(repo_path, log)
    if language == "HCL":
        log["framework"] = "HCL files detected"
        return "Terraform"
    log["framework"] = "no framework detected"
    return None


def _detect_python_framework(repo_path: Path, log: dict[str, str]) -> str | None:
    """Detect Python web frameworks from requirements files."""
    deps = _read_python_deps(repo_path)
    if not deps:
        log["framework"] = "no dependency files found"
        return None

    deps_lower = deps.lower()
    if "fastapi" in deps_lower:
        log["framework"] = "fastapi found in dependencies"
        return "FastAPI"
    if "django" in deps_lower:
        log["framework"] = "django found in dependencies"
        return "Django"
    if "flask" in deps_lower:
        log["framework"] = "flask found in dependencies"
        return "Flask"
    if "dspy" in deps_lower or "dspy-ai" in deps_lower:
        log["framework"] = "dspy found in dependencies"
        return "DSPy"

    log["framework"] = "no known Python framework in dependencies"
    return None


def _detect_js_framework(repo_path: Path, log: dict[str, str]) -> str | None:
    """Detect JS/TS frameworks from package.json."""
    pkg = _read_package_json(repo_path)
    if not pkg:
        log["framework"] = "no package.json found"
        return None

    all_deps = {**pkg.get("dependencies", {}), **pkg.get("devDependencies", {})}

    if "expo" in all_deps:
        log["framework"] = "expo found in package.json dependencies"
        return "Expo / React Native"
    if "react-native" in all_deps and "expo" not in all_deps:
        log["framework"] = "react-native found in package.json dependencies"
        return "React Native"
    if "next" in all_deps:
        log["framework"] = "next found in package.json dependencies"
        return "Next.js"
    if "nuxt" in all_deps:
        log["framework"] = "nuxt found in package.json dependencies"
        return "Nuxt"
    if "react" in all_deps:
        log["framework"] = "react found in package.json dependencies"
        return "React"
    if "vue" in all_deps:
        log["framework"] = "vue found in package.json dependencies"
        return "Vue"

    log["framework"] = "no known JS framework in package.json"
    return None


# ---------------------------------------------------------------------------
# Start command detection
# ---------------------------------------------------------------------------

def _detect_start_command(repo_path: Path, language: str | None, log: dict[str, str]) -> str | None:
    # 1. package.json scripts
    pkg = _read_package_json(repo_path)
    if pkg:
        scripts = pkg.get("scripts", {})
        if "dev" in scripts:
            log["start_command"] = f"package.json scripts.dev = \"{scripts['dev']}\""
            pkg_manager = _detect_package_manager(repo_path)
            return f"{pkg_manager} dev"
        if "start" in scripts:
            log["start_command"] = f"package.json scripts.start = \"{scripts['start']}\""
            pkg_manager = _detect_package_manager(repo_path)
            return f"{pkg_manager} start"

    # 2. Makefile targets
    makefile = _read_makefile(repo_path)
    if makefile:
        targets = _parse_makefile_targets(makefile)
        if "run" in targets:
            log["start_command"] = f"Makefile target 'run'"
            return "make run"
        if "dev" in targets:
            log["start_command"] = f"Makefile target 'dev'"
            return "make dev"
        if "serve" in targets:
            log["start_command"] = f"Makefile target 'serve'"
            return "make serve"
        if "start" in targets:
            log["start_command"] = f"Makefile target 'start'"
            return "make start"

    # 3. Procfile
    procfile_path = repo_path / "Procfile"
    if procfile_path.exists():
        content = procfile_path.read_text()
        match = re.search(r"^web:\s*(.+)$", content, re.MULTILINE)
        if match:
            log["start_command"] = f"Procfile web process"
            return match.group(1).strip()

    # 4. render.yaml
    render_path = repo_path / "render.yaml"
    if render_path.exists():
        try:
            with open(render_path) as f:
                render = yaml.safe_load(f) or {}
            services = render.get("services", [])
            if services and isinstance(services, list):
                cmd = services[0].get("startCommand")
                if cmd:
                    log["start_command"] = f"render.yaml startCommand"
                    return cmd
        except Exception:
            pass

    # 5. Python fallback: look for main.py with uvicorn/gunicorn
    if language == "Python":
        if (repo_path / "main.py").exists():
            deps = _read_python_deps(repo_path)
            if deps and "uvicorn" in deps.lower():
                log["start_command"] = "main.py + uvicorn in dependencies"
                return "uvicorn main:app --reload"

    log["start_command"] = "no start command detected"
    return None


# ---------------------------------------------------------------------------
# Port detection
# ---------------------------------------------------------------------------

def _detect_port(repo_path: Path, framework: str | None, log: dict[str, str]) -> int | None:
    # 1. .env.example / .env.template files
    for env_name in (".env.example", ".env.template", ".env.sample"):
        env_path = repo_path / env_name
        if env_path.exists():
            content = env_path.read_text()
            match = re.search(r"^PORT\s*=\s*(\d+)", content, re.MULTILINE)
            if match:
                log["port"] = f"PORT={match.group(1)} in {env_name}"
                return int(match.group(1))

    # 2. docker-compose.yml ports
    compose_path = repo_path / "docker-compose.yml"
    if not compose_path.exists():
        compose_path = repo_path / "docker-compose.yaml"
    if compose_path.exists():
        try:
            with open(compose_path) as f:
                compose = yaml.safe_load(f) or {}
            services = compose.get("services", {})
            for svc_name, svc_data in services.items():
                ports = svc_data.get("ports", [])
                for port_mapping in ports:
                    port_str = str(port_mapping)
                    # Parse "host:container" or just "port"
                    match = re.search(r"(\d+):\d+", port_str)
                    if match:
                        # This is a shared service port (like postgres), not the app port
                        # Only use if service name matches repo context
                        pass
        except Exception:
            pass

    # 3. Framework defaults
    framework_ports = {
        "Next.js": 3000,
        "FastAPI": 8000,
        "Expo / React Native": 8081,
        "React Native": 8081,
        "Django": 8000,
        "Flask": 5000,
        "React": 3000,
        "Vue": 3000,
        "Nuxt": 3000,
    }
    if framework and framework in framework_ports:
        log["port"] = f"framework default for {framework}"
        return framework_ports[framework]

    log["port"] = "no port detected"
    return None


# ---------------------------------------------------------------------------
# Health check detection
# ---------------------------------------------------------------------------

def _detect_health_check(
    repo_path: Path,
    language: str | None,
    framework: str | None,
    log: dict[str, str],
) -> str | None:
    # FastAPI: search for /health or /status routes
    if framework == "FastAPI" or language == "Python":
        for py_file in repo_path.rglob("*.py"):
            try:
                content = py_file.read_text(errors="ignore")
            except Exception:
                continue
            # Look for route decorators with health or status paths
            for pattern in [
                r'@\w+\.\w+\(\s*["\']/(health|status)["\']',
                r'router\.\w+\(\s*["\']/(health|status)["\']',
            ]:
                match = re.search(pattern, content)
                if match:
                    endpoint = f"/{match.group(1)}"
                    log["health_check"] = f"found {endpoint} route in {py_file.relative_to(repo_path)}"
                    return endpoint

    # Next.js: check for api/health route
    if framework == "Next.js":
        api_health = repo_path / "src" / "app" / "api" / "health" / "route.ts"
        if api_health.exists():
            log["health_check"] = "found src/app/api/health/route.ts"
            return "/api/health"
        # No explicit health check
        log["health_check"] = "no health endpoint found (Next.js)"
        return None

    # Mobile apps don't have health checks
    if framework in ("Expo / React Native", "React Native"):
        log["health_check"] = "not applicable (mobile app)"
        return None

    log["health_check"] = "no health check detected"
    return None


# ---------------------------------------------------------------------------
# Install command detection
# ---------------------------------------------------------------------------

def _detect_install_command(repo_path: Path, language: str | None, log: dict[str, str]) -> str | None:
    # Node.js package managers
    if (repo_path / "package.json").exists():
        pkg_manager = _detect_package_manager(repo_path)
        log["install_command"] = f"{pkg_manager} detected from lock file"
        return f"{pkg_manager} install"

    # Python
    if language == "Python":
        # Prefer Makefile install target
        makefile = _read_makefile(repo_path)
        if makefile:
            targets = _parse_makefile_targets(makefile)
            if "install" in targets:
                log["install_command"] = "Makefile install target"
                return "make install"

        if (repo_path / "setup.py").exists() or (repo_path / "pyproject.toml").exists():
            log["install_command"] = "setup.py/pyproject.toml found"
            return "pip install -e ."

        if (repo_path / "requirements.txt").exists():
            log["install_command"] = "requirements.txt found"
            return "pip install -r requirements.txt"

    log["install_command"] = "no install command detected"
    return None


# ---------------------------------------------------------------------------
# Dependency file detection
# ---------------------------------------------------------------------------

def _detect_dependencies(repo_path: Path, language: str | None, log: dict[str, str]) -> str | None:
    if (repo_path / "package.json").exists():
        log["dependencies"] = "package.json"
        return "package.json"
    if (repo_path / "requirements.txt").exists():
        log["dependencies"] = "requirements.txt"
        return "requirements.txt"
    if (repo_path / "pyproject.toml").exists():
        log["dependencies"] = "pyproject.toml"
        return "pyproject.toml"
    if (repo_path / "setup.py").exists():
        log["dependencies"] = "setup.py"
        return "setup.py"
    if (repo_path / "go.mod").exists():
        log["dependencies"] = "go.mod"
        return "go.mod"
    if (repo_path / "Cargo.toml").exists():
        log["dependencies"] = "Cargo.toml"
        return "Cargo.toml"
    log["dependencies"] = "no dependency file found"
    return None


# ---------------------------------------------------------------------------
# Env file detection
# ---------------------------------------------------------------------------

def _detect_env_file(repo_path: Path, log: dict[str, str]) -> str | None:
    for name in (".env.example", ".env.template", ".env.sample"):
        if (repo_path / name).exists():
            log["env_file"] = name
            return name
    log["env_file"] = "no env template found"
    return None


# ---------------------------------------------------------------------------
# File reading helpers
# ---------------------------------------------------------------------------

def _read_package_json(repo_path: Path) -> dict[str, Any] | None:
    pkg_path = repo_path / "package.json"
    if not pkg_path.exists():
        return None
    try:
        with open(pkg_path) as f:
            return json.load(f)
    except (json.JSONDecodeError, OSError):
        return None


def _read_python_deps(repo_path: Path) -> str | None:
    """Read combined text from requirements.txt, setup.py, pyproject.toml."""
    parts: list[str] = []
    for name in ("requirements.txt", "setup.py", "pyproject.toml"):
        dep_path = repo_path / name
        if dep_path.exists():
            try:
                parts.append(dep_path.read_text(errors="ignore"))
            except OSError:
                pass
    return "\n".join(parts) if parts else None


def _read_makefile(repo_path: Path) -> str | None:
    for name in ("Makefile", "makefile", "GNUmakefile"):
        mf_path = repo_path / name
        if mf_path.exists():
            try:
                return mf_path.read_text(errors="ignore")
            except OSError:
                pass
    return None


def _parse_makefile_targets(content: str) -> set[str]:
    """Extract target names from a Makefile."""
    targets: set[str] = set()
    for line in content.splitlines():
        match = re.match(r"^([a-zA-Z_][\w-]*):", line)
        if match:
            targets.add(match.group(1))
    return targets


def _detect_package_manager(repo_path: Path) -> str:
    """Detect which Node.js package manager to use."""
    if (repo_path / "yarn.lock").exists():
        return "yarn"
    if (repo_path / "pnpm-lock.yaml").exists():
        return "pnpm"
    if (repo_path / "bun.lockb").exists():
        return "bun"
    return "npm"


# ---------------------------------------------------------------------------
# Alias for integration with other commands (e.g. init calls discover_cmd)
# ---------------------------------------------------------------------------

discover_cmd = discover

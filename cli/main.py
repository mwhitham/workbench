"""Workbench CLI — main application definition."""

from __future__ import annotations

import typer
from rich.console import Console

from cli import __version__
from cli.commands import init, up, down, status, push, sync, docs, add, cd
from cli.commands.feature import feature_app

app = typer.Typer(
    name="workbench",
    help="Developer workbench — orchestrate multiple repos into a unified local dev environment.",
    no_args_is_help=True,
    add_completion=False,
)

# Shared console instance
console = Console()

# ---------------------------------------------------------------------------
# Global state — set by the main callback, read by all commands
# ---------------------------------------------------------------------------

class _State:
    quiet: bool = False
    verbose: bool = False

state = _State()


def banner() -> None:
    """Print the startup banner (unless --quiet)."""
    if not state.quiet:
        console.print(f"\n  [bold cyan]workbench[/bold cyan] [dim]v{__version__}[/dim]\n")


# ---------------------------------------------------------------------------
# Main callback — handles global flags
# ---------------------------------------------------------------------------

@app.callback(invoke_without_command=True)
def main(
    quiet: bool = typer.Option(False, "--quiet", "-q", help="Minimal output for scripts and CI."),
    verbose: bool = typer.Option(False, "--verbose", "-v", help="Show underlying commands and debug info."),
) -> None:
    """Developer workbench for multi-repo orchestration."""
    state.quiet = quiet
    state.verbose = verbose


# ---------------------------------------------------------------------------
# Register commands
# ---------------------------------------------------------------------------

app.command(name="init", help="Clone all repos and run discovery.")(init.init_cmd)
app.command(name="up", help="Start services (all or a specific one).")(up.up_cmd)
app.command(name="down", help="Stop running services.")(down.down_cmd)
app.command(name="status", help="Show repo and service status dashboard.")(status.status_cmd)
app.command(name="push", help="Push changes for one or all repos.")(push.push_cmd)
app.command(name="sync", help="Pull latest changes for all repos.")(sync.sync_cmd)
app.command(name="docs", help="Open or serve the documentation.")(docs.docs_cmd)
app.command(name="add", help="Add a new repo to the workbench.")(add.add_cmd)
app.command(name="cd", help="Navigate to workbench root or a repo directory.")(cd.cd_cmd)
app.add_typer(feature_app)

try:
    from cli.commands import discover
    app.command(name="discover", help="Auto-detect repo configurations.")(discover.discover)
except Exception:
    pass  # discover command registered when available


# ---------------------------------------------------------------------------
# Entrypoint
# ---------------------------------------------------------------------------

def run() -> None:
    app()

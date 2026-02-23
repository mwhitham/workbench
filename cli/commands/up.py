"""workbench up — start services."""

from __future__ import annotations

import signal
import sys
import time
from pathlib import Path
from typing import Optional

import typer
from rich.console import Console
from rich.panel import Panel

from cli.utils.process import ProcessManager, ServiceProcess, SERVICE_COLORS

console = Console()


def up_cmd(
    service: Optional[str] = typer.Argument(None, help="Service to start (omit for all)."),
) -> None:
    """Start services (all or a specific one)."""
    from cli.main import banner, state
    from cli.utils.config import load_config, find_workbench_yaml

    banner()

    config = load_config()
    workbench_root = find_workbench_yaml().parent
    shared_env = config.environment.get("shared_env", {}) if config.environment else {}

    # Filter to startable services (not infrastructure)
    startable: dict[str, object] = {}
    for name, repo_cfg in config.repos.items():
        if repo_cfg.is_infrastructure:
            continue
        startable[name] = repo_cfg

    if service:
        if service not in config.repos:
            console.print(f"\n  [red]✗[/red] Unknown service: [bold]{service}[/bold]")
            console.print(f"  [dim]Available: {', '.join(config.repos.keys())}[/dim]\n")
            raise typer.Exit(1)
        if config.repos[service].is_infrastructure:
            console.print(
                f"\n  [yellow]○[/yellow] [bold]{service}[/bold] is an infrastructure repo "
                f"(reference only — cannot be started)\n"
            )
            raise typer.Exit(1)
        startable = {service: config.repos[service]}

    if not startable:
        console.print("  [yellow]No startable services found.[/yellow]\n")
        raise typer.Exit(1)

    # Check all services have a start command
    missing_cmd = [n for n, c in startable.items() if not c.start_command]
    if missing_cmd:
        console.print("  [red]✗[/red] Missing start commands:\n")
        for name in missing_cmd:
            console.print(f"    [dim]•[/dim] {name}")
        console.print(
            "\n  Run [bold cyan]workbench discover[/bold cyan] to auto-detect, "
            "or set [bold]start_command[/bold] in workbench.yaml.\n"
        )
        raise typer.Exit(1)

    # Build process manager
    manager = ProcessManager(workbench_root)
    color_idx = 0

    for name, repo_cfg in startable.items():
        color = SERVICE_COLORS[color_idx % len(SERVICE_COLORS)]
        color_idx += 1

        svc = ServiceProcess(
            name=name,
            command=repo_cfg.start_command,
            cwd=workbench_root / (repo_cfg.path or f"repos/{name}"),
            port=repo_cfg.port,
            health_check=repo_cfg.health_check,
            env=shared_env if isinstance(shared_env, dict) else {},
            color=color,
            workbench_root=workbench_root,
        )
        manager.add(svc)

    # -- Start services with live status ------------------------------------
    console.print("  [bold]→[/bold] Starting services...\n")

    for name, svc in manager.services.items():
        port_str = f":{svc.port}" if svc.port else ""
        console.print(f"    {name:<20} [cyan]●[/cyan] starting on {port_str} ...")
        svc.start()

    # Wait for health
    console.print()
    all_healthy = True
    for name, svc in manager.services.items():
        healthy = svc.wait_healthy(timeout=30)
        if healthy:
            console.print(f"    {name:<20} [green]✓[/green] healthy")
        else:
            if svc.is_running():
                console.print(f"    {name:<20} [yellow]●[/yellow] running [dim](health check inconclusive)[/dim]")
            else:
                all_healthy = False
                console.print(f"    {name:<20} [red]✗[/red] failed to start")
                _show_error_panel(name, svc)

    if not all_healthy:
        console.print()
        manager.stop_all()
        raise typer.Exit(1)

    console.print(
        "\n  All services running. Press [bold]Ctrl+C[/bold] to stop all.\n"
    )
    console.print("  [dim]─── logs ─────────────────────────────────────────────[/dim]")

    # Start log streaming threads
    for svc in manager.services.values():
        svc.start_log_thread(console)

    # -- Wait for Ctrl+C ----------------------------------------------------
    def _shutdown(signum, frame):
        console.print("\n\n  [bold]→[/bold] Stopping services...\n")
        manager.stop_all()
        for name in manager.services:
            console.print(f"    [green]✓[/green] {name:<20} stopped")
        console.print()
        sys.exit(0)

    signal.signal(signal.SIGINT, _shutdown)
    signal.signal(signal.SIGTERM, _shutdown)

    # Block main thread
    try:
        while manager.get_running():
            time.sleep(1)
    except KeyboardInterrupt:
        _shutdown(None, None)

    # If we get here, all processes exited on their own
    console.print("\n  [yellow]All services have exited.[/yellow]\n")
    manager.stop_all()


def _show_error_panel(name: str, svc: ServiceProcess) -> None:
    """Show an actionable error panel for a failed service."""
    lines = []
    port = svc.port
    if port:
        lines.append(f"Port {port} may already be in use\n")
        lines.append(f"Try: [bold]lsof -i :{port}[/bold] to find the process")
        lines.append(f" or: set a different port in workbench.yaml")
    else:
        lines.append("The start command exited immediately.")
        lines.append(f"Check the command: [bold]{svc.command}[/bold]")
        lines.append("Run [bold]workbench up --verbose[/bold] for more detail.")

    panel = Panel(
        "\n".join(lines),
        title=f"{name} error",
        border_style="red",
        padding=(1, 2),
    )
    console.print()
    console.print(panel)

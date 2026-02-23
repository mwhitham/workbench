"""workbench status — dashboard showing repo and service status."""

from __future__ import annotations

from pathlib import Path

import typer
from rich.console import Console
from rich.table import Table

from cli.utils import git
from cli.utils.process import ProcessManager

console = Console()


def status_cmd() -> None:
    """Show repo and service status dashboard."""
    from cli.main import banner, state
    from cli.utils.config import load_config, find_workbench_yaml

    banner()

    config = load_config()
    workbench_root = find_workbench_yaml().parent

    if not config.repos:
        console.print("  [yellow]No repos defined in workbench.yaml[/yellow]\n")
        raise typer.Exit(1)

    # -- Repositories table -------------------------------------------------
    repo_table = Table(
        title="REPOSITORIES",
        title_style="bold",
        show_header=True,
        header_style="bold dim",
        border_style="dim",
        padding=(0, 2),
        expand=False,
    )
    repo_table.add_column("Repo", style="bold", min_width=16)
    repo_table.add_column("Branch", min_width=12)
    repo_table.add_column("Status", min_width=20)

    for name, repo_cfg in config.repos.items():
        rel_path = repo_cfg.path or f"repos/{name}"
        repo_path = workbench_root / rel_path

        if not repo_path.exists():
            repo_table.add_row(name, "[dim]—[/dim]", "[dim]not cloned[/dim]")
            continue

        info = git.get_status_summary(repo_path)

        # Build status string
        if info["dirty"]:
            status_str = f"[yellow]●[/yellow] {info['modified_count']} modified"
        else:
            status_str = "[green]✓[/green] clean"

        # Ahead/behind
        parts = []
        if info["ahead"]:
            parts.append(f"{info['ahead']} ahead")
        if info["behind"]:
            parts.append(f"{info['behind']} behind")
        if parts:
            status_str += f" [dim]· {' · '.join(parts)}[/dim]"

        repo_table.add_row(name, f"[cyan]{info['branch']}[/cyan]", status_str)

    console.print()
    console.print(repo_table)
    console.print()

    # -- Services table -----------------------------------------------------
    running_pids = ProcessManager.read_pid_files(workbench_root)

    svc_table = Table(
        title="SERVICES",
        title_style="bold",
        show_header=True,
        header_style="bold dim",
        border_style="dim",
        padding=(0, 2),
        expand=False,
    )
    svc_table.add_column("Service", style="bold", min_width=16)
    svc_table.add_column("Port", min_width=8)
    svc_table.add_column("Status", min_width=20)

    for name, repo_cfg in config.repos.items():
        is_infra = repo_cfg.is_infrastructure
        port = repo_cfg.port
        port_str = f":{port}" if port else "[dim]—[/dim]"

        if is_infra:
            svc_table.add_row(name, "[dim]—[/dim]", "[dim]reference only[/dim]")
        elif name in running_pids:
            running_port = running_pids[name].get("port")
            p_str = f":{running_port}" if running_port else port_str
            svc_table.add_row(name, p_str, "[green]● running[/green]")
        else:
            svc_table.add_row(name, port_str, "[dim]○ stopped[/dim]")

    console.print(svc_table)
    console.print()

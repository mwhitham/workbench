"""Process management for workbench services."""

from __future__ import annotations

import json
import os
import signal
import subprocess
import sys
import threading
import time
from pathlib import Path
from typing import Optional
from urllib.request import urlopen
from urllib.error import URLError

from rich.console import Console

# Color palette for per-service log prefixes
SERVICE_COLORS = ["cyan", "magenta", "yellow", "green", "blue", "red"]

WORKBENCH_DIR = Path(".workbench")
PID_DIR = WORKBENCH_DIR / "pids"


def _ensure_pid_dir(root: Path) -> Path:
    pid_dir = root / PID_DIR
    pid_dir.mkdir(parents=True, exist_ok=True)
    return pid_dir


class ServiceProcess:
    """Wraps a subprocess for a single service."""

    def __init__(
        self,
        name: str,
        command: str,
        cwd: Path,
        port: int | None = None,
        health_check: str | None = None,
        env: dict[str, str] | None = None,
        color: str = "cyan",
        workbench_root: Path | None = None,
    ) -> None:
        self.name = name
        self.command = command
        self.cwd = cwd
        self.port = port
        self.health_check = health_check
        self.color = color
        self.workbench_root = workbench_root or Path.cwd()

        self._env = {**os.environ, **(env or {})}
        self._proc: subprocess.Popen | None = None
        self._log_thread: threading.Thread | None = None

    # -- PID file helpers ---------------------------------------------------

    @property
    def _pid_file(self) -> Path:
        return _ensure_pid_dir(self.workbench_root) / f"{self.name}.pid"

    def _write_pid(self) -> None:
        self._pid_file.write_text(json.dumps({"pid": self._proc.pid, "port": self.port}))

    def _remove_pid(self) -> None:
        self._pid_file.unlink(missing_ok=True)

    # -- Lifecycle ----------------------------------------------------------

    def start(self) -> None:
        """Start the service subprocess."""
        self._proc = subprocess.Popen(
            self.command,
            shell=True,
            cwd=self.cwd,
            env=self._env,
            stdout=subprocess.PIPE,
            stderr=subprocess.STDOUT,
            text=True,
            preexec_fn=os.setsid,
        )
        self._write_pid()

    def stop(self, timeout: float = 5.0) -> None:
        """Stop the service (SIGTERM then SIGKILL)."""
        if self._proc is None:
            self._remove_pid()
            return
        try:
            os.killpg(os.getpgid(self._proc.pid), signal.SIGTERM)
            self._proc.wait(timeout=timeout)
        except (ProcessLookupError, subprocess.TimeoutExpired):
            try:
                os.killpg(os.getpgid(self._proc.pid), signal.SIGKILL)
                self._proc.wait(timeout=2)
            except (ProcessLookupError, OSError):
                pass
        self._proc = None
        self._remove_pid()

    def is_running(self) -> bool:
        if self._proc is None:
            return False
        return self._proc.poll() is None

    def wait_healthy(self, timeout: float = 30.0, interval: float = 1.0) -> bool:
        """Wait for the service to become healthy.

        Checks the health_check URL if set, otherwise just checks the process
        is alive after a brief delay.
        """
        deadline = time.monotonic() + timeout
        while time.monotonic() < deadline:
            if not self.is_running():
                return False
            if self.health_check:
                url = self.health_check
                # If health_check is a relative path, build a full URL
                if url.startswith("/") and self.port:
                    url = f"http://127.0.0.1:{self.port}{url}"
                elif not url.startswith("http"):
                    url = f"http://127.0.0.1:{self.port}/{url.lstrip('/')}" if self.port else None
                if url:
                    try:
                        resp = urlopen(url, timeout=2)
                        if 200 <= resp.status < 400:
                            return True
                    except (URLError, OSError, ValueError):
                        pass
            elif self.port:
                # No explicit health check — try connecting to the port
                import socket
                try:
                    with socket.create_connection(("127.0.0.1", self.port), timeout=1):
                        return True
                except OSError:
                    pass
            else:
                # No port or health check — just wait briefly and check alive
                time.sleep(2)
                return self.is_running()
            time.sleep(interval)
        return self.is_running()

    def stream_logs(self, console: Console) -> None:
        """Stream stdout lines with a colored prefix. Run in a thread."""
        if self._proc is None or self._proc.stdout is None:
            return
        tag = f"[{self.color}][{self.name:<12}][/{self.color}]"
        try:
            for line in self._proc.stdout:
                console.print(f"  {tag} {line.rstrip()}")
        except ValueError:
            pass  # stdout closed

    def start_log_thread(self, console: Console) -> None:
        """Start a daemon thread that streams logs."""
        self._log_thread = threading.Thread(
            target=self.stream_logs, args=(console,), daemon=True
        )
        self._log_thread.start()


class ProcessManager:
    """Manages multiple ServiceProcess instances."""

    def __init__(self, workbench_root: Path | None = None) -> None:
        self.root = workbench_root or Path.cwd()
        self.services: dict[str, ServiceProcess] = {}

    def add(self, svc: ServiceProcess) -> None:
        self.services[svc.name] = svc

    def start_all(self, console: Console) -> dict[str, bool]:
        """Start all registered services. Returns {name: healthy}."""
        results: dict[str, bool] = {}
        for name, svc in self.services.items():
            svc.start()
            results[name] = True  # started; health checked separately
        return results

    def stop_all(self) -> None:
        for svc in self.services.values():
            svc.stop()

    def stop_service(self, name: str) -> bool:
        if name in self.services:
            self.services[name].stop()
            return True
        return False

    def get_running(self) -> list[str]:
        return [n for n, s in self.services.items() if s.is_running()]

    # -- Static helpers for checking PID files (no live manager) ------------

    @staticmethod
    def read_pid_files(root: Path) -> dict[str, dict]:
        """Read all PID files and return {service_name: {pid, port}}."""
        pid_dir = root / PID_DIR
        if not pid_dir.exists():
            return {}
        result = {}
        for f in pid_dir.glob("*.pid"):
            try:
                data = json.loads(f.read_text())
                name = f.stem
                # Verify process is actually running
                try:
                    os.kill(data["pid"], 0)
                    result[name] = data
                except OSError:
                    # Process not running — stale PID file
                    f.unlink(missing_ok=True)
            except (json.JSONDecodeError, KeyError):
                f.unlink(missing_ok=True)
        return result

    @staticmethod
    def kill_by_pid_file(root: Path, name: str) -> bool:
        """Stop a service using its PID file."""
        pid_file = root / PID_DIR / f"{name}.pid"
        if not pid_file.exists():
            return False
        try:
            data = json.loads(pid_file.read_text())
            pid = data["pid"]
            try:
                os.killpg(os.getpgid(pid), signal.SIGTERM)
            except (ProcessLookupError, OSError):
                pass
            pid_file.unlink(missing_ok=True)
            return True
        except (json.JSONDecodeError, KeyError, OSError):
            pid_file.unlink(missing_ok=True)
            return False

#!/usr/bin/env python3
"""Cross-platform runtime primitives used by ContextGO.

This module is intentionally dependency-free.  It centralizes user directories,
private file handling, interpreter resolution, daemon state, and process
lifecycle so the rest of ContextGO does not assume POSIX tools are installed.
"""

from __future__ import annotations

import contextlib
import json
import os
import signal
import subprocess
import sys
import time
from dataclasses import dataclass
from pathlib import Path
from typing import Any

APP_NAME = "ContextGO"
LEGACY_STORAGE_NAME = ".contextgo"


def user_home() -> Path:
    """Return the effective user home, with a test/portable override."""
    override = os.environ.get("CONTEXTGO_HOME", "").strip()
    return Path(override).expanduser().resolve() if override else Path.home().expanduser().resolve()


def _home(home: Path | None = None) -> Path:
    return (home or user_home()).expanduser()


def _first_env_path(*names: str) -> Path | None:
    for name in names:
        value = os.environ.get(name, "").strip()
        if value:
            return Path(value).expanduser()
    return None


def platform_data_dir(home: Path | None = None) -> Path:
    """Return the native per-user data directory for ContextGO."""
    root = _home(home)
    if os.name == "nt":
        base = _first_env_path("LOCALAPPDATA", "APPDATA") or root / "AppData" / "Local"
    elif sys.platform == "darwin":
        base = root / "Library" / "Application Support"
    else:
        base = (_first_env_path("XDG_DATA_HOME") if home is None else None) or root / ".local" / "share"
    return base / "contextgo"


def platform_config_dir(home: Path | None = None) -> Path:
    """Return the native per-user configuration directory for ContextGO."""
    root = _home(home)
    if os.name == "nt":
        base = _first_env_path("APPDATA", "LOCALAPPDATA") or root / "AppData" / "Roaming"
    elif sys.platform == "darwin":
        base = root / "Library" / "Application Support"
    else:
        base = (_first_env_path("XDG_CONFIG_HOME") if home is None else None) or root / ".config"
    return base / "contextgo"


def platform_cache_dir(home: Path | None = None) -> Path:
    """Return the native per-user cache directory for ContextGO."""
    root = _home(home)
    if os.name == "nt":
        base = _first_env_path("LOCALAPPDATA", "TEMP", "TMP") or root / "AppData" / "Local"
    elif sys.platform == "darwin":
        base = root / "Library" / "Caches"
    else:
        base = (_first_env_path("XDG_CACHE_HOME") if home is None else None) or root / ".cache"
    return base / "contextgo"


def platform_state_dir(home: Path | None = None) -> Path:
    """Return a writable per-user state directory."""
    return platform_data_dir(home) / "state"


def storage_root(default_home_name: str = LEGACY_STORAGE_NAME, home: Path | None = None) -> Path:
    """Resolve ContextGO storage while preserving existing legacy data.

    ``CONTEXTGO_STORAGE_ROOT`` always wins.  An existing ``~/.contextgo`` is
    retained for backwards compatibility; a fresh install uses the native
    platform data directory.  Custom legacy names remain deterministic for
    callers and tests.
    """
    override = os.environ.get("CONTEXTGO_STORAGE_ROOT", "").strip()
    if override:
        return Path(override).expanduser().resolve()

    root = _home(home)
    legacy = root / default_home_name
    # Keep the historical ~/.contextgo location as the default so upgrades do
    # not silently fork an existing index.  Users who want native OS data
    # directories can opt in explicitly; config/cache already use native dirs.
    use_native = os.environ.get("CONTEXTGO_PLATFORM_STORAGE", "").strip().lower() in {"1", "true", "yes", "on"}
    if not use_native or default_home_name != LEGACY_STORAGE_NAME:
        return legacy.resolve()
    return platform_data_dir(root).resolve()


def config_dir() -> Path:
    """Return the ContextGO configuration directory."""
    override = os.environ.get("CONTEXTGO_CONFIG_DIR", "").strip()
    return Path(override).expanduser().resolve() if override else platform_config_dir().resolve()


def cache_dir() -> Path:
    """Return the ContextGO cache directory."""
    override = os.environ.get("CONTEXTGO_CACHE_DIR", "").strip()
    return Path(override).expanduser().resolve() if override else platform_cache_dir().resolve()


def ensure_private_dir(path: Path) -> Path:
    """Create a user-private directory where the platform permits mode bits."""
    path.mkdir(parents=True, exist_ok=True, mode=0o700)
    with contextlib.suppress(OSError):
        path.chmod(0o700)
    return path


def restrict_file(path: Path) -> None:
    """Apply owner-only mode on POSIX and best-effort protection elsewhere."""
    with contextlib.suppress(OSError):
        path.chmod(0o600)


def atomic_write_text(path: Path, text: str, *, mode: int = 0o600) -> None:
    """Atomically write UTF-8 text and keep the destination private."""
    ensure_private_dir(path.parent)
    tmp = path.with_name(f".{path.name}.{os.getpid()}.tmp")
    try:
        flags = os.O_WRONLY | os.O_CREAT | os.O_TRUNC
        fd = os.open(tmp, flags, mode)
        with os.fdopen(fd, "w", encoding="utf-8", newline="") as handle:
            handle.write(text)
            handle.flush()
            with contextlib.suppress(OSError):
                os.fsync(handle.fileno())
        os.replace(tmp, path)
        restrict_file(path)
    finally:
        with contextlib.suppress(OSError):
            tmp.unlink()


def atomic_write_json(path: Path, payload: Any, *, indent: int = 2) -> None:
    """Atomically write a JSON document with stable UTF-8 serialization."""
    atomic_write_text(path, json.dumps(payload, ensure_ascii=False, indent=indent) + "\n")


def runtime_python() -> str:
    """Return the interpreter running ContextGO, never a hard-coded ``python3``."""
    return sys.executable or ("python.exe" if os.name == "nt" else "python3")


def command_available(name: str) -> bool:
    """Return whether an optional external command is available."""
    from shutil import which

    return which(name) is not None


def tool_data_roots(home: Path | None = None) -> list[Path]:
    """Return common per-user data roots, including legacy home-relative data."""
    root = _home(home)
    roots = [root]
    if os.name == "nt":
        for candidate in (_first_env_path("APPDATA"), _first_env_path("LOCALAPPDATA")):
            if candidate:
                roots.append(candidate)
    elif sys.platform == "darwin":
        roots.append(root / "Library" / "Application Support")
    else:
        data_home = _first_env_path("XDG_DATA_HOME") if home is None else None
        roots.extend([data_home or root / ".local" / "share", root / ".config"])
    return _unique_paths(roots)


def tool_config_roots(home: Path | None = None) -> list[Path]:
    """Return common per-user configuration roots for adapters."""
    root = _home(home)
    roots = [root]
    if os.name == "nt":
        for candidate in (_first_env_path("APPDATA"), _first_env_path("LOCALAPPDATA")):
            if candidate:
                roots.append(candidate)
    elif sys.platform == "darwin":
        roots.extend([root / "Library" / "Application Support", root / ".config"])
    else:
        roots.extend([_first_env_path("XDG_CONFIG_HOME") or root / ".config", root / ".local" / "share"])
    return _unique_paths(roots)


def _unique_paths(paths: list[Path]) -> list[Path]:
    seen: set[str] = set()
    result: list[Path] = []
    for path in paths:
        key = os.path.normcase(os.path.normpath(str(path)))
        if key not in seen:
            seen.add(key)
            result.append(path)
    return result


def daemon_pid_path() -> Path:
    """Return the cross-platform daemon PID/lock path."""
    return ensure_private_dir(storage_root() / "logs") / "contextgo_daemon.lock"


def read_pid(path: Path | None = None) -> int | None:
    """Read a positive PID from a ContextGO lock file."""
    target = path or daemon_pid_path()
    try:
        value = int(target.read_text(encoding="utf-8").strip())
    except (OSError, ValueError):
        return None
    return value if value > 0 else None


def process_is_alive(pid: int) -> bool:
    """Return whether *pid* is alive without relying on POSIX-only commands."""
    if pid <= 0:
        return False
    try:
        os.kill(pid, 0)
    except PermissionError:
        return True
    except OSError:
        return False
    return True


@dataclass(frozen=True)
class DaemonStatus:
    running: bool
    pid: int | None
    pid_file: str
    service: str


def daemon_status() -> DaemonStatus:
    """Return daemon state from the portable PID lock."""
    pid_file = daemon_pid_path()
    pid = read_pid(pid_file)
    return DaemonStatus(
        running=bool(pid and process_is_alive(pid)),
        pid=pid,
        pid_file=str(pid_file),
        service=service_name(),
    )


def service_name() -> str:
    if os.name == "nt":
        return "Task Scheduler: ContextGO"
    if sys.platform == "darwin":
        return "launchd: com.contextgo.daemon"
    return "systemd-user: contextgo.service"


def start_daemon(*, module: str = "contextgo.context_daemon") -> int:
    """Start the daemon detached from the current console and return its PID."""
    current = daemon_status()
    if current.running and current.pid:
        return current.pid
    ensure_private_dir(storage_root() / "logs")
    stdout_path = storage_root() / "logs" / "daemon-launcher.log"
    handle = stdout_path.open("a", encoding="utf-8")
    kwargs: dict[str, Any] = {
        "stdin": subprocess.DEVNULL,
        "stdout": handle,
        "stderr": subprocess.STDOUT,
        "cwd": str(storage_root()),
        "env": os.environ.copy(),
    }
    if os.name == "nt":
        flags = getattr(subprocess, "DETACHED_PROCESS", 0) | getattr(subprocess, "CREATE_NEW_PROCESS_GROUP", 0)
        if flags:
            kwargs["creationflags"] = flags
    else:
        kwargs["start_new_session"] = True
    try:
        proc = subprocess.Popen([runtime_python(), "-m", module], **kwargs)
    finally:
        handle.close()
    deadline = time.monotonic() + 5
    while time.monotonic() < deadline:
        status = daemon_status()
        if status.running and status.pid:
            return status.pid
        if proc.poll() is not None:
            break
        time.sleep(0.1)
    return proc.pid


def stop_daemon(*, timeout: float = 10.0) -> bool:
    """Request graceful daemon shutdown and wait for the PID to disappear."""
    status = daemon_status()
    if not status.pid:
        return True
    try:
        os.kill(status.pid, signal.SIGTERM)
    except OSError:
        return True
    deadline = time.monotonic() + timeout
    while time.monotonic() < deadline:
        if not process_is_alive(status.pid):
            return True
        time.sleep(0.1)
    return not process_is_alive(status.pid)


def install_service() -> dict[str, object]:
    """Install a per-user service definition using the native OS mechanism."""
    cfg = config_dir()
    ensure_private_dir(cfg)
    python = runtime_python()
    if os.name == "nt":
        launcher = cfg / "contextgo-daemon.cmd"
        atomic_write_text(launcher, f'@echo off\r\n"{python}" -m contextgo.context_daemon\r\n', mode=0o700)
        task_name = "ContextGO"
        if not command_available("schtasks"):
            return {"installed": False, "service": service_name(), "path": str(launcher), "error": "schtasks not found"}
        proc = subprocess.run(
            ["schtasks", "/Create", "/TN", task_name, "/TR", str(launcher), "/SC", "ONLOGON", "/F"],
            capture_output=True,
            text=True,
            check=False,
        )
        return {
            "installed": proc.returncode == 0,
            "service": service_name(),
            "path": str(launcher),
            "returncode": proc.returncode,
        }
    if sys.platform == "darwin":
        path = _write_launchd_service(cfg, python)
        return {"installed": True, "service": service_name(), "path": str(path)}
    path = _write_systemd_service(cfg, python)
    if command_available("systemctl"):
        subprocess.run(["systemctl", "--user", "daemon-reload"], check=False, capture_output=True)
        subprocess.run(["systemctl", "--user", "enable", "contextgo.service"], check=False, capture_output=True)
    return {"installed": True, "service": service_name(), "path": str(path)}


def uninstall_service() -> dict[str, object]:
    """Remove the per-user service definition without touching user data."""
    if os.name == "nt":
        result: dict[str, object] = {"service": service_name(), "removed": True}
        if command_available("schtasks"):
            proc = subprocess.run(
                ["schtasks", "/Delete", "/TN", "ContextGO", "/F"], capture_output=True, text=True, check=False
            )
            result.update({"removed": proc.returncode == 0, "returncode": proc.returncode})
        with contextlib.suppress(OSError):
            (config_dir() / "contextgo-daemon.cmd").unlink()
        return result
    if sys.platform == "darwin":
        path = Path.home() / "Library" / "LaunchAgents" / "com.contextgo.daemon.plist"
    else:
        path = Path.home() / ".config" / "systemd" / "user" / "contextgo.service"
        if command_available("systemctl"):
            subprocess.run(
                ["systemctl", "--user", "disable", "--now", "contextgo.service"], check=False, capture_output=True
            )
    with contextlib.suppress(OSError):
        path.unlink()
    return {"service": service_name(), "removed": True, "path": str(path)}


def _write_launchd_service(cfg: Path, python: str) -> Path:
    path = Path.home() / "Library" / "LaunchAgents" / "com.contextgo.daemon.plist"
    ensure_private_dir(path.parent)
    content = f"""<?xml version="1.0" encoding="UTF-8"?>
<!DOCTYPE plist PUBLIC "-//Apple//DTD PLIST 1.0//EN" "http://www.apple.com/DTDs/PropertyList-1.0.dtd">
<plist version="1.0"><dict>
<key>Label</key><string>com.contextgo.daemon</string>
<key>ProgramArguments</key><array><string>{python}</string><string>-m</string><string>contextgo.context_daemon</string></array>
<key>RunAtLoad</key><true/><key>KeepAlive</key><true/>
</dict></plist>
"""
    atomic_write_text(path, content)
    return path


def _write_systemd_service(cfg: Path, python: str) -> Path:
    path = Path.home() / ".config" / "systemd" / "user" / "contextgo.service"
    ensure_private_dir(path.parent)
    content = f"""[Unit]
Description=ContextGO context and memory daemon
After=default.target

[Service]
ExecStart={python} -m contextgo.context_daemon
Restart=on-failure
RestartSec=5

[Install]
WantedBy=default.target
"""
    atomic_write_text(path, content)
    return path

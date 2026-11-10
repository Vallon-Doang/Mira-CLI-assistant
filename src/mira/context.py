"""Lightweight, privacy-conscious environment detection."""

from __future__ import annotations

import os
import platform
import pwd
import shutil
import subprocess
from dataclasses import dataclass, field
from pathlib import Path

TOOL_CANDIDATES = (
    "git",
    "python3",
    "pip",
    "pip3",
    "dnf",
    "systemctl",
    "journalctl",
    "firewall-cmd",
    "docker",
    "podman",
    "npm",
    "cargo",
    "godot",
    "nvidia-smi",
    "ss",
    "ip",
    "curl",
    "wget",
    "make",
    "gcc",
)

PROJECT_MARKERS: tuple[tuple[str, tuple[str, ...]], ...] = (
    ("Python", ("pyproject.toml", "setup.py", "setup.cfg", "requirements.txt")),
    ("Laravel (PHP)", ("composer.json", "artisan")),
    ("PHP", ("composer.json",)),
    ("Node.js", ("package.json",)),
    ("Rust", ("Cargo.toml",)),
    ("Godot", ("project.godot",)),
)

_MAX_PARENT_LEVELS = 3


@dataclass
class ContextSnapshot:
    os_name: str
    os_id: str
    os_version: str
    kernel: str
    arch: str
    shell: str | None
    cwd_name: str | None
    project_types: list[str] = field(default_factory=list)
    project_files: list[str] = field(default_factory=list)
    git_repo: bool = False
    git_branch: str | None = None
    git_dirty: bool | None = None
    tools: list[str] = field(default_factory=list)

    @property
    def workspace_label(self) -> str:
        if self.cwd_name is None:
            return "unknown"
        if self.project_types:
            return f"{', '.join(self.project_types)} project ({self.cwd_name})"
        return f"directory ({self.cwd_name})"

    def to_prompt(self) -> str:
        lines = [
            f"OS: {self.os_name}" + (f" {self.os_version}" if self.os_version else ""),
            f"Kernel: {self.kernel}",
            f"Architecture: {self.arch}",
        ]
        if self.shell:
            lines.append(f"Shell: {self.shell}")
        if self.cwd_name is not None:
            lines.append(f"Workspace: {self.workspace_label}")
        if self.project_files:
            lines.append("Project files: " + ", ".join(self.project_files))
        if self.git_repo:
            branch = self.git_branch or "unknown"
            dirty = " (dirty)" if self.git_dirty else ""
            lines.append(f"Git branch: {branch}{dirty}")
        if self.tools:
            lines.append("Available tools: " + ", ".join(self.tools))
        return "\n".join(lines)

    def to_dict(self) -> dict[str, object]:
        return {
            "os": self.os_name,
            "os_id": self.os_id,
            "os_version": self.os_version,
            "kernel": self.kernel,
            "arch": self.arch,
            "shell": self.shell,
            "workspace": self.workspace_label,
            "cwd_name": self.cwd_name,
            "project_types": list(self.project_types),
            "project_files": list(self.project_files),
            "git_repo": self.git_repo,
            "git_branch": self.git_branch,
            "git_dirty": self.git_dirty,
            "tools": list(self.tools),
        }


_STATIC_CACHE: dict[str, str] | None = None


def collect_context(enabled: bool = True, cwd: Path | None = None) -> ContextSnapshot:
    """Collect a fresh snapshot. Static OS facts are cached per process."""
    static = _static_info()
    if not enabled:
        return ContextSnapshot(
            os_name=static["os_name"],
            os_id=static["os_id"],
            os_version=static["os_version"],
            kernel=static["kernel"],
            arch=static["arch"],
            shell=None,
            cwd_name=None,
        )

    try:
        workdir = Path(cwd) if cwd is not None else Path.cwd()
        cwd_name = workdir.name or "root"
    except OSError:
        workdir = None
        cwd_name = None

    projects: list[str] = []
    project_files: list[str] = []
    git_repo = False
    git_branch: str | None = None
    git_dirty: bool | None = None

    if workdir is not None:
        projects, repo_root, project_files = _detect_projects(workdir)
        git_repo = repo_root is not None
        if repo_root is not None:
            git_branch, git_dirty = _git_state(repo_root)

    return ContextSnapshot(
        os_name=static["os_name"],
        os_id=static["os_id"],
        os_version=static["os_version"],
        kernel=static["kernel"],
        arch=static["arch"],
        shell=_detect_shell(),
        cwd_name=cwd_name,
        project_types=projects,
        project_files=project_files,
        git_repo=git_repo,
        git_branch=git_branch,
        git_dirty=git_dirty,
        tools=[tool for tool in TOOL_CANDIDATES if shutil.which(tool)],
    )


def _static_info() -> dict[str, str]:
    global _STATIC_CACHE
    if _STATIC_CACHE is not None:
        return _STATIC_CACHE
    release = _read_os_release()
    os_name = release.get("NAME") or platform.system() or "Linux"
    os_id = (release.get("ID") or os_name).lower()
    os_version = release.get("VERSION_ID") or ""
    uname = os.uname()
    _STATIC_CACHE = {
        "os_name": os_name,
        "os_id": os_id,
        "os_version": os_version,
        "kernel": uname.release,
        "arch": uname.machine,
    }
    return _STATIC_CACHE


def _read_os_release(path: str = "/etc/os-release") -> dict[str, str]:
    try:
        text = Path(path).read_text(encoding="utf-8", errors="replace")
    except OSError:
        return {}
    result: dict[str, str] = {}
    for line in text.splitlines():
        line = line.strip()
        if not line or line.startswith("#") or "=" not in line:
            continue
        key, value = line.split("=", 1)
        value = value.strip()
        if len(value) >= 2 and value[0] == value[-1] and value[0] in ("'", '"'):
            value = value[1:-1]
        result[key.strip()] = value.replace('\\"', '"').replace("\\$", "$")
    return result


def _detect_shell() -> str | None:
    env_shell = os.environ.get("SHELL")
    if env_shell:
        return Path(env_shell).name
    try:
        parent = Path(f"/proc/{os.getppid()}/comm").read_text(encoding="utf-8").strip()
        if parent and parent not in ("python", "python3"):
            return parent
    except OSError:
        pass
    try:
        return Path(pwd.getpwuid(os.getuid()).pw_shell).name
    except (KeyError, OSError):
        return None


def _detect_projects(start: Path) -> tuple[list[str], Path | None, list[str]]:
    current = start
    for _ in range(_MAX_PARENT_LEVELS + 1):
        try:
            names = {entry.name for entry in current.iterdir()}
        except OSError:
            return [], None, []

        found: list[str] = []
        for label, markers in PROJECT_MARKERS:
            if label == "Laravel (PHP)":
                if all(marker in names for marker in markers):
                    found.append(label)
            elif any(marker in names for marker in markers):
                found.append(label)
        if "PHP" in found and "Laravel (PHP)" in found:
            found.remove("PHP")

        files: list[str] = []
        for _, markers in PROJECT_MARKERS:
            for marker in markers:
                if marker in names and marker not in files:
                    files.append(marker)
        files = files[:5]

        repo_root = current if ".git" in names else None
        if found or repo_root is not None:
            if repo_root is not None and not found:
                found.append("Git repository")
            return found, repo_root, files

        parent = current.parent
        if parent == current:
            break
        current = parent
    return [], None, []


def _git_state(repo: Path) -> tuple[str | None, bool | None]:
    if shutil.which("git") is None:
        return None, None
    base = ["git", "-C", str(repo), "-c", "core.fsmonitor=false", "--no-optional-locks"]
    try:
        branch = subprocess.run(
            base + ["rev-parse", "--abbrev-ref", "HEAD"],
            capture_output=True,
            text=True,
            timeout=1.0,
            check=False,
        )
        branch_name = branch.stdout.strip() if branch.returncode == 0 else None
        if not branch_name:
            symbolic = subprocess.run(
                base + ["symbolic-ref", "--short", "HEAD"],
                capture_output=True,
                text=True,
                timeout=1.0,
                check=False,
            )
            branch_name = symbolic.stdout.strip() if symbolic.returncode == 0 else None
        status = subprocess.run(
            base + ["status", "--porcelain"],
            capture_output=True,
            text=True,
            timeout=1.0,
            check=False,
        )
    except (OSError, subprocess.TimeoutExpired):
        return None, None
    dirty = bool(status.stdout.strip()) if status.returncode == 0 else None
    return (branch_name or None), dirty

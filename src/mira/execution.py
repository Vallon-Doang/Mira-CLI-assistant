"""Opt-in command proposal extraction, risk classification, and execution.

The model never runs anything.  It may propose at most one command.  MIRA
classifies that command deterministically, then decides whether it is safe to
run automatically, needs confirmation, or must be refused.

This module deliberately keeps policy separate from I/O so it can be tested
without a terminal, Ollama, or a real command.
"""

from __future__ import annotations

import os
import re
import shlex
import signal
import subprocess
import time
from dataclasses import dataclass, field
from pathlib import Path

RISK_SAFE = "safe"
RISK_MODERATE = "moderate"
RISK_DESTRUCTIVE = "destructive"

STATUS_NO_COMMAND = "no_command"
STATUS_AMBIGUOUS = "ambiguous"
STATUS_EXECUTED = "executed"
STATUS_DECLINED = "declined"
STATUS_CONFIRMATION_REQUIRED = "confirmation_required"
STATUS_REFUSED_DESTRUCTIVE = "refused_destructive"
STATUS_SPAWN_FAILED = "spawn_failed"

_COMMAND_RE = re.compile(r"(?im)^[ \t]*COMMAND:[ \t]*(.+?)[ \t]*$")
_FENCE_RE = re.compile(r"```(?:bash|sh|shell|console)?[ \t]*\n(.*?)```", re.S | re.I)
_PROSE_STARTS = {
    "a", "an", "and", "as", "at", "be", "because", "but", "by", "check",
    "command", "do", "execute", "first", "for", "from", "here", "if", "in",
    "it", "note", "on", "or", "run", "so", "that", "the", "then", "this",
    "to", "try", "use", "we", "when", "with", "you", "your",
}

# Read-only diagnostics.  A few of these have argument-sensitive exceptions
# handled by _base_risk.
_SAFE_BASES = {
    "ls", "cat", "head", "tail", "wc", "df", "du", "free", "uptime", "uname",
    "whoami", "id", "pwd", "date", "which", "whereis", "type", "ss", "dig",
    "host", "nslookup", "resolvectl", "nvidia-smi", "sensors", "lsblk",
    "findmnt", "ps", "pgrep", "lsof", "stat", "file", "grep", "rg", "sort",
    "uniq", "cut", "tr", "nl", "basename", "dirname", "realpath", "readlink",
    "echo", "printf", "test", "[", "true", "false", "getenforce", "hostname",
    "dmesg", "lsusb", "lspci", "lscpu", "lsmem", "vmstat", "iostat", "mpstat",
    "pidstat", "sar", "smartctl", "systemd-analyze", "who", "w", "last",
    "lastlog", "groups", "getent", "locale", "timedatectl", "localectl",
    "hostnamectl", "loginctl", "bootctl", "systemctl", "journalctl", "git",
    "dnf", "rpm", "firewall-cmd", "nmcli", "ip", "ping", "docker", "podman",
    "ollama", "find",
}

# Commands that can change local state but do not usually delete data.
_MODERATE_BASES = {
    "cp", "mv", "ln", "mkdir", "touch", "install", "tee", "sed", "awk",
    "tar", "zip", "unzip", "gzip", "gunzip", "xz", "zstd", "7z", "openssl",
    "gpg", "curl", "wget", "nc", "netcat", "telnet", "socat", "top", "htop",
    "less", "more", "vi", "vim", "nano", "emacs", "apt", "apt-get", "pacman",
    "zypper", "flatpak", "snap", "pip", "pip3", "npm", "yarn", "pnpm", "cargo",
    "go", "make", "cmake", "timeout", "nice", "nohup", "stdbuf",
}

# Commands that can delete data, change permissions, or take the machine down.
_DESTRUCTIVE_BASES = {
    "rm", "rmdir", "dd", "mkfs", "mke2fs", "mkswap", "wipefs", "fdisk",
    "sfdisk", "parted", "shred", "truncate", "shutdown", "reboot", "poweroff",
    "halt", "kill", "pkill", "killall", "chmod", "chown", "chgrp", "chattr",
    "setfacl", "useradd", "userdel", "usermod", "groupadd", "groupdel",
    "passwd", "mount", "umount", "swapoff", "swapon", "crontab", "at", "batch",
    "sudo", "su", "doas", "pkexec", "bash", "sh", "zsh", "fish", "dash", "ksh",
    "eval", "exec", "source", ".", "python", "python3", "node", "ruby", "perl",
    "php", "ssh", "scp", "sftp", "rsync", "xargs", "watch", "env", "iptables",
    "nft", "ufw", "systemd-run",
}

_PACKAGE_SAFE = {
    "list", "info", "search", "repolist", "provides", "show", "policy",
    "check-update", "whatprovides", "deplist", "repoquery", "freeze", "check",
    "index", "outdated", "audit", "view", "ls", "metadata", "tree", "find",
    "list-updates", "repos", "packages", "version", "--version",
}
_PACKAGE_MODERATE = {
    "install", "reinstall", "upgrade", "update", "distro-sync", "dist-upgrade",
    "full-upgrade", "group", "module", "config-manager", "clean", "download",
    "wheel", "ci", "refresh", "dup", "build-dep", "source", "-S", "-Syu",
}
_PACKAGE_DESTRUCTIVE = {
    "remove", "erase", "autoremove", "uninstall", "purge", "rm", "publish",
    "run", "-R", "-Rns", "-Sc",
}

_GIT_SAFE = {
    "status", "log", "diff", "show", "rev-parse", "ls-files", "describe",
    "blame", "shortlog", "branch", "remote", "config", "tag", "stash",
    "worktree", "fsck",
}
_GIT_MODERATE = {
    "add", "commit", "push", "pull", "fetch", "clone", "checkout", "switch",
    "merge", "cherry-pick", "revert", "init", "mv", "gc", "submodule", "bisect",
}
_GIT_DESTRUCTIVE = {"reset", "clean", "rm", "restore", "rebase", "prune"}

_SYSTEMCTL_SAFE = {
    "status", "is-active", "is-enabled", "is-failed", "list-units",
    "list-unit-files", "list-jobs", "list-sockets", "list-timers",
    "list-machines", "show", "cat", "get-default",
}
_SYSTEMCTL_MODERATE = {
    "start", "restart", "reload", "enable", "disable", "unmask", "daemon-reload",
}
_SYSTEMCTL_DESTRUCTIVE = {
    "stop", "mask", "isolate", "poweroff", "reboot", "halt", "suspend",
    "hibernate", "kill", "set-default",
}

_CONTAINER_SAFE = {
    "ps", "images", "logs", "inspect", "version", "info", "stats", "top",
    "port", "diff", "history", "search",
}
_CONTAINER_MODERATE = {
    "start", "stop", "restart", "pull", "build", "create", "cp", "commit",
    "tag", "push", "login", "logout", "pause", "unpause",
}
_CONTAINER_DESTRUCTIVE = {"run", "exec", "rm", "rmi", "prune", "kill", "system"}

_OLLAMA_SAFE = {"list", "ps", "show", "--version"}
_OLLAMA_MODERATE = {"run", "serve", "pull", "push", "create", "cp", "stop"}
_OLLAMA_DESTRUCTIVE = {"rm"}

_KNOWN_BASES = _SAFE_BASES | _MODERATE_BASES | _DESTRUCTIVE_BASES


@dataclass(frozen=True)
class CommandPlan:
    """A proposed command plus MIRA's deterministic safety judgement."""

    command: str
    argv: tuple[str, ...]
    shell: bool
    risk: str
    reason: str
    shell_features: tuple[str, ...] = field(default_factory=tuple)

    @property
    def auto_run(self) -> bool:
        return self.risk == RISK_SAFE and not self.shell

    def to_dict(self) -> dict[str, object]:
        return {
            "command": self.command,
            "risk": self.risk,
            "reason": self.reason,
            "shell": self.shell,
            "shell_features": list(self.shell_features),
        }


@dataclass
class ExecutionResult:
    """Outcome of a proposed command, including refusals."""

    status: str
    command: str | None = None
    risk: str | None = None
    reason: str | None = None
    shell: bool = False
    shell_features: list[str] = field(default_factory=list)
    executed: bool = False
    exit_code: int | None = None
    stdout: str = ""
    stderr: str = ""
    timed_out: bool = False
    truncated: bool = False
    duration_ms: float | None = None
    message: str | None = None

    def to_dict(self) -> dict[str, object]:
        return {
            "status": self.status,
            "command": self.command,
            "risk": self.risk,
            "reason": self.reason,
            "shell": self.shell,
            "shell_features": self.shell_features,
            "executed": self.executed,
            "exit_code": self.exit_code,
            "stdout": self.stdout,
            "stderr": self.stderr,
            "timed_out": self.timed_out,
            "truncated": self.truncated,
            "duration_ms": round(self.duration_ms, 1) if self.duration_ms is not None else None,
            "message": self.message,
        }


def extract_command(text: str) -> tuple[str, str | None, str | None]:
    """Extract at most one proposed command from a model response.

    Returns ``(cleaned_text, command, issue)``.  ``issue`` is set when the
    response is ambiguous or malformed; in that case nothing is executed.
    """
    matches = list(_COMMAND_RE.finditer(text))
    if len(matches) > 1:
        return text, None, "multiple COMMAND lines were proposed"
    if matches:
        command = _clean_command(matches[0].group(1))
        if not command:
            return text, None, "an empty command was proposed"
        cleaned = text[: matches[0].start()] + text[matches[0].end() :]
        return _tidy(cleaned), command, None

    blocks = list(_FENCE_RE.finditer(text))
    if len(blocks) > 1:
        return text, None, "multiple code blocks were proposed"
    if len(blocks) == 1:
        body = blocks[0].group(1)
        lines = [
            line.strip()
            for line in body.splitlines()
            if line.strip() and not line.strip().startswith("#")
        ]
        if len(lines) != 1:
            return text, None, "the code block must contain exactly one command"
        command = _clean_command(lines[0])
        if not command:
            return text, None, "an empty command was proposed"
        cleaned = text[: blocks[0].start()] + text[blocks[0].end() :]
        return _tidy(cleaned), command, None

    fallback = _fallback_command(text)
    if fallback is not None:
        command, cleaned = fallback
        return cleaned, command, None

    return text, None, None


def classify(command: str) -> CommandPlan:
    """Classify one command without running it."""
    raw = command.strip()
    features = tuple(detect_shell_features(raw))
    shell = bool(features)
    parse_error = False
    try:
        tokens = tuple(shlex.split(raw))
    except ValueError:
        tokens = tuple(raw.split())
        parse_error = True

    if not tokens:
        return CommandPlan(
            command=raw,
            argv=(),
            shell=True,
            risk=RISK_DESTRUCTIVE,
            reason="the command is empty",
            shell_features=features,
        )

    base = Path(tokens[0]).name
    risk, reason = _base_risk(base, tokens)

    lowered = tuple(Path(token).name for token in tokens)
    if any(token in _DESTRUCTIVE_BASES for token in lowered[1:]):
        risk = RISK_DESTRUCTIVE
        reason = "contains a destructive command"
    elif risk == RISK_SAFE and any(token in _MODERATE_BASES for token in lowered[1:]):
        risk = RISK_MODERATE
        reason = "contains a state-changing command"

    if "sudo" in lowered or "su" in lowered or "doas" in lowered or "pkexec" in lowered:
        risk = RISK_DESTRUCTIVE
        reason = "runs with elevated privileges"
    if "$(" in raw or "`" in raw:
        risk = RISK_DESTRUCTIVE
        reason = "contains command substitution"
    if shell and risk == RISK_SAFE:
        risk = RISK_MODERATE
        reason = "uses shell features"
    if parse_error:
        shell = True
        risk = RISK_DESTRUCTIVE
        reason = "could not be parsed safely"

    return CommandPlan(
        command=raw,
        argv=tokens,
        shell=shell,
        risk=risk,
        reason=reason,
        shell_features=features,
    )


def detect_shell_features(command: str) -> list[str]:
    """Return human-readable shell features found outside quotes."""
    unquoted = re.sub(r"'[^']*'|\"[^\"]*\"", "", command)
    checks = (
        ("&&", "AND chain"),
        ("||", "OR chain"),
        ("|", "pipe"),
        ("&", "background operator"),
        (";", "command separator"),
        ("$(", "command substitution"),
        ("`", "command substitution"),
        ("<", "input redirection"),
        (">", "output redirection"),
        ("$", "variable expansion"),
        ("(", "subshell"),
        (")", "subshell"),
        ("\n", "multi-line command"),
        ("*", "glob"),
        ("?", "glob"),
        ("[", "glob"),
        ("]", "glob"),
        ("{", "brace expansion"),
        ("}", "brace expansion"),
        ("~", "home expansion"),
        ("#", "comment"),
    )
    found: list[str] = []
    for token, label in checks:
        if token in unquoted and label not in found:
            found.append(label)
    return found


def execute_plan(
    plan: CommandPlan,
    timeout: float = 30.0,
    max_output: int = 20_000,
    cwd: str | os.PathLike[str] | None = None,
) -> ExecutionResult:
    """Run a plan, capturing output.  Never uses ``shell=True`` directly."""
    result = ExecutionResult(
        status=STATUS_EXECUTED,
        command=plan.command,
        risk=plan.risk,
        reason=plan.reason,
        shell=plan.shell,
        shell_features=list(plan.shell_features),
        executed=True,
    )
    if plan.shell:
        argv = ["bash", "-lc", plan.command]
    else:
        argv = list(plan.argv)
    if not argv:
        result.status = STATUS_SPAWN_FAILED
        result.executed = False
        result.exit_code = 127
        result.message = "no command to run"
        return result

    started = time.perf_counter()
    try:
        proc = subprocess.Popen(
            argv,
            stdin=subprocess.DEVNULL,
            stdout=subprocess.PIPE,
            stderr=subprocess.PIPE,
            encoding="utf-8",
            errors="replace",
            cwd=cwd,
            start_new_session=True,
        )
    except FileNotFoundError:
        result.status = STATUS_SPAWN_FAILED
        result.executed = False
        result.exit_code = 127
        result.stderr = f"{argv[0]}: command not found"
        result.duration_ms = (time.perf_counter() - started) * 1000.0
        return result
    except OSError as exc:
        result.status = STATUS_SPAWN_FAILED
        result.executed = False
        result.exit_code = 126
        result.stderr = str(exc)
        result.duration_ms = (time.perf_counter() - started) * 1000.0
        return result

    try:
        stdout, stderr = proc.communicate(timeout=timeout)
    except subprocess.TimeoutExpired:
        try:
            os.killpg(os.getpgid(proc.pid), signal.SIGKILL)
        except (ProcessLookupError, PermissionError):
            pass
        stdout, stderr = proc.communicate()
        result.timed_out = True
        result.message = f"timed out after {timeout:g}s"

    result.exit_code = proc.returncode
    result.stdout, stdout_cut = _truncate(stdout, max_output)
    result.stderr, stderr_cut = _truncate(stderr, max_output)
    result.truncated = stdout_cut or stderr_cut
    result.duration_ms = (time.perf_counter() - started) * 1000.0
    return result


def _base_risk(base: str, tokens: tuple[str, ...]) -> tuple[str, str]:
    if base == "git":
        return _git_risk(tokens)
    if base == "systemctl":
        return _systemctl_risk(tokens)
    if base == "journalctl":
        if any(
            token.startswith("--vacuum")
            or token in ("--rotate", "--flush", "--sync", "--relinquish-var")
            for token in tokens[1:]
        ):
            return RISK_DESTRUCTIVE, "journalctl can delete or rotate logs"
        if any(token in ("-f", "--follow") for token in tokens[1:]):
            return RISK_MODERATE, "journalctl --follow runs until interrupted"
        return RISK_SAFE, "read-only log query"
    if base in ("dnf", "apt", "apt-get", "pacman", "zypper", "flatpak", "snap",
                "pip", "pip3", "npm", "yarn", "pnpm", "cargo"):
        return _package_risk(tokens)
    if base == "rpm":
        return _rpm_risk(tokens)
    if base == "firewall-cmd":
        return _firewall_risk(tokens)
    if base == "nmcli":
        return _nmcli_risk(tokens)
    if base == "ip":
        return _ip_risk(tokens)
    if base == "ping":
        if any(token in ("-c", "-w", "-W") for token in tokens[1:]):
            return RISK_SAFE, "bounded network probe"
        return RISK_MODERATE, "ping can run indefinitely without -c"
    if base in ("docker", "podman"):
        return _container_risk(tokens)
    if base == "ollama":
        return _ollama_risk(tokens)
    if base == "find":
        if any(
            token in ("-delete", "-exec", "-execdir", "-ok", "-okdir", "-fprint",
                      "-fprint0", "-fprintf", "-fls")
            for token in tokens[1:]
        ):
            return RISK_DESTRUCTIVE, "find can delete files or run commands"
        return RISK_SAFE, "read-only file search"
    if base == "hostnamectl":
        if len(tokens) == 1 or tokens[1] in ("status", "show"):
            return RISK_SAFE, "read-only hostname query"
        return RISK_DESTRUCTIVE, "hostnamectl can change the hostname"
    if base == "timedatectl":
        if len(tokens) == 1 or tokens[1] in ("status", "show", "list-timezones"):
            return RISK_SAFE, "read-only time query"
        return RISK_MODERATE, "timedatectl can change system time"
    if base == "localectl":
        if len(tokens) == 1 or tokens[1] in ("status", "show"):
            return RISK_SAFE, "read-only locale query"
        return RISK_MODERATE, "localectl can change locale settings"
    if base == "date":
        if any(token in ("-s", "--set") for token in tokens[1:]):
            return RISK_DESTRUCTIVE, "date can change the system clock"
        return RISK_SAFE, "read-only date query"
    if base == "sed":
        if any(token.startswith("-i") or token == "--in-place" for token in tokens[1:]):
            return RISK_DESTRUCTIVE, "sed -i can overwrite files in place"
        return RISK_MODERATE, "sed can transform file content"
    if base.startswith("mkfs"):
        return RISK_DESTRUCTIVE, "mkfs can destroy a filesystem"
    if base == "hostname":
        if len(tokens) > 1:
            return RISK_DESTRUCTIVE, "hostname can change the system hostname"
        return RISK_SAFE, "read-only hostname query"
    if base == "tail":
        if any(token in ("-f", "-F", "--follow") for token in tokens[1:]):
            return RISK_MODERATE, "tail --follow runs until interrupted"
        return RISK_SAFE, "read-only file query"
    if base == "dmesg":
        if any(token in ("-C", "-c", "--clear", "--read-clear") for token in tokens[1:]):
            return RISK_DESTRUCTIVE, "dmesg can clear the kernel ring buffer"
        if any(token in ("-w", "--follow") for token in tokens[1:]):
            return RISK_MODERATE, "dmesg --follow runs until interrupted"
        return RISK_SAFE, "read-only kernel log query"
    if base == "smartctl":
        if any(token in ("-t", "--test", "-s", "--set") for token in tokens[1:]):
            return RISK_DESTRUCTIVE, "smartctl can change or test a disk"
        return RISK_SAFE, "read-only disk health query"
    if base == "resolvectl":
        if any(token in ("flush-caches", "reset-server-features") for token in tokens[1:]):
            return RISK_MODERATE, "resolvectl can change resolver state"
        return RISK_SAFE, "read-only DNS query"
    if base in _SAFE_BASES:
        return RISK_SAFE, "read-only diagnostic command"
    if base in _MODERATE_BASES:
        return RISK_MODERATE, f"{base} can modify state"
    if base in _DESTRUCTIVE_BASES:
        return RISK_DESTRUCTIVE, f"{base} can delete data or change system state"
    return RISK_MODERATE, f"unknown command {base!r} requires confirmation"


def _git_risk(tokens: tuple[str, ...]) -> tuple[str, str]:
    sub = _find_subcommand(tokens, _GIT_SAFE | _GIT_MODERATE | _GIT_DESTRUCTIVE)
    if sub in _GIT_DESTRUCTIVE:
        return RISK_DESTRUCTIVE, f"git {sub} can discard or delete work"
    if sub == "push" and any(token in ("--force", "-f", "--force-with-lease") for token in tokens):
        return RISK_DESTRUCTIVE, "git push --force can overwrite remote history"
    if sub == "branch" and any(
        token in ("-d", "-D", "--delete") for token in tokens
    ):
        return RISK_DESTRUCTIVE, "git branch --delete can discard branch work"
    if sub == "branch" and any(
        token in ("-m", "-M", "--move", "-c", "-C", "--copy") for token in tokens
    ):
        return RISK_MODERATE, "git branch can modify branches"
    if sub == "remote":
        action = _first_value(tokens, skip={"remote"})
        if action in ("add", "remove", "rename", "set-url", "prune", "update"):
            return RISK_MODERATE, "git remote can change repository configuration"
        return RISK_SAFE, "read-only git query"
    if sub == "config":
        if any(token in ("--get", "--get-all", "--list", "-l") for token in tokens):
            return RISK_SAFE, "read-only git configuration query"
        return RISK_MODERATE, "git config can change repository configuration"
    if sub == "tag":
        if any(token in ("-d", "--delete") for token in tokens):
            return RISK_DESTRUCTIVE, "git tag -d deletes tags"
        if any(token in ("-a", "-s", "-f") for token in tokens):
            return RISK_MODERATE, "git tag can create or move tags"
        if any(token in ("-l", "--list", "--contains", "--merged", "--no-merged",
                         "--points-at", "--sort") for token in tokens):
            return RISK_SAFE, "read-only git query"
        if any(not token.startswith("-") for token in tokens[2:]):
            return RISK_MODERATE, "git tag can create a tag"
        return RISK_SAFE, "read-only git query"
    if sub == "stash":
        action = _first_value(tokens, skip={"stash"})
        if action in ("list", "show"):
            return RISK_SAFE, "read-only git query"
        if action in ("clear", "drop"):
            return RISK_DESTRUCTIVE, "git stash can delete saved work"
        return RISK_MODERATE, "git stash can modify saved work"
    if sub == "worktree":
        action = _first_value(tokens, skip={"worktree"})
        if action == "list":
            return RISK_SAFE, "read-only git query"
        if action in ("remove", "prune"):
            return RISK_DESTRUCTIVE, "git worktree can delete a working tree"
        return RISK_MODERATE, "git worktree can modify worktrees"
    if sub in _GIT_MODERATE:
        return RISK_MODERATE, f"git {sub} can modify repository state"
    if not sub:
        if len(tokens) == 1 or all(
            token in ("--version", "--help", "-h", "--no-pager") for token in tokens[1:]
        ):
            return RISK_SAFE, "read-only git query"
        return RISK_MODERATE, "git command needs confirmation"
    return RISK_SAFE, "read-only git query"


def _systemctl_risk(tokens: tuple[str, ...]) -> tuple[str, str]:
    sub = _find_subcommand(tokens, _SYSTEMCTL_SAFE | _SYSTEMCTL_MODERATE | _SYSTEMCTL_DESTRUCTIVE)
    if sub in _SYSTEMCTL_DESTRUCTIVE:
        return RISK_DESTRUCTIVE, f"systemctl {sub} can stop or disrupt services"
    if sub in _SYSTEMCTL_MODERATE:
        return RISK_MODERATE, f"systemctl {sub} changes service state"
    if sub:
        return RISK_SAFE, "read-only service query"
    if len(tokens) == 1 or all(_safe_systemctl_option(token) for token in tokens[1:]):
        return RISK_SAFE, "read-only service query"
    return RISK_MODERATE, "systemctl command needs confirmation"


def _safe_systemctl_option(token: str) -> bool:
    if token in (
        "--failed", "--version", "--help", "-h", "--no-pager", "--no-legend",
        "--all", "--full", "--plain", "--quiet", "--user", "--system",
        "--global", "--runtime", "--value", "--recursive",
    ):
        return True
    return token.startswith(("--state=", "--type=", "--property=", "--job-mode="))


def _package_risk(tokens: tuple[str, ...]) -> tuple[str, str]:
    base = Path(tokens[0]).name
    sub = _find_subcommand(tokens, _PACKAGE_SAFE | _PACKAGE_MODERATE | _PACKAGE_DESTRUCTIVE)
    if sub == "audit" and base in ("npm", "yarn", "pnpm") and "fix" in tokens:
        return RISK_MODERATE, f"{base} audit fix changes dependencies"
    if base == "dnf" and sub in ("group", "module"):
        if any(token in ("remove", "erase", "uninstall") for token in tokens):
            return RISK_DESTRUCTIVE, f"dnf {sub} remove can remove packages"
        return RISK_MODERATE, f"dnf {sub} changes installed software"
    if sub in _PACKAGE_DESTRUCTIVE:
        return RISK_DESTRUCTIVE, f"{base} {sub} can remove or publish software"
    if sub in _PACKAGE_MODERATE:
        return RISK_MODERATE, f"{base} {sub} changes installed software"
    if sub in _PACKAGE_SAFE:
        return RISK_SAFE, f"read-only {base} query"
    # Package managers without a recognized subcommand are not safe.
    return RISK_MODERATE, f"{base} needs confirmation"


def _rpm_risk(tokens: tuple[str, ...]) -> tuple[str, str]:
    if any(token in ("-e", "--erase", "-i", "--install", "-U", "--upgrade", "-F", "--freshen") for token in tokens[1:]):
        return RISK_DESTRUCTIVE, "rpm can install or erase packages"
    if any(token in ("-q", "-qi", "-ql", "-qa", "-qf", "-qc", "-qd", "--verify") for token in tokens[1:]):
        return RISK_SAFE, "read-only package query"
    return RISK_MODERATE, "rpm needs confirmation"


def _firewall_risk(tokens: tuple[str, ...]) -> tuple[str, str]:
    values = tokens[1:]
    if any(
        value.startswith("--remove-")
        or value.startswith("--delete-")
        or value in ("--panic-on", "--set-target")
        for value in values
    ):
        return RISK_DESTRUCTIVE, "firewall changes can cut off network access"
    if any(
        value.startswith("--add-")
        or value.startswith("--set-")
        or value in ("--reload", "--complete-reload", "--runtime-to-permanent", "--panic-off")
        for value in values
    ):
        return RISK_MODERATE, "firewall changes can affect connectivity"
    if len(tokens) == 1 or all(
        value.startswith(("--list-", "--get-", "--query-"))
        or value in ("--state", "--version", "--help", "-h")
        for value in values
    ):
        return RISK_SAFE, "read-only firewall query"
    return RISK_MODERATE, "firewall-cmd needs confirmation"


def _nmcli_risk(tokens: tuple[str, ...]) -> tuple[str, str]:
    sub = _find_subcommand(tokens, {"show", "status", "list", "up", "down", "connect", "disconnect", "add", "modify", "reload", "delete", "remove"})
    if sub in ("delete", "remove"):
        return RISK_DESTRUCTIVE, "nmcli can delete network connections"
    if sub in ("up", "down", "connect", "disconnect", "add", "modify", "reload"):
        return RISK_MODERATE, "nmcli can change network state"
    if sub in ("show", "status", "list"):
        return RISK_SAFE, "read-only network query"
    if len(tokens) == 1 or all(
        token in ("--version", "--help", "-h") for token in tokens[1:]
    ):
        return RISK_SAFE, "read-only network query"
    return RISK_MODERATE, "nmcli command needs confirmation"


def _ip_risk(tokens: tuple[str, ...]) -> tuple[str, str]:
    values = tokens[1:]
    if "exec" in values:
        return RISK_DESTRUCTIVE, "ip netns exec runs a command"
    if any(value in ("del", "delete", "flush") for value in values):
        return RISK_DESTRUCTIVE, "ip can remove network configuration"
    if any(value in ("add", "set", "change", "replace") for value in values):
        return RISK_MODERATE, "ip can change network configuration"
    if "monitor" in values:
        return RISK_MODERATE, "ip monitor runs until interrupted"
    read_only = {
        "address", "addr", "a", "route", "r", "link", "l", "neigh", "n",
        "maddress", "m", "mroute", "mr", "rule", "ru", "tunnel", "t",
        "tuntap", "tap", "help", "show", "list", "get",
    }
    if len(tokens) == 1 or all(
        value.startswith("-") or value in read_only for value in values
    ):
        return RISK_SAFE, "read-only network query"
    return RISK_MODERATE, "ip command needs confirmation"


def _container_risk(tokens: tuple[str, ...]) -> tuple[str, str]:
    base = Path(tokens[0]).name
    sub = _find_subcommand(tokens, _CONTAINER_SAFE | _CONTAINER_MODERATE | _CONTAINER_DESTRUCTIVE)
    if sub in _CONTAINER_DESTRUCTIVE:
        return RISK_DESTRUCTIVE, f"{base} {sub} can run or delete containers"
    if sub in _CONTAINER_MODERATE:
        return RISK_MODERATE, f"{base} {sub} changes container state"
    if sub == "logs" and any(
        token in ("-f", "--follow") for token in tokens[1:]
    ):
        return RISK_MODERATE, f"{base} logs --follow runs until interrupted"
    if sub in _CONTAINER_SAFE:
        return RISK_SAFE, "read-only container query"
    if len(tokens) == 1 or all(
        token in ("--version", "--help", "-h") for token in tokens[1:]
    ):
        return RISK_SAFE, "read-only container query"
    return RISK_MODERATE, f"{base} command needs confirmation"


def _ollama_risk(tokens: tuple[str, ...]) -> tuple[str, str]:
    sub = _find_subcommand(tokens, _OLLAMA_SAFE | _OLLAMA_MODERATE | _OLLAMA_DESTRUCTIVE)
    if sub in _OLLAMA_DESTRUCTIVE:
        return RISK_DESTRUCTIVE, "ollama rm deletes a local model"
    if sub in _OLLAMA_MODERATE:
        return RISK_MODERATE, "ollama can download or start a model"
    if sub in _OLLAMA_SAFE:
        return RISK_SAFE, "read-only Ollama query"
    if len(tokens) == 1 or all(
        token in ("--version", "--help", "-h") for token in tokens[1:]
    ):
        return RISK_SAFE, "read-only Ollama query"
    return RISK_MODERATE, "ollama command needs confirmation"


def _find_subcommand(tokens: tuple[str, ...], known: set[str]) -> str:
    for token in tokens[1:]:
        if token in known:
            return token
    return ""


def _first_value(tokens: tuple[str, ...], skip: set[str]) -> str:
    for token in tokens[1:]:
        if token.startswith("-") or token in skip:
            continue
        return token
    return ""


def _fallback_command(text: str) -> tuple[str, str] | None:
    """Handle models that put a bare command on the first line.

    This is deliberately limited to the first non-empty line and to commands
    whose executable is in the known policy tables.  It prevents a normal
    explanation from being mistaken for a command.
    """
    lines = text.splitlines()
    for index, line in enumerate(lines):
        if not line.strip():
            continue
        if not _looks_like_command(line):
            return None
        command = _clean_command(line)
        if not command:
            return None
        cleaned = "\n".join(lines[:index] + lines[index + 1 :])
        return command, _tidy(cleaned)
    return None


def _looks_like_command(line: str) -> bool:
    value = line.strip()
    if value.startswith(("```", "#", "- ", "* ", "> ")):
        return False
    value = _clean_command(value)
    if not value or "\n" in value:
        return False
    if value.endswith((".", "?", "!")):
        return False
    try:
        tokens = shlex.split(value)
    except ValueError:
        return False
    if not tokens:
        return False
    if tokens[0].lower() in _PROSE_STARTS:
        return False
    base = Path(tokens[0]).name
    return base in _KNOWN_BASES or base.startswith("mkfs")


def _clean_command(value: str) -> str:
    value = value.strip()
    if len(value) >= 2 and value.startswith("`") and value.endswith("`"):
        value = value[1:-1].strip()
    if value.startswith("$ "):
        value = value[2:].strip()
    return value


def _tidy(text: str) -> str:
    return re.sub(r"\n{3,}", "\n\n", text).strip()


def _truncate(text: str, limit: int) -> tuple[str, bool]:
    if limit <= 0 or len(text) <= limit:
        return text, False
    return text[:limit].rstrip() + "\n… (truncated)", True

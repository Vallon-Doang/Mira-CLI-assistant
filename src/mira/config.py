"""Configuration loading, validation, and atomic updates."""

from __future__ import annotations

import os
import re
import tempfile
import tomllib
from dataclasses import dataclass, field
from pathlib import Path
from urllib.parse import urlparse

from .errors import ConfigError

DEFAULT_MODEL = "gemma4:e4b-it-q4_K_M"
DEFAULT_HOST = "http://127.0.0.1:11434"
MODES = ("oneshot", "explain", "converse")

DEFAULT_CONFIG_TEMPLATE = """\
# MIRA configuration. Created automatically on first run.
# Path: {path}

[model]
name = "gemma4:e4b-it-q4_K_M"
temperature = 0.2
num_predict = 256
num_ctx = 4096
keep_alive = "5m"
explain_temperature = 0.3
explain_num_predict = 768

[ollama]
host = "http://127.0.0.1:11434"
stream = true
timeout = 120

[behavior]
default_mode = "oneshot"
thinking = false
context_detection = true
cheatsheet = true
direct_answers = true

[conversation]
max_messages = 12

[retrieval]
max_results = 3

[execution]
enabled = false
timeout = 30
max_output = 20000
allow_destructive = false
"""


@dataclass
class ModelConfig:
    name: str = DEFAULT_MODEL
    temperature: float = 0.2
    num_predict: int = 256
    num_ctx: int = 4096
    keep_alive: str | int = "5m"
    explain_temperature: float = 0.3
    explain_num_predict: int = 768


@dataclass
class OllamaConfig:
    host: str = DEFAULT_HOST
    stream: bool = True
    timeout: float = 120.0


@dataclass
class BehaviorConfig:
    default_mode: str = "oneshot"
    thinking: bool = False
    context_detection: bool = True
    cheatsheet: bool = True
    direct_answers: bool = True


@dataclass
class ConversationConfig:
    max_messages: int = 12


@dataclass
class RetrievalConfig:
    max_results: int = 3


@dataclass
class ExecutionConfig:
    enabled: bool = False
    timeout: float = 30.0
    max_output: int = 20_000
    allow_destructive: bool = False


@dataclass
class Config:
    model: ModelConfig = field(default_factory=ModelConfig)
    ollama: OllamaConfig = field(default_factory=OllamaConfig)
    behavior: BehaviorConfig = field(default_factory=BehaviorConfig)
    conversation: ConversationConfig = field(default_factory=ConversationConfig)
    retrieval: RetrievalConfig = field(default_factory=RetrievalConfig)
    execution: ExecutionConfig = field(default_factory=ExecutionConfig)
    path: Path = field(default_factory=lambda: config_path())

    def render(self) -> str:
        """Render the effective configuration as TOML."""
        keep = self.model.keep_alive
        keep_text = f'"{keep}"' if isinstance(keep, str) else str(keep)
        return (
            "[model]\n"
            f'name = "{self.model.name}"\n'
            f"temperature = {self.model.temperature}\n"
            f"num_predict = {self.model.num_predict}\n"
            f"num_ctx = {self.model.num_ctx}\n"
            f"keep_alive = {keep_text}\n"
            f"explain_temperature = {self.model.explain_temperature}\n"
            f"explain_num_predict = {self.model.explain_num_predict}\n"
            "\n[ollama]\n"
            f'host = "{self.ollama.host}"\n'
            f"stream = {_toml_bool(self.ollama.stream)}\n"
            f"timeout = {_fmt_number(self.ollama.timeout)}\n"
            "\n[behavior]\n"
            f'default_mode = "{self.behavior.default_mode}"\n'
            f"thinking = {_toml_bool(self.behavior.thinking)}\n"
            f"context_detection = {_toml_bool(self.behavior.context_detection)}\n"
            f"cheatsheet = {_toml_bool(self.behavior.cheatsheet)}\n"
            f"direct_answers = {_toml_bool(self.behavior.direct_answers)}\n"
            "\n[conversation]\n"
            f"max_messages = {self.conversation.max_messages}\n"
            "\n[retrieval]\n"
            f"max_results = {self.retrieval.max_results}\n"
            "\n[execution]\n"
            f"enabled = {_toml_bool(self.execution.enabled)}\n"
            f"timeout = {_fmt_number(self.execution.timeout)}\n"
            f"max_output = {self.execution.max_output}\n"
            f"allow_destructive = {_toml_bool(self.execution.allow_destructive)}\n"
        )


def config_path() -> Path:
    """Return the configuration path, honouring MIRA_CONFIG and XDG."""
    override = os.environ.get("MIRA_CONFIG")
    if override:
        return Path(override).expanduser()
    xdg = os.environ.get("XDG_CONFIG_HOME")
    base = Path(xdg).expanduser() if xdg else Path.home() / ".config"
    return base / "mira" / "config.toml"


def load_config(path: Path | None = None, create: bool = True) -> Config:
    """Load and validate configuration, creating defaults when absent."""
    cfg_path = Path(path) if path is not None else config_path()
    if not cfg_path.exists():
        if not create:
            return Config(path=cfg_path)
        _atomic_write(cfg_path, DEFAULT_CONFIG_TEMPLATE.replace("{path}", str(cfg_path)))
        return Config(path=cfg_path)

    try:
        text = cfg_path.read_text(encoding="utf-8")
    except OSError as exc:
        raise ConfigError(f"Cannot read configuration file {cfg_path}: {exc}") from exc

    try:
        data = tomllib.loads(text)
    except tomllib.TOMLDecodeError as exc:
        raise ConfigError(
            f"Malformed configuration in {cfg_path}: {exc}",
            hint="Fix the TOML syntax or remove the file to regenerate defaults.",
        ) from exc

    try:
        cfg = Config(
            model=ModelConfig(
                name=_str(data, "model", "name", DEFAULT_MODEL),
                temperature=_float(data, "model", "temperature", 0.2),
                num_predict=_int(data, "model", "num_predict", 256),
                num_ctx=_int(data, "model", "num_ctx", 4096),
                keep_alive=_keep_alive(data),
                explain_temperature=_float(data, "model", "explain_temperature", 0.3),
                explain_num_predict=_int(data, "model", "explain_num_predict", 768),
            ),
            ollama=OllamaConfig(
                host=_str(data, "ollama", "host", DEFAULT_HOST),
                stream=_bool(data, "ollama", "stream", True),
                timeout=_float(data, "ollama", "timeout", 120.0),
            ),
            behavior=BehaviorConfig(
                default_mode=_str(data, "behavior", "default_mode", "oneshot"),
                thinking=_bool(data, "behavior", "thinking", False),
                context_detection=_bool(data, "behavior", "context_detection", True),
                cheatsheet=_bool(data, "behavior", "cheatsheet", True),
                direct_answers=_bool(data, "behavior", "direct_answers", True),
            ),
            conversation=ConversationConfig(
                max_messages=_int(data, "conversation", "max_messages", 12),
            ),
            retrieval=RetrievalConfig(
                max_results=_int(data, "retrieval", "max_results", 3),
            ),
            execution=ExecutionConfig(
                enabled=_bool(data, "execution", "enabled", False),
                timeout=_float(data, "execution", "timeout", 30.0),
                max_output=_int(data, "execution", "max_output", 20_000),
                allow_destructive=_bool(data, "execution", "allow_destructive", False),
            ),
            path=cfg_path,
        )
    except ConfigError:
        raise
    except (TypeError, ValueError) as exc:
        raise ConfigError(f"Invalid configuration in {cfg_path}: {exc}") from exc

    validate_config(cfg)
    return cfg


def validate_config(cfg: Config) -> None:
    """Validate a Config, raising ConfigError with a precise reason."""
    path = cfg.path
    if not isinstance(cfg.model.name, str) or not cfg.model.name.strip():
        raise ConfigError(f"Invalid configuration in {path}: model.name must be a non-empty string")
    if not 0.0 <= cfg.model.temperature <= 2.0:
        raise ConfigError(f"Invalid configuration in {path}: model.temperature must be between 0 and 2")
    if not 1 <= cfg.model.num_predict <= 32768:
        raise ConfigError(f"Invalid configuration in {path}: model.num_predict must be between 1 and 32768")
    if not 512 <= cfg.model.num_ctx <= 131072:
        raise ConfigError(f"Invalid configuration in {path}: model.num_ctx must be between 512 and 131072")
    if not 0.0 <= cfg.model.explain_temperature <= 2.0:
        raise ConfigError(
            f"Invalid configuration in {path}: model.explain_temperature must be between 0 and 2"
        )
    if not 1 <= cfg.model.explain_num_predict <= 32768:
        raise ConfigError(
            f"Invalid configuration in {path}: model.explain_num_predict must be between 1 and 32768"
        )
    if isinstance(cfg.model.keep_alive, str) and not cfg.model.keep_alive.strip():
        raise ConfigError(f"Invalid configuration in {path}: model.keep_alive must not be empty")
    if isinstance(cfg.model.keep_alive, (int, float)) and cfg.model.keep_alive < 0:
        raise ConfigError(f"Invalid configuration in {path}: model.keep_alive must not be negative")

    host = cfg.ollama.host.strip()
    parsed = urlparse(host)
    if parsed.scheme not in ("http", "https") or not parsed.netloc:
        raise ConfigError(
            f"Invalid configuration in {path}: ollama.host must be an http(s) URL, got {host!r}"
        )
    if not 0 < cfg.ollama.timeout <= 3600:
        raise ConfigError(f"Invalid configuration in {path}: ollama.timeout must be between 0 and 3600")
    if cfg.behavior.default_mode not in MODES:
        raise ConfigError(
            f"Invalid configuration in {path}: behavior.default_mode must be one of {', '.join(MODES)}"
        )
    if cfg.conversation.max_messages < 2:
        raise ConfigError(
            f"Invalid configuration in {path}: conversation.max_messages must be at least 2"
        )
    if not 1 <= cfg.retrieval.max_results <= 20:
        raise ConfigError(
            f"Invalid configuration in {path}: retrieval.max_results must be between 1 and 20"
        )
    if not 1 <= cfg.execution.timeout <= 600:
        raise ConfigError(
            f"Invalid configuration in {path}: execution.timeout must be between 1 and 600"
        )
    if not 1_000 <= cfg.execution.max_output <= 1_000_000:
        raise ConfigError(
            f"Invalid configuration in {path}: execution.max_output must be between 1000 and 1000000"
        )


def set_config_value(path: Path, section: str, key: str, value: object) -> None:
    """Update one key in the config file, preserving comments and layout."""
    path = Path(path)
    if path.exists():
        try:
            lines = path.read_text(encoding="utf-8").splitlines()
        except OSError as exc:
            raise ConfigError(f"Cannot read configuration file {path}: {exc}") from exc
    else:
        lines = DEFAULT_CONFIG_TEMPLATE.replace("{path}", str(path)).splitlines()

    literal = _toml_literal(value)
    section_re = re.compile(r"^\s*\[([^\]]+)\]\s*$")
    key_re = re.compile(rf"^\s*{re.escape(key)}\s*=")

    section_start = None
    section_end = len(lines)
    for index, line in enumerate(lines):
        match = section_re.match(line)
        if not match:
            continue
        if section_start is not None:
            section_end = index
            break
        if match.group(1).strip() == section:
            section_start = index

    if section_start is None:
        if lines and lines[-1].strip():
            lines.append("")
        lines.extend([f"[{section}]", f"{key} = {literal}"])
    else:
        replaced = False
        for index in range(section_start + 1, section_end):
            if key_re.match(lines[index]):
                lines[index] = f"{key} = {literal}"
                replaced = True
                break
        if not replaced:
            insert_at = section_end
            while insert_at > section_start + 1 and not lines[insert_at - 1].strip():
                insert_at -= 1
            lines.insert(insert_at, f"{key} = {literal}")

    _atomic_write(path, "\n".join(lines).rstrip("\n") + "\n")


def _atomic_write(path: Path, text: str) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    fd, tmp_name = tempfile.mkstemp(dir=path.parent, prefix=f".{path.name}.", suffix=".tmp")
    try:
        with os.fdopen(fd, "w", encoding="utf-8") as handle:
            handle.write(text)
            handle.flush()
            os.fsync(handle.fileno())
        os.replace(tmp_name, path)
    except BaseException:
        try:
            os.unlink(tmp_name)
        except OSError:
            pass
        raise


def _section(data: dict, name: str) -> dict:
    value = data.get(name, {})
    if not isinstance(value, dict):
        raise ConfigError(f"Invalid configuration: [{name}] must be a table")
    return value


def _str(data: dict, section: str, key: str, default: str) -> str:
    value = _section(data, section).get(key, default)
    if not isinstance(value, str):
        raise ConfigError(f"Invalid configuration: {section}.{key} must be a string")
    return value


def _bool(data: dict, section: str, key: str, default: bool) -> bool:
    value = _section(data, section).get(key, default)
    if not isinstance(value, bool):
        raise ConfigError(f"Invalid configuration: {section}.{key} must be true or false")
    return value


def _int(data: dict, section: str, key: str, default: int) -> int:
    value = _section(data, section).get(key, default)
    if isinstance(value, bool) or not isinstance(value, int):
        raise ConfigError(f"Invalid configuration: {section}.{key} must be an integer")
    return value


def _float(data: dict, section: str, key: str, default: float) -> float:
    value = _section(data, section).get(key, default)
    if isinstance(value, bool) or not isinstance(value, (int, float)):
        raise ConfigError(f"Invalid configuration: {section}.{key} must be a number")
    return float(value)


def _keep_alive(data: dict) -> str | int:
    value = _section(data, "model").get("keep_alive", "5m")
    if isinstance(value, bool) or not isinstance(value, (str, int)):
        raise ConfigError("Invalid configuration: model.keep_alive must be a string or integer")
    return value


def _toml_bool(value: bool) -> str:
    return "true" if value else "false"


def _fmt_number(value: float) -> str:
    return str(int(value)) if float(value).is_integer() else str(value)


def _toml_literal(value: object) -> str:
    if isinstance(value, bool):
        return _toml_bool(value)
    if isinstance(value, (int, float)):
        return _fmt_number(float(value)) if isinstance(value, float) else str(value)
    if isinstance(value, str):
        escaped = value.replace("\\", "\\\\").replace('"', '\\"')
        return f'"{escaped}"'
    raise ConfigError(f"Cannot serialize configuration value of type {type(value).__name__}")

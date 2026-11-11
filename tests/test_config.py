from __future__ import annotations

from pathlib import Path

import pytest

from mira.config import (
    Config,
    config_path,
    load_config,
    set_config_value,
    validate_config,
)
from mira.errors import ConfigError


def test_defaults_are_created(tmp_path: Path) -> None:
    path = tmp_path / "config.toml"
    cfg = load_config(path)
    assert path.exists()
    assert cfg.model.name == "gemma4:e4b-it-q4_K_M"
    assert cfg.ollama.host == "http://127.0.0.1:11434"
    assert cfg.behavior.direct_answers is True
    assert cfg.conversation.max_messages == 12
    assert cfg.execution.enabled is False
    assert cfg.execution.timeout == 30.0
    assert cfg.execution.max_output == 20_000
    assert cfg.execution.confirm_safe is False
    assert cfg.path == path


def test_malformed_toml(tmp_path: Path) -> None:
    path = tmp_path / "config.toml"
    path.write_text("[model\nname = 'x'", encoding="utf-8")
    with pytest.raises(ConfigError, match="Malformed configuration"):
        load_config(path)


def test_invalid_temperature(tmp_path: Path) -> None:
    path = tmp_path / "config.toml"
    path.write_text("[model]\ntemperature = 5.0\n", encoding="utf-8")
    with pytest.raises(ConfigError, match="temperature"):
        load_config(path)


def test_invalid_host(tmp_path: Path) -> None:
    path = tmp_path / "config.toml"
    path.write_text('[ollama]\nhost = "ftp://example.com"\n', encoding="utf-8")
    with pytest.raises(ConfigError, match="ollama.host"):
        load_config(path)


def test_invalid_mode(tmp_path: Path) -> None:
    path = tmp_path / "config.toml"
    path.write_text('[behavior]\ndefault_mode = "chat"\n', encoding="utf-8")
    with pytest.raises(ConfigError, match="default_mode"):
        load_config(path)


def test_invalid_max_messages(tmp_path: Path) -> None:
    path = tmp_path / "config.toml"
    path.write_text("[conversation]\nmax_messages = 1\n", encoding="utf-8")
    with pytest.raises(ConfigError, match="max_messages"):
        load_config(path)


def test_execution_settings_load_and_render(tmp_path: Path) -> None:
    path = tmp_path / "config.toml"
    path.write_text(
        "[execution]\nenabled = true\ntimeout = 45\nmax_output = 5000\n"
        "allow_destructive = true\nconfirm_safe = true\n",
        encoding="utf-8",
    )
    cfg = load_config(path)
    assert cfg.execution.enabled is True
    assert cfg.execution.timeout == 45.0
    assert cfg.execution.max_output == 5000
    assert cfg.execution.allow_destructive is True
    assert cfg.execution.confirm_safe is True
    rendered = cfg.render()
    assert "[execution]" in rendered
    assert "timeout = 45" in rendered
    assert "confirm_safe = true" in rendered


def test_invalid_execution_timeout(tmp_path: Path) -> None:
    path = tmp_path / "config.toml"
    path.write_text("[execution]\ntimeout = 0\n", encoding="utf-8")
    with pytest.raises(ConfigError, match="execution.timeout"):
        load_config(path)


def test_invalid_execution_max_output(tmp_path: Path) -> None:
    path = tmp_path / "config.toml"
    path.write_text("[execution]\nmax_output = 10\n", encoding="utf-8")
    with pytest.raises(ConfigError, match="execution.max_output"):
        load_config(path)


def test_set_model_preserves_comments(tmp_path: Path) -> None:
    path = tmp_path / "config.toml"
    path.write_text(
        "# keep this comment\n[model]\nname = \"old-model\"\ntemperature = 0.1\n",
        encoding="utf-8",
    )
    set_config_value(path, "model", "name", "new-model")
    text = path.read_text(encoding="utf-8")
    assert "# keep this comment" in text
    assert 'name = "new-model"' in text
    assert "temperature = 0.1" in text
    assert load_config(path).model.name == "new-model"


def test_set_config_value_adds_missing_key(tmp_path: Path) -> None:
    path = tmp_path / "config.toml"
    path.write_text("[model]\nname = \"x\"\n", encoding="utf-8")
    set_config_value(path, "model", "num_predict", 128)
    assert "num_predict = 128" in path.read_text(encoding="utf-8")


def test_config_path_env(monkeypatch: pytest.MonkeyPatch, tmp_path: Path) -> None:
    target = tmp_path / "custom.toml"
    monkeypatch.setenv("MIRA_CONFIG", str(target))
    assert config_path() == target


def test_config_path_xdg(monkeypatch: pytest.MonkeyPatch, tmp_path: Path) -> None:
    monkeypatch.delenv("MIRA_CONFIG", raising=False)
    monkeypatch.setenv("XDG_CONFIG_HOME", str(tmp_path))
    assert config_path() == tmp_path / "mira" / "config.toml"


def test_validate_accepts_defaults() -> None:
    validate_config(Config())

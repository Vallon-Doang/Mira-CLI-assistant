from __future__ import annotations

import io
import json
from pathlib import Path

import pytest

from mira.cli import build_parser, main


class TtyStringIO(io.StringIO):
    def isatty(self) -> bool:  # noqa: D102
        return True


def test_parser_joins_multiword_query() -> None:
    args = build_parser().parse_args(["how", "do", "i", "check", "ip"])
    assert args.query == ["how", "do", "i", "check", "ip"]


def test_single_dash_modes() -> None:
    assert build_parser().parse_args(["-explain", "q"]).explain is True
    assert build_parser().parse_args(["-converse"]).converse is True


def test_version(capsys) -> None:
    assert main(["--version"]) == 0
    assert "mira 0.1.0" in capsys.readouterr().out


def test_no_question_on_tty(mira_config, monkeypatch, capsys) -> None:
    monkeypatch.setattr("sys.stdin", TtyStringIO(""))
    assert main([]) == 2
    assert "No question provided" in capsys.readouterr().err


def test_fast_path(mira_config, capsys) -> None:
    code = main(["Where is Apache's configuration file on Fedora?"])
    captured = capsys.readouterr()
    assert code == 0
    assert "/etc/httpd/conf/httpd.conf" in captured.out
    assert "(local cheatsheet)" in captured.out
    assert captured.err == ""


def test_fast_path_json(mira_config, capsys) -> None:
    code = main(["--json", "How do I check available disk space?"])
    payload = json.loads(capsys.readouterr().out)
    assert code == 0
    assert payload["source"] == "cheatsheet"
    assert payload["answer"].startswith("```bash\ndf -h")
    assert payload["retrieval"][0]["topic"] == "Check available disk space"
    assert payload["context"]["os"] == "Fedora Linux"


def test_llm_path(mira_config, fake_ollama, capsys) -> None:
    fake_ollama.chat_text = "Use the fake command."
    code = main(["--no-cheatsheet", "hello"])
    captured = capsys.readouterr()
    assert code == 0
    assert "Use the fake command." in captured.out
    assert fake_ollama.last_chat_payload["think"] is False
    assert fake_ollama.last_chat_payload["stream"] is True


def test_llm_json(mira_config, fake_ollama, capsys) -> None:
    fake_ollama.chat_text = "Structured answer."
    code = main(["--json", "--no-cheatsheet", "hello"])
    payload = json.loads(capsys.readouterr().out)
    assert code == 0
    assert payload["source"] == "llm"
    assert payload["answer"] == "Structured answer."
    assert payload["usage"]["prompt_tokens"] == 12
    assert payload["usage"]["completion_tokens"] == 5
    assert payload["timing"]["ttft_ms"] is None


def test_debug_goes_to_stderr_with_json(mira_config, capsys) -> None:
    code = main(["--json", "--debug", "--no-cheatsheet", "hello"])
    captured = capsys.readouterr()
    assert code == 0
    assert "MIRA debug:" in captured.err
    json.loads(captured.out)


def test_explain_uses_longer_limit(mira_config, fake_ollama, capsys) -> None:
    code = main(["--explain", "--no-cheatsheet", "explain something"])
    assert code == 0
    assert fake_ollama.last_chat_payload["options"]["num_predict"] == 768
    assert fake_ollama.last_chat_payload["options"]["temperature"] == 0.3


def test_list_models(mira_config, capsys) -> None:
    code = main(["--list-models"])
    out = capsys.readouterr().out
    assert code == 0
    assert "test-model:latest" in out
    assert "*" in out


def test_list_models_json(mira_config, capsys) -> None:
    code = main(["--list-models", "--json"])
    payload = json.loads(capsys.readouterr().out)
    assert code == 0
    assert payload["default"] == "test-model:latest"
    assert payload["models"][0]["name"] == "test-model:latest"


def test_set_model(mira_config, capsys) -> None:
    code = main(["--set-model", "test-model:latest"])
    assert code == 0
    assert "Default model set" in capsys.readouterr().out
    assert 'name = "test-model:latest"' in mira_config.read_text(encoding="utf-8")


def test_set_missing_model(mira_config, capsys) -> None:
    code = main(["--set-model", "missing:latest"])
    assert code == 4
    assert "not installed" in capsys.readouterr().err


def test_show_config_json(mira_config, capsys) -> None:
    code = main(["--show-config", "--json"])
    payload = json.loads(capsys.readouterr().out)
    assert code == 0
    assert payload["config"]["model"]["name"] == "test-model:latest"
    assert payload["path"] == str(mira_config)


def test_no_context_json(mira_config, capsys) -> None:
    code = main(["--json", "--no-context", "--no-cheatsheet", "hello"])
    payload = json.loads(capsys.readouterr().out)
    assert code == 0
    assert payload["context"] is None


def test_no_cheatsheet_has_no_retrieval(mira_config, capsys) -> None:
    code = main(["--json", "--no-cheatsheet", "how do I restart apache"])
    payload = json.loads(capsys.readouterr().out)
    assert code == 0
    assert payload["retrieval"] == []


def test_non_streaming_text_output(tmp_path: Path, monkeypatch, fake_ollama, capsys) -> None:
    path = tmp_path / "config.toml"
    path.write_text(
        '[model]\nname = "test-model:latest"\n\n[ollama]\n'
        f'host = "{fake_ollama.host}"\nstream = false\ntimeout = 10\n',
        encoding="utf-8",
    )
    monkeypatch.setenv("MIRA_CONFIG", str(path))
    fake_ollama.chat_text = "buffered answer"
    assert main(["--no-cheatsheet", "hello"]) == 0
    assert capsys.readouterr().out.strip() == "buffered answer"


def test_default_converse_mode_rejects_json(tmp_path: Path, monkeypatch, fake_ollama, capsys) -> None:
    path = tmp_path / "config.toml"
    path.write_text(
        '[model]\nname = "test-model:latest"\n\n[ollama]\n'
        f'host = "{fake_ollama.host}"\n\n[behavior]\ndefault_mode = "converse"\n',
        encoding="utf-8",
    )
    monkeypatch.setenv("MIRA_CONFIG", str(path))
    assert main(["--json", "hello"]) == 2
    payload = json.loads(capsys.readouterr().out)
    assert "conversation mode" in payload["error"]["message"]


def test_argparse_error_with_json(capsys) -> None:
    assert main(["--json", "--not-a-flag"]) == 2
    payload = json.loads(capsys.readouterr().out)
    assert payload["error"]["code"] == 2


def test_model_override_missing(mira_config, capsys) -> None:
    code = main(["--no-cheatsheet", "--model", "missing:latest", "hello"])
    assert code == 4
    assert "not installed" in capsys.readouterr().err


def test_unreachable_ollama(tmp_path: Path, monkeypatch, capsys) -> None:
    path = tmp_path / "config.toml"
    path.write_text(
        '[model]\nname = "test-model:latest"\n\n[ollama]\n'
        'host = "http://127.0.0.1:1"\ntimeout = 0.5\n',
        encoding="utf-8",
    )
    monkeypatch.setenv("MIRA_CONFIG", str(path))
    code = main(["--no-cheatsheet", "hello"])
    assert code == 3
    assert "not responding" in capsys.readouterr().err


def test_malformed_config_json_error(tmp_path: Path, monkeypatch, capsys) -> None:
    path = tmp_path / "config.toml"
    path.write_text("[model\n", encoding="utf-8")
    monkeypatch.setenv("MIRA_CONFIG", str(path))
    code = main(["--json", "hello"])
    payload = json.loads(capsys.readouterr().out)
    assert code == 2
    assert payload["error"]["code"] == 2
    assert "Malformed" in payload["error"]["message"]


def test_json_converse_is_rejected(mira_config, capsys) -> None:
    assert main(["--json", "--converse"]) == 2
    payload = json.loads(capsys.readouterr().out)
    assert "cannot be combined" in payload["error"]["message"]


def test_management_with_question_is_rejected(mira_config, capsys) -> None:
    assert main(["--show-config", "hello"]) == 2
    assert "do not take a question" in capsys.readouterr().err


def test_query_from_stdin(mira_config, fake_ollama, monkeypatch, capsys) -> None:
    fake_ollama.chat_text = "stdin answer"
    monkeypatch.setattr("sys.stdin", io.StringIO("hello from stdin\n"))
    assert main([]) == 0
    assert "stdin answer" in capsys.readouterr().out

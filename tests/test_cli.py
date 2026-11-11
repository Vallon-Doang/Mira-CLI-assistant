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
    assert "mira 0.2.1" in capsys.readouterr().out


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
    assert payload["config"]["execution"]["enabled"] is False
    assert payload["config"]["execution"]["timeout"] == 30.0
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


def test_converse_does_not_use_fast_path(mira_config, fake_ollama, monkeypatch, capsys) -> None:
    fake_ollama.chat_text = "model answer in conversation"
    monkeypatch.setattr("sys.stdin", io.StringIO("/exit\n"))
    code = main(["-converse", "How do I check available disk space?"])
    captured = capsys.readouterr()
    assert code == 0
    assert "model answer in conversation" in captured.out
    assert "(local cheatsheet)" not in captured.out
    assert fake_ollama.last_chat_payload is not None


def test_execute_safe_command_auto_runs(mira_config, fake_ollama, capsys) -> None:
    fake_ollama.chat_text = "Here is the check.\nCOMMAND: printf hello"
    code = main(["--execute", "--no-cheatsheet", "check something"])
    captured = capsys.readouterr()
    assert code == 0
    assert "Here is the check." in captured.out
    assert "Command: printf hello" in captured.out
    assert "hello" in captured.out
    assert "Exit code: 0" in captured.out
    assert fake_ollama.last_chat_payload["stream"] is False


def test_execute_moderate_with_yes(mira_config, fake_ollama, tmp_path: Path, capsys) -> None:
    target = tmp_path / "created-by-mira"
    fake_ollama.chat_text = f"COMMAND: touch {target}"
    code = main(["--execute", "--yes", "--no-cheatsheet", "create it"])
    captured = capsys.readouterr()
    assert code == 0
    assert target.exists()
    assert "Risk: moderate" in captured.out


def test_execute_moderate_without_yes_needs_confirmation(mira_config, fake_ollama, capsys) -> None:
    fake_ollama.chat_text = "COMMAND: touch /tmp/mira-should-not-exist"
    code = main(["--execute", "--no-cheatsheet", "create it"])
    captured = capsys.readouterr()
    assert code == 1
    assert "Not executed" in captured.out
    assert "confirmation" in captured.out


def test_execute_destructive_is_blocked(mira_config, fake_ollama, tmp_path: Path, capsys) -> None:
    target = tmp_path / "missing"
    fake_ollama.chat_text = f"COMMAND: rm -rf {target}"
    code = main(["--execute", "--yes", "--no-cheatsheet", "remove it"])
    captured = capsys.readouterr()
    assert code == 1
    assert "Destructive command blocked" in captured.out
    assert target.exists() is False


def test_execute_destructive_with_allow_and_yes(mira_config, fake_ollama, tmp_path: Path, capsys) -> None:
    target = tmp_path / "missing"
    fake_ollama.chat_text = f"COMMAND: rm -rf {target}"
    code = main(
        ["--execute", "--yes", "--allow-destructive", "--no-cheatsheet", "remove it"]
    )
    captured = capsys.readouterr()
    assert code == 0
    assert "Risk: destructive" in captured.out
    assert "Exit code: 0" in captured.out


def test_execute_shell_pipeline_with_yes(mira_config, fake_ollama, capsys) -> None:
    fake_ollama.chat_text = "COMMAND: printf 'a\\nb\\n' | wc -l"
    code = main(["--execute", "--yes", "--no-cheatsheet", "count lines"])
    captured = capsys.readouterr()
    assert code == 0
    assert "Shell features: pipe" in captured.out
    assert "2" in captured.out


def test_execute_json_safe_command(mira_config, fake_ollama, capsys) -> None:
    fake_ollama.chat_text = "COMMAND: printf hello"
    code = main(["--json", "--execute", "--no-cheatsheet", "run it"])
    payload = json.loads(capsys.readouterr().out)
    assert code == 0
    assert payload["answer"] is None
    assert payload["execution"]["status"] == "executed"
    assert payload["execution"]["executed"] is True
    assert payload["execution"]["stdout"] == "hello"
    assert payload["execution"]["exit_code"] == 0


def test_execute_json_moderate_requires_confirmation(mira_config, fake_ollama, capsys) -> None:
    fake_ollama.chat_text = "COMMAND: touch /tmp/mira-json-should-not-exist"
    code = main(["--json", "--execute", "--no-cheatsheet", "create it"])
    payload = json.loads(capsys.readouterr().out)
    assert code == 1
    assert payload["execution"]["status"] == "confirmation_required"
    assert payload["error"]["code"] == 1


def test_execute_json_multiple_commands_rejected(mira_config, fake_ollama, capsys) -> None:
    fake_ollama.chat_text = "COMMAND: ls\nCOMMAND: df -h"
    code = main(["--json", "--execute", "--no-cheatsheet", "do things"])
    payload = json.loads(capsys.readouterr().out)
    assert code == 1
    assert payload["execution"]["status"] == "ambiguous"
    assert "multiple" in payload["error"]["message"]


def test_execute_no_command_just_answers(mira_config, fake_ollama, capsys) -> None:
    fake_ollama.chat_text = "No command is needed."
    code = main(["--execute", "--no-cheatsheet", "explain"])
    captured = capsys.readouterr()
    assert code == 0
    assert "No command is needed." in captured.out
    assert "Command:" not in captured.out


def test_execute_fast_path_is_not_executed(mira_config, capsys) -> None:
    code = main(["--execute", "How do I check available disk space?"])
    captured = capsys.readouterr()
    assert code == 0
    assert "(local cheatsheet)" in captured.out
    assert "Exit code:" not in captured.out


def test_execute_bare_first_line_command(mira_config, fake_ollama, capsys) -> None:
    fake_ollama.chat_text = "printf hello\nThis prints hello."
    code = main(["--execute", "--no-cheatsheet", "print hello"])
    captured = capsys.readouterr()
    assert code == 0
    assert "Command: printf hello" in captured.out
    assert "This prints hello." in captured.out
    assert "hello" in captured.out


def test_execute_moderate_interactive_accept(mira_config, fake_ollama, tmp_path: Path, monkeypatch, capsys) -> None:
    target = tmp_path / "confirmed"
    fake_ollama.chat_text = f"COMMAND: touch {target}"
    monkeypatch.setattr("mira.output.Console.is_interactive", lambda self: True)
    monkeypatch.setattr("builtins.input", lambda prompt: "y")
    code = main(["--execute", "--no-cheatsheet", "create it"])
    assert code == 0
    assert target.exists()
    assert "Risk: moderate" in capsys.readouterr().out


def test_execute_moderate_interactive_decline(mira_config, fake_ollama, tmp_path: Path, monkeypatch, capsys) -> None:
    target = tmp_path / "declined"
    fake_ollama.chat_text = f"COMMAND: touch {target}"
    monkeypatch.setattr("mira.output.Console.is_interactive", lambda self: True)
    monkeypatch.setattr("builtins.input", lambda prompt: "n")
    code = main(["--execute", "--no-cheatsheet", "create it"])
    assert code == 0
    assert not target.exists()
    assert "Not executed" in capsys.readouterr().out


def test_execute_from_config(mira_config, fake_ollama, capsys) -> None:
    text = mira_config.read_text(encoding="utf-8")
    mira_config.write_text(text + "\n[execution]\nenabled = true\n", encoding="utf-8")
    fake_ollama.chat_text = "COMMAND: printf configured"
    code = main(["--no-cheatsheet", "run configured"])
    captured = capsys.readouterr()
    assert code == 0
    assert "configured" in captured.out
    assert "Command: printf configured" in captured.out


def test_yes_without_execute_is_rejected(mira_config, capsys) -> None:
    assert main(["--yes", "--no-cheatsheet", "hello"]) == 2
    assert "--execute" in capsys.readouterr().err


def test_doctor_ok(mira_config, capsys) -> None:
    code = main(["--doctor"])
    out = capsys.readouterr().out
    assert code == 0
    assert "[OK] Ollama API" in out
    assert "[OK] Model" in out
    assert "[OK] Knowledge" in out


def test_doctor_json(mira_config, capsys) -> None:
    code = main(["--doctor", "--json"])
    payload = json.loads(capsys.readouterr().out)
    assert code == 0
    assert payload["ok"] is True
    names = {item["name"] for item in payload["checks"]}
    assert {"Python", "Ollama API", "Model", "Knowledge"} <= names


def test_doctor_missing_model(mira_config, fake_ollama, capsys) -> None:
    fake_ollama.models = []
    code = main(["--doctor"])
    out = capsys.readouterr().out
    assert code == 1
    assert "[FAIL] Model" in out


def test_doctor_unreachable_ollama(tmp_path: Path, monkeypatch, capsys) -> None:
    path = tmp_path / "config.toml"
    path.write_text(
        '[model]\nname = "test-model:latest"\n\n[ollama]\n'
        'host = "http://127.0.0.1:1"\ntimeout = 0.5\n',
        encoding="utf-8",
    )
    monkeypatch.setenv("MIRA_CONFIG", str(path))
    code = main(["--doctor"])
    out = capsys.readouterr().out
    assert code == 1
    assert "[FAIL] Ollama API" in out

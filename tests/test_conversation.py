from __future__ import annotations

import io
import sys

from mira.conversation import Conversation, run_repl


def test_history_limit_and_user_start() -> None:
    conversation = Conversation(max_messages=4)
    for index in range(3):
        conversation.add_user(f"q{index}")
        conversation.add_assistant(f"a{index}")
    history = conversation.history()
    assert len(history) == 4
    assert history[0] == {"role": "user", "content": "q1"}
    assert history[-1] == {"role": "assistant", "content": "a2"}


def test_history_drops_orphan_assistant() -> None:
    conversation = Conversation(max_messages=3)
    conversation.add_user("q0")
    conversation.add_assistant("a0")
    conversation.add_user("q1")
    conversation.add_assistant("a1")
    history = conversation.history()
    assert history[0]["role"] == "user"


def test_clear_and_previous_user() -> None:
    conversation = Conversation()
    conversation.add_user("first")
    conversation.add_assistant("answer")
    conversation.add_user("second")
    assert conversation.previous_user() == "second"
    assert conversation.turns == 2
    conversation.clear()
    assert conversation.history() == []
    assert conversation.previous_user() is None


def test_repl_commands(monkeypatch, capsys) -> None:
    conversation = Conversation()
    conversation.add_user("old")
    conversation.add_assistant("old answer")
    asked: list[str] = []

    monkeypatch.setattr(sys, "stdin", io.StringIO("/help\n/clear\nhello\n/exit\n"))
    code = run_repl(asked.append, conversation=conversation)

    captured = capsys.readouterr()
    assert code == 0
    assert asked == ["hello"]
    assert "Commands:" in captured.out
    assert "History cleared." in captured.out
    assert conversation.history() == []


def test_repl_unknown_command(monkeypatch, capsys) -> None:
    monkeypatch.setattr(sys, "stdin", io.StringIO("/nope\n/exit\n"))
    assert run_repl(lambda question: None) == 0
    assert "Unknown command" in capsys.readouterr().out


def test_repl_eof(monkeypatch) -> None:
    monkeypatch.setattr(sys, "stdin", io.StringIO(""))
    assert run_repl(lambda question: None) == 0


def test_repl_initial_question(monkeypatch) -> None:
    monkeypatch.setattr(sys, "stdin", io.StringIO("/exit\n"))
    asked: list[str] = []
    run_repl(asked.append, initial="first question")
    assert asked == ["first question"]

"""Bounded conversation history and the interactive REPL."""

from __future__ import annotations

import sys
from dataclasses import dataclass, field
from typing import Callable

HELP_TEXT = """\
Commands:
  /help   Show this help
  /clear  Clear conversation history
  /exit   Exit MIRA
  /quit   Exit MIRA
"""


@dataclass
class Conversation:
    max_messages: int = 12
    messages: list[dict[str, str]] = field(default_factory=list)

    def add_user(self, content: str) -> None:
        self.messages.append({"role": "user", "content": content})

    def add_assistant(self, content: str) -> None:
        self.messages.append({"role": "assistant", "content": content})

    def clear(self) -> None:
        self.messages.clear()

    def history(self) -> list[dict[str, str]]:
        """Return at most max_messages entries, starting with a user turn."""
        if self.max_messages <= 0:
            return []
        trimmed = self.messages[-self.max_messages :] if len(self.messages) > self.max_messages else list(self.messages)
        while trimmed and trimmed[0].get("role") != "user":
            trimmed.pop(0)
        return trimmed

    def previous_user(self) -> str | None:
        for message in reversed(self.messages):
            if message.get("role") == "user":
                return message.get("content")
        return None

    @property
    def turns(self) -> int:
        return sum(1 for message in self.messages if message.get("role") == "user")


def run_repl(
    respond: Callable[[str], None],
    initial: str | None = None,
    conversation: Conversation | None = None,
) -> int:
    """Run an interactive session. ``respond`` handles one question."""
    if initial:
        respond(initial)

    interactive = sys.stdin.isatty()
    while True:
        try:
            line = input("mira> " if interactive else "")
        except EOFError:
            if interactive:
                print()
            return 0
        except KeyboardInterrupt:
            print()
            continue

        question = line.strip()
        if not question:
            continue
        command = question.casefold()
        if command in ("/exit", "/quit", "exit", "quit"):
            return 0
        if command == "/clear":
            if conversation is not None:
                conversation.clear()
            print("History cleared.")
            continue
        if command == "/help":
            print(HELP_TEXT, end="")
            continue
        if question.startswith("/"):
            print("Unknown command. Type /help for available commands.")
            continue

        try:
            respond(question)
        except KeyboardInterrupt:
            print()
            continue

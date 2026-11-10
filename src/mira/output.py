"""Terminal output: streaming, ANSI rules, JSON, and debug logging."""

from __future__ import annotations

import json
import os
import sys
import time
from dataclasses import dataclass
from typing import Iterable, TextIO

from .execution import RISK_DESTRUCTIVE, RISK_MODERATE, STATUS_NO_COMMAND, ExecutionResult
from .ollama_client import ChatChunk

_RESET = "\033[0m"
_DIM = "\033[2m"
_BOLD = "\033[1m"
_RED = "\033[31m"
_YELLOW = "\033[33m"
_GREEN = "\033[32m"


@dataclass
class StreamResult:
    text: str = ""
    ttft_ms: float | None = None
    total_ms: float = 0.0
    prompt_tokens: int | None = None
    completion_tokens: int | None = None
    eval_duration_ns: int | None = None
    interrupted: bool = False
    thinking_chars: int = 0


class Console:
    def __init__(
        self,
        debug: bool = False,
        json_mode: bool = False,
        stdout: TextIO | None = None,
        stderr: TextIO | None = None,
    ) -> None:
        self.debug_enabled = debug
        self.json_mode = json_mode
        self.out = stdout or sys.stdout
        self.err = stderr or sys.stderr
        self._out_color = _supports_color(self.out)
        self._err_color = _supports_color(self.err)

    # -- basic output -----------------------------------------------------

    def write(self, text: str) -> None:
        self.out.write(text)
        self.out.flush()

    def line(self, text: str = "") -> None:
        self.write(text + "\n")

    def debug(self, message: str) -> None:
        if not self.debug_enabled:
            return
        prefix = "MIRA debug:"
        if self._err_color:
            prefix = f"{_DIM}{prefix}{_RESET}"
        for index, line in enumerate(str(message).splitlines() or [""]):
            label = prefix if index == 0 else " " * len("MIRA debug:")
            self.err.write(f"{label} {line}\n")
        self.err.flush()

    def error(self, message: str) -> None:
        prefix = "MIRA:"
        if self._err_color:
            prefix = f"{_BOLD}{_RED}{prefix}{_RESET}"
        lines = message.splitlines()
        if lines and lines[0].startswith("MIRA: "):
            lines[0] = lines[0][len("MIRA: ") :]
        for index, line in enumerate(lines):
            label = prefix if index == 0 else ""
            self.err.write(f"{label} {line}\n" if label else f"{line}\n")
        self.err.flush()

    def print_cheatsheet(self, body: str) -> None:
        self.write(body.rstrip() + "\n\n")
        label = "(local cheatsheet)"
        self.line(f"{_DIM}{label}{_RESET}" if self._out_color else label)

    def emit_json(self, payload: dict) -> None:
        self.write(json.dumps(payload, indent=2, ensure_ascii=False) + "\n")

    def is_interactive(self) -> bool:
        return _is_tty(self.out)

    def confirm(self, prompt: str) -> bool:
        """Ask for confirmation.  Non-interactive input is always a no."""
        if not self.is_interactive():
            return False
        try:
            answer = input(prompt)
        except (EOFError, KeyboardInterrupt):
            self.line()
            return False
        return answer.strip().lower() in ("y", "yes")

    def print_execution(self, result: ExecutionResult) -> None:
        if result.status == STATUS_NO_COMMAND:
            return
        if result.command is None:
            if result.message:
                self.line(result.message)
            return

        risk = result.risk or "unknown"
        if risk == RISK_DESTRUCTIVE:
            label = _paint(f"Risk: {risk}", _RED, self._out_color)
        elif risk == RISK_MODERATE:
            label = _paint(f"Risk: {risk}", _YELLOW, self._out_color)
        else:
            label = _paint(f"Risk: {risk}", _GREEN, self._out_color)
        reason = f" — {result.reason}" if result.reason else ""
        self.line(f"Command: {result.command}")
        self.line(label + reason)
        if result.shell_features:
            features = ", ".join(result.shell_features)
            self.line(_paint(f"Shell features: {features}", _YELLOW, self._out_color))

        if not result.executed:
            message = result.message or "not executed"
            self.line(f"Not executed: {message}")
            return

        if result.stdout:
            self.write(result.stdout)
            if not result.stdout.endswith("\n"):
                self.line()
        if result.stderr:
            if result.stdout:
                self.line()
            self.write(result.stderr)
            if not result.stderr.endswith("\n"):
                self.line()
        if not result.stdout and not result.stderr:
            self.line("(no output)")
        status = f"Exit code: {result.exit_code}"
        if result.duration_ms is not None:
            status += f" ({result.duration_ms:.0f} ms)"
        if result.timed_out:
            status += " — timed out"
        if result.truncated:
            status += " — output truncated"
        self.line(_paint(status, _DIM, self._out_color))

    # -- streaming --------------------------------------------------------

    def stream(self, chunks: Iterable[ChatChunk]) -> StreamResult:
        result = StreamResult()
        started = time.perf_counter()
        first_token_at: float | None = None
        last: ChatChunk | None = None
        iterator = iter(chunks)
        try:
            for chunk in iterator:
                last = chunk
                if chunk.thinking:
                    result.thinking_chars += len(chunk.thinking)
                if chunk.content:
                    if first_token_at is None:
                        first_token_at = time.perf_counter()
                        result.ttft_ms = (first_token_at - started) * 1000.0
                    result.text += chunk.content
                    self.write(chunk.content)
        except KeyboardInterrupt:
            result.interrupted = True
            close = getattr(iterator, "close", None)
            if close is not None:
                close()
        finally:
            result.total_ms = (time.perf_counter() - started) * 1000.0
            if last is not None:
                result.prompt_tokens = last.prompt_eval_count
                result.completion_tokens = last.eval_count
                result.eval_duration_ns = last.eval_duration
            if result.text and not result.text.endswith("\n"):
                self.write("\n")
        return result


def _paint(text: str, color: str, enabled: bool) -> str:
    return f"{color}{text}{_RESET}" if enabled else text


def _is_tty(stream: TextIO) -> bool:
    try:
        return bool(stream.isatty())
    except (AttributeError, ValueError):
        return False


def _supports_color(stream: TextIO) -> bool:
    if os.environ.get("NO_COLOR"):
        return False
    if os.environ.get("TERM") == "dumb":
        return False
    try:
        return bool(stream.isatty())
    except (AttributeError, ValueError):
        return False

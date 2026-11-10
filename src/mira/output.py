"""Terminal output: streaming, ANSI rules, JSON, and debug logging."""

from __future__ import annotations

import json
import os
import sys
import time
from dataclasses import dataclass
from typing import Iterable, TextIO

from .ollama_client import ChatChunk

_RESET = "\033[0m"
_DIM = "\033[2m"
_BOLD = "\033[1m"
_RED = "\033[31m"


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


def _supports_color(stream: TextIO) -> bool:
    if os.environ.get("NO_COLOR"):
        return False
    if os.environ.get("TERM") == "dumb":
        return False
    try:
        return bool(stream.isatty())
    except (AttributeError, ValueError):
        return False

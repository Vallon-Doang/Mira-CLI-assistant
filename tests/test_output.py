from __future__ import annotations

import io
import json

from mira.ollama_client import ChatChunk
from mira.output import Console


def test_stream_output() -> None:
    out, err = io.StringIO(), io.StringIO()
    console = Console(stdout=out, stderr=err)
    result = console.stream(
        [
            ChatChunk(content="hello "),
            ChatChunk(content="world"),
            ChatChunk(done=True, prompt_eval_count=4, eval_count=2, eval_duration=1_000_000_000),
        ]
    )
    assert result.text == "hello world"
    assert out.getvalue() == "hello world\n"
    assert result.ttft_ms is not None
    assert result.prompt_tokens == 4
    assert result.completion_tokens == 2


def test_thinking_is_not_printed() -> None:
    out = io.StringIO()
    console = Console(stdout=out, stderr=io.StringIO())
    result = console.stream([ChatChunk(content="answer", thinking="secret")])
    assert out.getvalue() == "answer\n"
    assert result.thinking_chars == len("secret")


def test_json_output() -> None:
    out = io.StringIO()
    console = Console(json_mode=True, stdout=out, stderr=io.StringIO())
    console.emit_json({"answer": "x"})
    assert json.loads(out.getvalue()) == {"answer": "x"}


def test_cheatsheet_label() -> None:
    out = io.StringIO()
    console = Console(stdout=out, stderr=io.StringIO())
    console.print_cheatsheet("Use /etc/foo.conf")
    assert out.getvalue() == "Use /etc/foo.conf\n\n(local cheatsheet)\n"


def test_debug_only_when_enabled() -> None:
    out, err = io.StringIO(), io.StringIO()
    Console(stdout=out, stderr=err).debug("hidden")
    assert err.getvalue() == ""
    Console(debug=True, stdout=out, stderr=err).debug("shown")
    assert "MIRA debug: shown" in err.getvalue()


def test_error_prefix() -> None:
    err = io.StringIO()
    Console(stdout=io.StringIO(), stderr=err).error("MIRA: failed\n\nhint")
    assert err.getvalue() == "MIRA: failed\n\nhint\n"

from __future__ import annotations

import pytest

from mira.errors import GenerationError, ModelMissingError, OllamaUnreachableError
from mira.ollama_client import OllamaClient


def test_list_models(fake_ollama) -> None:
    client = OllamaClient(fake_ollama.host)
    assert client.model_names() == ["test-model:latest"]


def test_ensure_model(fake_ollama) -> None:
    client = OllamaClient(fake_ollama.host)
    client.ensure_model("test-model:latest")
    with pytest.raises(ModelMissingError, match="not installed"):
        client.ensure_model("missing:latest")


def test_supports_thinking_and_resolve(fake_ollama) -> None:
    client = OllamaClient(fake_ollama.host)
    assert client.supports_thinking("test-model:latest") is True
    assert client.resolve_think("test-model:latest", False) is False
    assert client.resolve_think("test-model:latest", True) is True
    # Cached: only one /api/show request.
    assert fake_ollama.request_count("/api/show") == 1


def test_supports_thinking_false(fake_ollama) -> None:
    fake_ollama.think_supported = False
    client = OllamaClient(fake_ollama.host)
    assert client.supports_thinking("test-model:latest") is False
    assert client.resolve_think("test-model:latest", False) is None


def test_streaming_chat(fake_ollama) -> None:
    fake_ollama.chat_text = "one two three"
    client = OllamaClient(fake_ollama.host)
    chunks = list(
        client.chat(
            "test-model:latest",
            [{"role": "user", "content": "hi"}],
            stream=True,
            think=False,
        )
    )
    text = "".join(chunk.content for chunk in chunks)
    assert text == "one two three"
    assert chunks[-1].done is True
    assert chunks[-1].prompt_eval_count == 12
    assert fake_ollama.last_chat_payload["stream"] is True
    assert fake_ollama.last_chat_payload["think"] is False


def test_non_streaming_chat(fake_ollama) -> None:
    fake_ollama.chat_text = "complete answer"
    client = OllamaClient(fake_ollama.host)
    chunks = list(
        client.chat(
            "test-model:latest",
            [{"role": "user", "content": "hi"}],
            stream=False,
        )
    )
    assert len(chunks) == 1
    assert chunks[0].content == "complete answer"
    assert chunks[0].done is True


def test_thinking_text_is_separate(fake_ollama) -> None:
    fake_ollama.chat_text = "visible"
    fake_ollama.thinking_text = "hidden reasoning"
    client = OllamaClient(fake_ollama.host)
    chunks = list(client.chat("test-model:latest", [{"role": "user", "content": "hi"}]))
    assert "".join(chunk.content for chunk in chunks) == "visible"
    assert any("hidden reasoning" in chunk.thinking for chunk in chunks)


def test_missing_model_on_chat(fake_ollama) -> None:
    client = OllamaClient(fake_ollama.host)
    with pytest.raises(ModelMissingError):
        list(client.chat("missing:latest", [{"role": "user", "content": "hi"}]))


def test_out_of_memory_error(fake_ollama) -> None:
    fake_ollama.fail_status = 500
    fake_ollama.fail_body = "out of memory"
    client = OllamaClient(fake_ollama.host)
    with pytest.raises(GenerationError, match="out of memory"):
        list(client.chat("test-model:latest", [{"role": "user", "content": "hi"}]))


def test_unreachable() -> None:
    client = OllamaClient("http://127.0.0.1:1", timeout=0.5, connect_timeout=0.5)
    with pytest.raises(OllamaUnreachableError, match="not responding"):
        client.check_connection()


def test_check_connection(fake_ollama) -> None:
    OllamaClient(fake_ollama.host).check_connection()

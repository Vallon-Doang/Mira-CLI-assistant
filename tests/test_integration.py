"""Live acceptance tests. Skipped unless MIRA_INTEGRATION=1."""

from __future__ import annotations

import json
import os

import pytest

from mira.cli import main
from mira.config import load_config
from mira.ollama_client import OllamaClient

pytestmark = [
    pytest.mark.integration,
    pytest.mark.skipif(
        os.environ.get("MIRA_INTEGRATION") != "1",
        reason="set MIRA_INTEGRATION=1 to run live Ollama tests",
    ),
]

QUESTIONS = [
    "Where is Apache's configuration file on Fedora?",
    "How do I restart Apache?",
    "How do I check listening ports?",
    "How do I inspect systemd logs?",
    "How do I allow HTTP through firewalld?",
    "How do I check NVIDIA GPU usage?",
    "How do I see my current Git branch?",
    "How do I find Python files recursively?",
    "How do I check available disk space?",
    "How do I inspect an Ollama service failure?",
]


@pytest.fixture(scope="module", autouse=True)
def live_environment() -> None:
    cfg = load_config(create=False)
    client = OllamaClient(cfg.ollama.host, timeout=5)
    try:
        names = client.model_names()
    except Exception as exc:  # noqa: BLE001 - integration guard
        pytest.skip(f"Ollama is not reachable: {exc}")
    if cfg.model.name not in names:
        pytest.skip("configured model is not installed")


@pytest.mark.parametrize("question", QUESTIONS)
def test_acceptance_fast_path(question: str, capsys) -> None:
    code = main([question])
    captured = capsys.readouterr()
    assert code == 0, captured.err
    assert captured.out.strip()
    assert "(local cheatsheet)" in captured.out


@pytest.mark.parametrize("question", QUESTIONS)
def test_acceptance_through_ollama(question: str, capsys) -> None:
    code = main(["--no-cheatsheet", "--json", question])
    captured = capsys.readouterr()
    assert code == 0, captured.err
    payload = json.loads(captured.out)
    assert payload["error"] is None
    assert payload["source"] == "llm"
    assert payload["answer"]

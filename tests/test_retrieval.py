from __future__ import annotations

from pathlib import Path

import pytest

from mira.retrieval import (
    direct_answer,
    load_entries,
    parse_knowledge_file,
    retrieve,
)

VALID = """\
# Test

## Apache configuration
---
os: fedora
keywords: apache, httpd, config
aliases: apache config
direct: true
---
Main configuration: `/etc/httpd/conf/httpd.conf`

## Git branch
---
os: linux
keywords: git, branch, current
aliases: current branch
direct: true
---
```bash
git branch --show-current
```

## Web server notes
---
os: linux
keywords: apache
direct: false
---
Some notes.
"""


def write_knowledge(path: Path, text: str = VALID) -> Path:
    path.write_text(text, encoding="utf-8")
    return path


def test_parse_entries(tmp_path: Path) -> None:
    entries = parse_knowledge_file(write_knowledge(tmp_path / "test.md"))
    assert len(entries) == 3
    assert entries[0].topic == "Apache configuration"
    assert entries[0].direct is True
    assert entries[0].keywords == ("apache", "httpd", "config")
    assert entries[0].source == "test.md"


def test_parse_missing_metadata(tmp_path: Path) -> None:
    path = tmp_path / "bad.md"
    path.write_text("## Broken\nno metadata\n", encoding="utf-8")
    with pytest.raises(ValueError, match="metadata"):
        parse_knowledge_file(path)


def test_parse_empty_body(tmp_path: Path) -> None:
    path = tmp_path / "bad.md"
    path.write_text("## Broken\n---\nos: any\n---\n\n", encoding="utf-8")
    with pytest.raises(ValueError, match="empty body"):
        parse_knowledge_file(path)


def test_retrieve_scores_and_orders(tmp_path: Path) -> None:
    write_knowledge(tmp_path / "test.md")
    entries = load_entries([tmp_path])
    scored = retrieve("where is apache config", entries, os_hint="fedora")
    assert scored[0].entry.topic == "Apache configuration"
    assert scored[0].score > scored[-1].score


def test_retrieve_os_filter(tmp_path: Path) -> None:
    write_knowledge(tmp_path / "test.md")
    entries = load_entries([tmp_path])
    scored = retrieve("apache config", entries, os_hint="debian")
    assert all(item.entry.os != "fedora" for item in scored)


def test_generic_os_matches(tmp_path: Path) -> None:
    write_knowledge(tmp_path / "test.md")
    entries = load_entries([tmp_path])
    scored = retrieve("git branch", entries, os_hint="debian")
    assert scored and scored[0].entry.topic == "Git branch"


def test_primary_keyword_requirement(tmp_path: Path) -> None:
    write_knowledge(tmp_path / "test.md")
    entries = load_entries([tmp_path])
    scored = retrieve("where is nginx config", entries, os_hint="fedora")
    assert all(item.entry.topic != "Apache configuration" for item in scored)


def test_direct_answer_returns_entry(tmp_path: Path) -> None:
    write_knowledge(tmp_path / "test.md")
    entries = load_entries([tmp_path])
    scored = retrieve("where is apache config", entries, os_hint="fedora")
    result = direct_answer("where is apache config", scored)
    assert result is not None
    assert result.entry.topic == "Apache configuration"


def test_direct_answer_requires_direct_flag(tmp_path: Path) -> None:
    write_knowledge(tmp_path / "test.md")
    entries = load_entries([tmp_path])
    scored = retrieve("web server notes", entries, os_hint="fedora")
    assert direct_answer("web server notes", scored) is None


def test_direct_answer_tie_falls_back(tmp_path: Path) -> None:
    text = """\
## Alpha topic
---
os: any
keywords: shared, alpha
direct: true
---
Alpha answer.

## Beta topic
---
os: any
keywords: shared, beta
direct: true
---
Beta answer.
"""
    path = tmp_path / "tie.md"
    path.write_text(text, encoding="utf-8")
    entries = load_entries([tmp_path])
    scored = retrieve("shared", entries, os_hint="fedora")
    assert len(scored) == 2
    assert direct_answer("shared", scored) is None


def test_direct_answer_long_query(tmp_path: Path) -> None:
    write_knowledge(tmp_path / "test.md")
    entries = load_entries([tmp_path])
    query = "apache config " + "word " * 25
    scored = retrieve(query, entries, os_hint="fedora")
    assert direct_answer(query, scored) is None


def test_user_override_wins(tmp_path: Path) -> None:
    bundled = tmp_path / "bundled"
    user = tmp_path / "user"
    bundled.mkdir()
    user.mkdir()
    write_knowledge(bundled / "test.md")
    user_file = user / "test.md"
    user_file.write_text(
        """\
## Apache configuration
---
os: fedora
keywords: apache
direct: true
---
User override.
""",
        encoding="utf-8",
    )
    entries = load_entries([user, bundled])
    apache = [entry for entry in entries if entry.topic == "Apache configuration"]
    assert len(apache) == 1
    assert "User override" in apache[0].body


def test_malformed_file_is_skipped(tmp_path: Path) -> None:
    (tmp_path / "bad.md").write_text("## Broken\nno metadata\n", encoding="utf-8")
    warnings: list[str] = []
    entries = load_entries([tmp_path], warn=warnings.append)
    assert entries == []
    assert warnings and "bad.md" in warnings[0]


def test_bundled_knowledge_parses() -> None:
    entries = load_entries([Path(__file__).resolve().parents[1] / "knowledge"])
    assert len(entries) >= 40
    topics = {entry.topic for entry in entries}
    assert "Apache configuration file" in topics
    assert "Check listening ports" in topics
    assert "Inspect an Ollama service failure" in topics


ACCEPTANCE_QUESTIONS = [
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


@pytest.mark.parametrize("question", ACCEPTANCE_QUESTIONS)
def test_acceptance_questions_have_direct_answers(question: str) -> None:
    entries = load_entries([Path(__file__).resolve().parents[1] / "knowledge"])
    scored = retrieve(question, entries, os_hint="fedora", max_results=3)
    result = direct_answer(question, scored)
    assert result is not None, [item.entry.topic for item in scored]

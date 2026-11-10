from __future__ import annotations

from pathlib import Path

import pytest

from mira.retrieval import (
    DIRECT_MAX_WORDS,
    direct_answer,
    load_entries,
    retrieve,
)

KNOWLEDGE = Path(__file__).resolve().parents[1] / "src" / "mira" / "knowledge"


@pytest.fixture(scope="module")
def entries():
    return load_entries([KNOWLEDGE])


TOPIC_CASES = [
    ("How do I check available disk space?", "Check available disk space"),
    ("Where is Apache's configuration file on Fedora?", "Apache configuration file"),
    ("How do I allow HTTP through firewalld?", "Allow HTTP through the firewall"),
    ("How do I restart a service?", "Restart a service"),
    ("How do I show my IP addresses?", "Show IP addresses"),
    ("How do I test connectivity with ping?", "Test network connectivity"),
    ("How do I list installed Ollama models?", "List installed models"),
    ("How do I create a Python virtual environment?", "Create a virtual environment"),
    ("How do I see the current Git branch?", "Show the current branch"),
    ("How do I check NVIDIA GPU usage?", "Check NVIDIA GPU usage"),
    ("How do I check inode usage?", "Check inode usage"),
    ("How do I open a TCP port in firewalld?", "Open a TCP or UDP port"),
    ("How do I find large files?", "Find large files"),
    ("How do I read kernel messages?", "Read kernel messages"),
    ("How do I check for an OOM kill?", "Check for an out-of-memory kill"),
    ("How do I list firewall rules?", "List firewall rules"),
    ("How do I configure Git?", "Configure Git"),
    ("How do I clone a repository?", "Clone a repository"),
    ("How do I check nginx status?", "Check nginx status"),
    ("How do I install a package on Fedora?", "Install a package"),
    ("How do I change file permissions?", "Change file permissions"),
    ("How do I find what is using a port?", "Find what is using a port"),
    ("How do I show the default gateway?", "Show the default gateway and routes"),
    ("How do I check system load?", "Check system load"),
    ("How do I view service logs?", "View service logs"),
    ("How do I follow logs live?", "Follow logs live"),
    ("How do I check hardware temperature?", "Check hardware temperatures"),
    ("How do I find a running process?", "Find a running process"),
]


@pytest.mark.parametrize(("query", "expected"), TOPIC_CASES)
def test_top_retrieval_topic(entries, query: str, expected: str) -> None:
    scored = retrieve(query, entries, os_hint="fedora", max_results=3)
    assert scored, f"no retrieval result for {query!r}"
    assert scored[0].entry.topic == expected, (
        f"{query!r} -> {scored[0].entry.topic!r}, expected {expected!r}; "
        f"matches={[(item.entry.topic, item.score) for item in scored]}"
    )


def test_unrelated_query_returns_nothing(entries) -> None:
    assert retrieve("How do I bake sourdough bread?", entries, os_hint="fedora") == []


def test_os_filter_excludes_fedora_only_entries(entries) -> None:
    scored = retrieve("How do I install a package with dnf?", entries, os_hint="debian")
    topics = {item.entry.topic for item in scored}
    assert "Install a package" not in topics


def test_os_filter_includes_fedora_entries(entries) -> None:
    scored = retrieve("How do I install a package with dnf?", entries, os_hint="fedora")
    topics = {item.entry.topic for item in scored}
    assert "Install a package" in topics


@pytest.mark.parametrize("os_hint", ["debian", "ubuntu", "arch", "opensuse"])
def test_os_filter_excludes_fedora_entries_on_other_distros(entries, os_hint: str) -> None:
    scored = retrieve("How do I change the hostname?", entries, os_hint=os_hint)
    assert all(item.entry.os != "fedora" for item in scored)


def test_os_filter_keeps_fedora_entries_on_fedora(entries) -> None:
    scored = retrieve("How do I check SELinux status?", entries, os_hint="fedora")
    assert any(item.entry.os == "fedora" for item in scored)


@pytest.mark.parametrize("os_hint", ["debian", "ubuntu", "arch", "opensuse", "fedora"])
def test_linux_entries_are_available_on_all_distros(entries, os_hint: str) -> None:
    scored = retrieve("How do I check system load?", entries, os_hint=os_hint)
    assert any(item.entry.os == "linux" for item in scored)


def test_fast_path_for_unambiguous_direct_entry(entries) -> None:
    scored = retrieve("How do I check available disk space?", entries, os_hint="fedora")
    direct = direct_answer("How do I check available disk space?", scored)
    assert direct is not None
    assert direct.entry.topic == "Check available disk space"


def test_fast_path_rejects_ambiguous_query(entries) -> None:
    query = "How do I check status of Apache and nginx?"
    scored = retrieve(query, entries, os_hint="fedora")
    assert scored[0].score == scored[1].score
    assert direct_answer(query, scored) is None


def test_fast_path_rejects_long_query(entries) -> None:
    query = "How do I check available disk space " + "please " * DIRECT_MAX_WORDS
    scored = retrieve(query, entries, os_hint="fedora")
    assert direct_answer(query, scored) is None


def test_fast_path_rejects_os_incompatible_entry(entries) -> None:
    query = "How do I change the hostname?"
    scored = retrieve(query, entries, os_hint="debian")
    assert direct_answer(query, scored) is None


def test_fast_path_rejects_non_direct_entry(entries) -> None:
    query = "How do I inspect firewall zones?"
    scored = retrieve(query, entries, os_hint="fedora")
    assert scored
    assert scored[0].entry.direct is False
    assert direct_answer(query, scored) is None

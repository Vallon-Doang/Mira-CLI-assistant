from __future__ import annotations

from pathlib import Path

from mira.context import ContextSnapshot
from mira.prompt_builder import ENTRY_BODY_LIMIT, build_messages
from mira.retrieval import Entry, ScoredEntry


def snapshot() -> ContextSnapshot:
    return ContextSnapshot(
        os_name="Fedora Linux",
        os_id="fedora",
        os_version="44",
        kernel="7.2.11",
        arch="x86_64",
        shell="bash",
        cwd_name="project",
        project_types=["Python"],
        git_repo=True,
        git_branch="main",
        git_dirty=False,
        tools=["git", "python3"],
    )


def entry(topic: str = "Apache configuration", body: str = "Use /etc/httpd/conf/httpd.conf") -> ScoredEntry:
    return ScoredEntry(
        entry=Entry(
            topic=topic,
            os="fedora",
            keywords=("apache",),
            aliases=(),
            direct=True,
            body=body,
            source="apache.md",
            path=Path("apache.md"),
        ),
        score=5.0,
    )


def test_build_includes_environment_and_reference() -> None:
    messages, diagnostics = build_messages(
        "where is apache config",
        snapshot(),
        [entry()],
    )
    system = messages[0]["content"]
    assert messages[0]["role"] == "system"
    assert "OS: Fedora Linux 44" in system
    assert "Reference information" in system
    assert "### Apache configuration" in system
    assert messages[-1] == {"role": "user", "content": "where is apache config"}
    assert diagnostics.included_entries


def test_no_context_or_reference() -> None:
    messages, _ = build_messages("hello", None, [])
    system = messages[0]["content"]
    assert "Environment:" not in system
    assert "Reference information" not in system


def test_history_is_included_and_starts_with_user() -> None:
    history = [
        {"role": "assistant", "content": "orphan"},
        {"role": "user", "content": "first"},
        {"role": "assistant", "content": "answer"},
    ]
    messages, _ = build_messages("second", None, [], history=history)
    roles = [message["role"] for message in messages]
    assert roles == ["system", "user", "assistant", "user"]
    assert messages[1]["content"] == "first"


def test_entry_body_is_truncated() -> None:
    long_body = "x" * (ENTRY_BODY_LIMIT + 200)
    messages, diagnostics = build_messages("apache", None, [entry(body=long_body)])
    assert diagnostics.truncated_entry_bodies == 1
    assert "..." in messages[0]["content"]


def test_budget_drops_entries_first() -> None:
    entries = [entry(topic=f"Topic {index}", body="y" * 600) for index in range(6)]
    _, diagnostics = build_messages(
        "question",
        None,
        entries,
        num_ctx=1024,
        output_reserve=256,
    )
    assert diagnostics.dropped_entries > 0
    assert len(diagnostics.included_entries) < len(entries)


def test_budget_drops_history() -> None:
    history = [
        {"role": "user" if index % 2 == 0 else "assistant", "content": "z" * 500}
        for index in range(10)
    ]
    _, diagnostics = build_messages(
        "question",
        None,
        [],
        history=history,
        num_ctx=1024,
        output_reserve=256,
    )
    assert diagnostics.dropped_history > 0

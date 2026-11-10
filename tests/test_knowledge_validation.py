from __future__ import annotations

from pathlib import Path

from mira.knowledge_validation import (
    compare_copies,
    validate_directory,
    validate_repository,
)


def write_entry(path: Path, topic: str = "Topic", body: str = "Use `df -h`.") -> None:
    path.write_text(
        f"## {topic}\n"
        "---\n"
        "os: linux\n"
        "keywords: disk, space\n"
        "aliases: check disk\n"
        "direct: true\n"
        "---\n"
        f"{body}\n",
        encoding="utf-8",
    )


def test_valid_directory(tmp_path: Path) -> None:
    write_entry(tmp_path / "disk.md")
    report = validate_directory(tmp_path)
    assert report.ok
    assert report.entries == 1


def test_missing_keywords(tmp_path: Path) -> None:
    (tmp_path / "bad.md").write_text(
        "## Bad\n---\nos: linux\ndirect: true\n---\nBody\n",
        encoding="utf-8",
    )
    report = validate_directory(tmp_path)
    assert not report.ok
    assert any("no keywords" in error for error in report.errors)


def test_duplicate_topic(tmp_path: Path) -> None:
    write_entry(tmp_path / "a.md", topic="Same")
    write_entry(tmp_path / "b.md", topic="Same")
    report = validate_directory(tmp_path)
    assert not report.ok
    assert any("duplicate topic" in error for error in report.errors)


def test_invalid_os_token(tmp_path: Path) -> None:
    (tmp_path / "bad.md").write_text(
        "## Bad\n---\nos: Fedora Linux!\nkeywords: x\ndirect: true\n---\nBody\n",
        encoding="utf-8",
    )
    report = validate_directory(tmp_path)
    assert not report.ok
    assert any("invalid os token" in error for error in report.errors)


def test_body_too_long(tmp_path: Path) -> None:
    write_entry(tmp_path / "long.md", body="x" * 2_001)
    report = validate_directory(tmp_path)
    assert not report.ok
    assert any("max 2000" in error for error in report.errors)


def test_direct_risky_command_warns(tmp_path: Path) -> None:
    write_entry(tmp_path / "risky.md", body="sudo rm -rf /tmp/x")
    report = validate_directory(tmp_path)
    assert report.ok
    assert any("risky command" in warning for warning in report.warnings)


def test_compare_copies_detects_difference(tmp_path: Path) -> None:
    source = tmp_path / "knowledge"
    package = tmp_path / "package"
    source.mkdir()
    package.mkdir()
    write_entry(source / "a.md")
    write_entry(package / "a.md", body="Different body")
    report = compare_copies(source, package)
    assert not report.ok
    assert any("differs" in error for error in report.errors)


def test_repository_knowledge_is_valid() -> None:
    root = Path(__file__).resolve().parents[1]
    report = validate_repository(root)
    assert report.ok, "\n".join(report.errors)
    assert report.entries >= 100

from __future__ import annotations

import shutil
import subprocess
from pathlib import Path

import pytest

from mira import context


def test_python_project_detection(tmp_path: Path) -> None:
    (tmp_path / "pyproject.toml").write_text("[project]\nname='x'\n", encoding="utf-8")
    snapshot = context.collect_context(cwd=tmp_path)
    assert "Python" in snapshot.project_types
    assert "pyproject.toml" in snapshot.project_files
    assert snapshot.cwd_name == tmp_path.name
    assert "Project files: pyproject.toml" in snapshot.to_prompt()


def test_laravel_project_detection(tmp_path: Path) -> None:
    (tmp_path / "composer.json").write_text("{}", encoding="utf-8")
    (tmp_path / "artisan").write_text("", encoding="utf-8")
    snapshot = context.collect_context(cwd=tmp_path)
    assert "Laravel (PHP)" in snapshot.project_types
    assert "PHP" not in snapshot.project_types


def test_project_detection_in_parent(tmp_path: Path) -> None:
    (tmp_path / "Cargo.toml").write_text("[package]\n", encoding="utf-8")
    child = tmp_path / "src" / "nested"
    child.mkdir(parents=True)
    snapshot = context.collect_context(cwd=child)
    assert "Rust" in snapshot.project_types
    assert snapshot.cwd_name == "nested"


def test_git_detection(tmp_path: Path) -> None:
    if shutil.which("git") is None:
        pytest.skip("git is not installed")
    subprocess.run(["git", "init", "-q", str(tmp_path)], check=True)
    (tmp_path / "file.txt").write_text("x", encoding="utf-8")
    subprocess.run(
        [
            "git",
            "-C",
            str(tmp_path),
            "-c",
            "user.name=Test",
            "-c",
            "user.email=test@example.com",
            "commit",
            "--allow-empty",
            "-q",
            "-m",
            "init",
        ],
        check=True,
    )
    snapshot = context.collect_context(cwd=tmp_path)
    assert snapshot.git_repo is True
    assert snapshot.git_dirty is True
    assert snapshot.git_branch is not None


def test_disabled_context_omits_workspace(tmp_path: Path) -> None:
    snapshot = context.collect_context(enabled=False, cwd=tmp_path)
    assert snapshot.shell is None
    assert snapshot.cwd_name is None
    assert snapshot.tools == []
    assert "Workspace" not in snapshot.to_prompt()


def test_shell_from_env(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setenv("SHELL", "/usr/bin/zsh")
    assert context._detect_shell() == "zsh"


def test_os_release_parsing(tmp_path: Path) -> None:
    release = tmp_path / "os-release"
    release.write_text(
        'NAME="Fedora Linux"\nVERSION_ID="44"\nID=fedora\nPRETTY_NAME="Fedora Linux 44"\n',
        encoding="utf-8",
    )
    parsed = context._read_os_release(str(release))
    assert parsed["NAME"] == "Fedora Linux"
    assert parsed["VERSION_ID"] == "44"
    assert parsed["ID"] == "fedora"


def test_tools_use_which(monkeypatch: pytest.MonkeyPatch, tmp_path: Path) -> None:
    monkeypatch.setattr(context.shutil, "which", lambda name: "/usr/bin/" + name if name == "git" else None)
    snapshot = context.collect_context(cwd=tmp_path)
    assert snapshot.tools == ["git"]


def test_prompt_has_no_absolute_path(tmp_path: Path) -> None:
    (tmp_path / "package.json").write_text("{}", encoding="utf-8")
    snapshot = context.collect_context(cwd=tmp_path)
    prompt = snapshot.to_prompt()
    assert str(tmp_path) not in prompt
    assert "Node.js" in prompt

"""Validation for curated Markdown knowledge entries."""

from __future__ import annotations

import re
from dataclasses import dataclass, field
from pathlib import Path

from .retrieval import Entry, parse_knowledge_file

MAX_BODY = 2_000
DIRECT_BODY_WARN = 600
_OS_RE = re.compile(r"^[a-z0-9][a-z0-9._-]*$")
_RISKY_PATTERNS = (
    re.compile(r"\brm\s+-[a-zA-Z]*r[a-zA-Z]*f?\b"),
    re.compile(r"\bdd\s+if="),
    re.compile(r"\bmkfs(?:\.\w+)?\b"),
    re.compile(r"\bshutdown\b"),
    re.compile(r"\breboot\b"),
    re.compile(r"\bsystemctl\s+(?:stop|disable|mask)\b"),
    re.compile(r"\b(?:dnf|yum)\s+remove\b"),
    re.compile(r"\b(?:apt|apt-get)\s+(?:remove|purge)\b"),
    re.compile(r"\bpacman\s+-R"),
)


@dataclass
class ValidationReport:
    files: int = 0
    entries: int = 0
    errors: list[str] = field(default_factory=list)
    warnings: list[str] = field(default_factory=list)

    @property
    def ok(self) -> bool:
        return not self.errors

    def merge(self, other: "ValidationReport") -> None:
        self.files += other.files
        self.entries += other.entries
        self.errors.extend(other.errors)
        self.warnings.extend(other.warnings)


def validate_dirs(dirs: list[Path]) -> ValidationReport:
    report = ValidationReport()
    for directory in dirs:
        report.merge(validate_directory(directory))
    return report


def validate_directory(directory: Path) -> ValidationReport:
    report = ValidationReport()
    directory = Path(directory)
    if not directory.is_dir():
        report.errors.append(f"{directory}: not a directory")
        return report
    paths = sorted(directory.glob("*.md"))
    if not paths:
        report.errors.append(f"{directory}: no Markdown knowledge files found")
        return report
    seen: dict[str, str] = {}
    for path in paths:
        report.files += 1
        try:
            entries = parse_knowledge_file(path)
        except (OSError, ValueError) as exc:
            report.errors.append(f"{path}: {exc}")
            continue
        if not entries:
            report.errors.append(f"{path}: no '## Topic' entries found")
        for entry in entries:
            report.entries += 1
            key = entry.topic.casefold()
            if key in seen:
                report.errors.append(
                    f"{path}: duplicate topic {entry.topic!r} (also in {seen[key]})"
                )
            else:
                seen[key] = str(path)
            _validate_entry(entry, path, report)
    return report


def compare_copies(source_dir: Path, package_dir: Path) -> ValidationReport:
    """Ensure the packaged knowledge is an exact copy of the source."""
    report = ValidationReport()
    source_dir = Path(source_dir)
    package_dir = Path(package_dir)
    if not source_dir.is_dir():
        report.errors.append(f"{source_dir}: not a directory")
        return report
    if not package_dir.is_dir():
        report.errors.append(f"{package_dir}: not a directory")
        return report
    source_names = {path.name for path in source_dir.glob("*.md")}
    package_names = {path.name for path in package_dir.glob("*.md")}
    for name in sorted(source_names - package_names):
        report.errors.append(f"{package_dir / name}: missing packaged copy")
    for name in sorted(package_names - source_names):
        report.warnings.append(f"{package_dir / name}: packaged file has no source")
    for name in sorted(source_names & package_names):
        source = source_dir / name
        packaged = package_dir / name
        try:
            if source.read_bytes() != packaged.read_bytes():
                report.errors.append(
                    f"{packaged}: differs from source {source}; copy knowledge/ to src/mira/knowledge/"
                )
        except OSError as exc:
            report.errors.append(f"{packaged}: cannot compare: {exc}")
    return report


def validate_repository(root: Path) -> ValidationReport:
    root = Path(root)
    source = root / "knowledge"
    package = root / "src" / "mira" / "knowledge"
    report = ValidationReport()
    report.merge(validate_directory(source))
    report.merge(validate_directory(package))
    report.merge(compare_copies(source, package))
    return report


def _validate_entry(entry: Entry, path: Path, report: ValidationReport) -> None:
    if not entry.topic.strip():
        report.errors.append(f"{path}: empty topic")
    if not entry.keywords:
        report.errors.append(f"{path}: {entry.topic!r} has no keywords")
    for value in entry.os.split(","):
        token = value.strip().lower()
        if token and not _OS_RE.match(token):
            report.errors.append(
                f"{path}: {entry.topic!r} has invalid os token {token!r}"
            )
    if len(entry.body) > MAX_BODY:
        report.errors.append(
            f"{path}: {entry.topic!r} body is {len(entry.body)} chars (max {MAX_BODY})"
        )
    elif entry.direct and len(entry.body) > DIRECT_BODY_WARN:
        report.warnings.append(
            f"{path}: {entry.topic!r} direct body is {len(entry.body)} chars "
            f"(prompt truncates at {DIRECT_BODY_WARN})"
        )
    if entry.direct:
        for pattern in _RISKY_PATTERNS:
            if pattern.search(entry.body):
                report.warnings.append(
                    f"{path}: {entry.topic!r} is direct and contains a risky command"
                )
                break


def format_report(report: ValidationReport) -> str:
    lines = [
        f"Checked {report.files} files and {report.entries} entries.",
        f"Errors: {len(report.errors)}  Warnings: {len(report.warnings)}",
    ]
    if report.errors:
        lines.append("")
        lines.append("Errors:")
        lines.extend(f"  - {item}" for item in report.errors)
    if report.warnings:
        lines.append("")
        lines.append("Warnings:")
        lines.extend(f"  - {item}" for item in report.warnings)
    return "\n".join(lines)


def main(argv: list[str] | None = None) -> int:
    import argparse

    parser = argparse.ArgumentParser(description="Validate MIRA knowledge files.")
    parser.add_argument(
        "--root",
        type=Path,
        default=Path(__file__).resolve().parents[2],
        help="repository root (default: detected from the package)",
    )
    args = parser.parse_args(argv)
    report = validate_repository(args.root)
    print(format_report(report))
    return 0 if report.ok else 1

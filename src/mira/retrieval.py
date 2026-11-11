"""Deterministic local knowledge parsing, retrieval, and the fast path."""

from __future__ import annotations

import re
from dataclasses import dataclass
from pathlib import Path
from typing import Callable

from .config import config_path

DIRECT_MIN_SCORE = 3.0
DIRECT_MAX_WORDS = 20

_STOPWORDS = {
    "a", "an", "and", "are", "as", "at", "be", "by", "can", "do", "does",
    "for", "from", "how", "i", "in", "is", "it", "my", "of", "on", "or",
    "the", "to", "use", "using", "what", "when", "where", "which", "with",
    "you", "your",
}


@dataclass(frozen=True)
class Entry:
    topic: str
    os: str
    keywords: tuple[str, ...]
    aliases: tuple[str, ...]
    direct: bool
    body: str
    source: str
    path: Path


@dataclass(frozen=True)
class ScoredEntry:
    entry: Entry
    score: float

    def to_dict(self) -> dict[str, object]:
        return {
            "topic": self.entry.topic,
            "file": self.entry.source,
            "score": round(self.score, 2),
        }


def knowledge_dirs() -> list[Path]:
    """User override first, then bundled package knowledge."""
    user = config_path().parent / "knowledge"
    bundled = Path(__file__).resolve().parent / "knowledge"
    return [path for path in (user, bundled) if path.is_dir()]


def load_entries(
    dirs: list[Path] | None = None,
    warn: Callable[[str], None] | None = None,
) -> list[Entry]:
    """Load entries, letting user files override bundled topics."""
    entries: list[Entry] = []
    seen: set[str] = set()
    for directory in dirs if dirs is not None else knowledge_dirs():
        for path in sorted(directory.glob("*.md")):
            try:
                parsed = parse_knowledge_file(path)
            except (OSError, ValueError) as exc:
                if warn is not None:
                    warn(f"Skipping knowledge file {path}: {exc}")
                continue
            for entry in parsed:
                key = entry.topic.casefold()
                if key in seen:
                    continue
                seen.add(key)
                entries.append(entry)
    return entries


def parse_knowledge_file(path: Path) -> list[Entry]:
    """Parse one Markdown file containing one or more ``## Topic`` entries."""
    text = Path(path).read_text(encoding="utf-8")
    lines = text.splitlines()
    entries: list[Entry] = []
    index = 0
    while index < len(lines):
        line = lines[index]
        if not line.startswith("## "):
            index += 1
            continue
        topic = line[3:].strip()
        if not topic:
            raise ValueError("entry heading is empty")
        index += 1
        while index < len(lines) and not lines[index].strip():
            index += 1
        if index >= len(lines) or lines[index].strip() != "---":
            raise ValueError(f"entry {topic!r} is missing a metadata block")
        index += 1
        meta: dict[str, str] = {}
        while index < len(lines) and lines[index].strip() != "---":
            raw = lines[index].strip()
            if raw and not raw.startswith("#"):
                if ":" not in raw:
                    raise ValueError(f"invalid metadata line in {topic!r}: {raw!r}")
                key, value = raw.split(":", 1)
                meta[key.strip().lower()] = value.strip()
            index += 1
        if index >= len(lines):
            raise ValueError(f"entry {topic!r} has an unterminated metadata block")
        index += 1
        body_lines: list[str] = []
        while index < len(lines) and not lines[index].startswith("## "):
            body_lines.append(lines[index])
            index += 1
        body = "\n".join(body_lines).strip()
        if not body:
            raise ValueError(f"entry {topic!r} has an empty body")

        keywords = _split_list(meta.get("keywords", ""))
        aliases = _split_list(meta.get("aliases", ""))
        os_value = (meta.get("os") or "any").strip().lower()
        direct = (meta.get("direct") or "false").strip().lower() in ("true", "yes", "1")
        entries.append(
            Entry(
                topic=topic,
                os=os_value,
                keywords=keywords,
                aliases=aliases,
                direct=direct,
                body=body,
                source=Path(path).name,
                path=Path(path),
            )
        )
    return entries


def retrieve(
    query: str,
    entries: list[Entry],
    os_hint: str = "",
    max_results: int = 3,
    context: str = "",
) -> list[ScoredEntry]:
    """Score entries deterministically and return the best matches.

    ``context`` (for example the previous conversation turn) is scored at half
    weight so the current question dominates.
    """
    text = _normalize(query)
    tokens = {token for token in text.split() if len(token) >= 2}
    context_text = _normalize(context)
    context_tokens = {token for token in context_text.split() if len(token) >= 2}
    scored: list[ScoredEntry] = []
    for entry in entries:
        if not _os_allowed(entry.os, os_hint):
            continue
        score = _score_entry(entry, text, tokens)
        if context_text:
            score += 0.5 * _score_entry(entry, context_text, context_tokens)
        if score > 0:
            scored.append(ScoredEntry(entry=entry, score=score))
    scored.sort(key=lambda item: (-item.score, item.entry.topic.casefold(), item.entry.source))
    return scored[: max(0, max_results)]


def _score_entry(entry: Entry, text: str, tokens: set[str]) -> float:
    score = 0.0
    primary_hit = False
    alias_hit = False
    for index, keyword in enumerate(entry.keywords):
        phrase = _normalize(keyword)
        if phrase and _contains_phrase(text, phrase):
            score += 2.0
            if index == 0:
                primary_hit = True
    for alias in entry.aliases:
        phrase = _normalize(alias)
        if phrase and _contains_phrase(text, phrase):
            score += 3.0
            alias_hit = True
    # Require the entry's subject (first keyword) or an alias. This keeps
    # generic words such as "config" from pulling in unrelated topics.
    if entry.keywords and not (primary_hit or alias_hit):
        return 0.0
    for token in _normalize(entry.topic).split():
        if token in _STOPWORDS or len(token) < 2:
            continue
        if token in tokens:
            score += 1.0
    return score


def direct_answer(
    query: str,
    scored: list[ScoredEntry],
) -> ScoredEntry | None:
    """Return a curated answer only when the match is unambiguous.

    A single generic keyword is not enough.  The query must cover the entry's
    topic words or match one of its aliases; otherwise a question like "fix my
    printer on Fedora" must not be answered with the "Fedora version" entry.
    """
    if not scored:
        return None
    top = scored[0]
    if not top.entry.direct:
        return None
    if top.score < DIRECT_MIN_SCORE:
        return None
    if len(scored) > 1 and scored[1].score == top.score:
        return None
    if len(query.split()) > DIRECT_MAX_WORDS:
        return None
    if not _topic_covered(query, top.entry):
        return None
    return top


def _topic_covered(query: str, entry: Entry) -> bool:
    text = _normalize(query)
    tokens = {token for token in text.split() if len(token) >= 2}
    topic_tokens = [
        token
        for token in _normalize(entry.topic).split()
        if token not in _STOPWORDS and len(token) >= 2
    ]
    if not topic_tokens:
        return True
    if all(token in tokens for token in topic_tokens):
        return True
    # Aliases are curated synonyms, so they may stand in for a topic word.
    return any(
        phrase and _contains_phrase(text, _normalize(phrase))
        for phrase in entry.aliases
    )


def render_direct(entry: Entry) -> str:
    return f"{entry.body}\n\n(local cheatsheet)"


def _normalize(value: str) -> str:
    value = value.casefold()
    value = re.sub(r"[^a-z0-9+_.-]+", " ", value)
    return " ".join(value.split())


def _contains_phrase(text: str, phrase: str) -> bool:
    return f" {phrase} " in f" {text} "


def _split_list(value: str) -> tuple[str, ...]:
    return tuple(part.strip() for part in value.split(",") if part.strip())


def _os_allowed(entry_os: str, os_hint: str) -> bool:
    values = [part.strip().lower() for part in entry_os.split(",") if part.strip()]
    if not values or any(value in ("any", "all", "linux") for value in values):
        return True
    hint = os_hint.strip().lower()
    if not hint:
        return True
    return any(value in hint or hint in value for value in values)

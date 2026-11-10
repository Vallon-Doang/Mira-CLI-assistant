#!/usr/bin/env python3
"""Benchmark MIRA against a live Ollama server.

Metrics come from Ollama's response metadata; unavailable values are reported
as ``n/a`` rather than estimated.
"""

from __future__ import annotations

import argparse
import json
import sys
import time
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
if str(ROOT / "src") not in sys.path:
    sys.path.insert(0, str(ROOT / "src"))

from mira.config import load_config  # noqa: E402
from mira.context import collect_context  # noqa: E402
from mira.ollama_client import OllamaClient  # noqa: E402
from mira.prompt_builder import build_messages  # noqa: E402
from mira.retrieval import load_entries, retrieve  # noqa: E402

DEFAULT_QUESTIONS = [
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


def parse_args(argv: list[str] | None = None) -> argparse.Namespace:
    parser = argparse.ArgumentParser(description="Benchmark MIRA with a live Ollama server.")
    parser.add_argument("--json", action="store_true", help="emit JSON instead of a table")
    parser.add_argument("--model", help="override the configured model")
    parser.add_argument("--host", help="override the Ollama host")
    parser.add_argument(
        "--questions",
        type=Path,
        help="file with one question per line (default: the 10 acceptance questions)",
    )
    parser.add_argument("--no-cheatsheet", action="store_true", help="disable retrieval")
    parser.add_argument("--explain", action="store_true", help="benchmark explain-mode limits")
    return parser.parse_args(argv)


def load_questions(path: Path | None) -> list[str]:
    if path is None:
        return list(DEFAULT_QUESTIONS)
    questions = [
        line.strip()
        for line in path.read_text(encoding="utf-8").splitlines()
        if line.strip() and not line.lstrip().startswith("#")
    ]
    if not questions:
        raise SystemExit(f"No questions found in {path}")
    return questions


def main(argv: list[str] | None = None) -> int:
    args = parse_args(argv)
    cfg = load_config(create=True)
    if args.model:
        cfg.model.name = args.model
    if args.host:
        cfg.ollama.host = args.host
    questions = load_questions(args.questions)

    client = OllamaClient(cfg.ollama.host, timeout=cfg.ollama.timeout)
    client.check_connection()
    client.ensure_model(cfg.model.name)
    think = client.resolve_think(cfg.model.name, cfg.behavior.thinking)

    entries = [] if args.no_cheatsheet else load_entries()
    rows: list[dict[str, object]] = []
    for question in questions:
        snapshot = collect_context(True)
        scored = (
            []
            if args.no_cheatsheet
            else retrieve(
                question,
                entries,
                os_hint=snapshot.os_id,
                max_results=cfg.retrieval.max_results,
            )
        )
        if args.explain:
            temperature = cfg.model.explain_temperature
            num_predict = cfg.model.explain_num_predict
        else:
            temperature = cfg.model.temperature
            num_predict = cfg.model.num_predict
        messages, _ = build_messages(
            question,
            snapshot,
            scored,
            num_ctx=cfg.model.num_ctx,
            output_reserve=num_predict,
        )
        options = {
            "temperature": temperature,
            "num_predict": num_predict,
            "num_ctx": cfg.model.num_ctx,
        }

        started = time.perf_counter()
        ttft_ms: float | None = None
        text: list[str] = []
        last = None
        try:
            for chunk in client.chat(
                model=cfg.model.name,
                messages=messages,
                options=options,
                think=think,
                stream=True,
                keep_alive=cfg.model.keep_alive,
            ):
                last = chunk
                if chunk.content:
                    if ttft_ms is None:
                        ttft_ms = (time.perf_counter() - started) * 1000.0
                    text.append(chunk.content)
        except KeyboardInterrupt:
            print("\nInterrupted.", file=sys.stderr)
            return 130
        total_ms = (time.perf_counter() - started) * 1000.0

        eval_count = last.eval_count if last is not None else None
        eval_duration = last.eval_duration if last is not None else None
        tokens_per_second = None
        if eval_count and eval_duration:
            tokens_per_second = eval_count / (eval_duration / 1_000_000_000)

        rows.append(
            {
                "question": question,
                "ttft_ms": round(ttft_ms, 1) if ttft_ms is not None else None,
                "total_ms": round(total_ms, 1),
                "tokens_per_second": round(tokens_per_second, 2)
                if tokens_per_second is not None
                else None,
                "prompt_tokens": last.prompt_eval_count if last is not None else None,
                "completion_tokens": eval_count,
                "retrieval_used": bool(scored),
                "retrieval_matches": len(scored),
                "answer_chars": len("".join(text)),
                "model": cfg.model.name,
            }
        )

    if args.json:
        print(json.dumps({"model": cfg.model.name, "results": rows}, indent=2))
        return 0

    header = (
        f"{'QUESTION':<44} {'TTFT ms':>9} {'TOTAL ms':>9} {'TOK/S':>8} "
        f"{'PROMPT':>7} {'EVAL':>6} {'RETR':>5}"
    )
    print(header)
    print("-" * len(header))
    for row in rows:
        question = str(row["question"])
        if len(question) > 42:
            question = question[:41] + "…"
        print(
            f"{question:<44} "
            f"{_fmt(row['ttft_ms'], 1):>9} "
            f"{_fmt(row['total_ms'], 1):>9} "
            f"{_fmt(row['tokens_per_second'], 2):>8} "
            f"{_fmt(row['prompt_tokens'], 0):>7} "
            f"{_fmt(row['completion_tokens'], 0):>6} "
            f"{'yes' if row['retrieval_used'] else 'no':>5}"
        )

    print()
    print(f"Model: {cfg.model.name}")
    print(f"Questions: {len(rows)}")
    print(f"Mean TTFT: {_mean(rows, 'ttft_ms')} ms")
    print(f"Mean total: {_mean(rows, 'total_ms')} ms")
    print(f"Mean tokens/s: {_mean(rows, 'tokens_per_second')}")
    return 0


def _fmt(value: object, digits: int) -> str:
    if value is None:
        return "n/a"
    if isinstance(value, float):
        return f"{value:.{digits}f}"
    return str(value)


def _mean(rows: list[dict[str, object]], key: str) -> str:
    values = [row[key] for row in rows if isinstance(row.get(key), (int, float))]
    if not values:
        return "n/a"
    return f"{sum(values) / len(values):.2f}"


if __name__ == "__main__":
    raise SystemExit(main())

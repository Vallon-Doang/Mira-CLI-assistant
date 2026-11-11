"""Command-line interface and orchestration."""

from __future__ import annotations

import argparse
import json
import shutil
import subprocess
import sys
import time
import traceback
from dataclasses import dataclass, field

from . import __version__
from .config import Config, load_config, set_config_value
from .context import ContextSnapshot, collect_context
from .conversation import Conversation, run_repl
from .errors import (
    EXIT_GENERIC,
    EXIT_INTERRUPTED,
    EXIT_OK,
    MiraError,
    UsageError,
)
from .execution import (
    RISK_DESTRUCTIVE,
    STATUS_AMBIGUOUS,
    STATUS_CONFIRMATION_REQUIRED,
    STATUS_DECLINED,
    STATUS_EXECUTED,
    STATUS_NO_COMMAND,
    STATUS_REFUSED_DESTRUCTIVE,
    STATUS_SPAWN_FAILED,
    CommandPlan,
    ExecutionResult,
    classify,
    execute_plan,
    extract_command,
)
from .ollama_client import OllamaClient
from .output import Console, StreamResult
from .prompt_builder import PromptDiagnostics, build_messages
from .retrieval import (
    Entry,
    ScoredEntry,
    direct_answer,
    knowledge_dirs,
    load_entries,
    retrieve,
)


class MiraArgumentParser(argparse.ArgumentParser):
    def error(self, message: str) -> None:  # type: ignore[override]
        raise UsageError(message, hint=self.format_usage().strip())


@dataclass
class TurnOutcome:
    text: str
    source: str
    snapshot: ContextSnapshot | None
    retrieval: list[ScoredEntry] = field(default_factory=list)
    prompt_diag: PromptDiagnostics | None = None
    stream_result: StreamResult | None = None
    direct_entry: Entry | None = None
    execution: ExecutionResult | None = None
    interrupted: bool = False
    streamed: bool = False
    total_ms: float = 0.0
    ttft_ms: float | None = None
    prompt_tokens: int | None = None
    completion_tokens: int | None = None


def build_parser() -> MiraArgumentParser:
    parser = MiraArgumentParser(
        prog="mira",
        description="A fast local Linux assistant powered by Ollama.",
    )
    parser.add_argument("query", nargs="*", help="question (quoted or unquoted)")
    parser.add_argument(
        "-explain",
        "--explain",
        action="store_true",
        help="give a longer, step-by-step explanation",
    )
    parser.add_argument(
        "-converse",
        "--converse",
        action="store_true",
        help="start an interactive conversation",
    )
    parser.add_argument("--model", metavar="MODEL", help="override the model for this invocation")
    parser.add_argument("--list-models", action="store_true", help="list installed Ollama models")
    parser.add_argument("--set-model", metavar="MODEL", help="persist a new default model")
    parser.add_argument("--show-config", action="store_true", help="show the effective configuration")
    parser.add_argument(
        "-execute",
        "--execute",
        action="store_true",
        help="allow MIRA to run one command proposed by the model",
    )
    parser.add_argument(
        "--yes",
        action="store_true",
        help="skip confirmation for safe and moderate commands (destructive still needs --allow-destructive)",
    )
    parser.add_argument(
        "--allow-destructive",
        action="store_true",
        help="permit destructive commands (still confirmed unless --yes is also given)",
    )
    parser.add_argument(
        "--confirm-safe",
        action="store_true",
        help="ask before running safe commands instead of running them automatically",
    )
    parser.add_argument("--doctor", action="store_true", help="run local installation diagnostics")
    parser.add_argument("--debug", action="store_true", help="show timing and diagnostics on stderr")
    parser.add_argument("--no-context", action="store_true", help="disable environment detection")
    parser.add_argument("--no-cheatsheet", action="store_true", help="disable local knowledge retrieval")
    parser.add_argument("--json", action="store_true", help="emit one structured JSON object")
    parser.add_argument("--version", action="version", version=f"mira {__version__}")
    return parser


def main(argv: list[str] | None = None) -> int:
    parser = build_parser()
    try:
        args = parser.parse_args(argv)
    except UsageError as exc:
        raw_argv = argv if argv is not None else sys.argv[1:]
        wants_json = "--json" in raw_argv
        console = Console(debug="--debug" in raw_argv, json_mode=wants_json)
        if wants_json:
            console.emit_json(_error_payload(exc))
        else:
            console.error(exc.render())
        return exc.exit_code
    except SystemExit as exc:
        return int(exc.code or 0)

    console = Console(debug=args.debug, json_mode=args.json)
    try:
        return _run(args, console)
    except MiraError as exc:
        _report_error(exc, console, args)
        return exc.exit_code
    except KeyboardInterrupt:
        console.line()
        if args.debug:
            traceback.print_exc(file=sys.stderr)
        exc = MiraError("Interrupted.")
        _report_error(exc, console, args)
        return EXIT_INTERRUPTED
    except Exception as exc:  # pragma: no cover - defensive
        if args.debug:
            traceback.print_exc(file=sys.stderr)
        _report_error(MiraError(f"Unexpected error: {exc}"), console, args)
        return EXIT_GENERIC


def _run(args: argparse.Namespace, console: Console) -> int:
    query = " ".join(args.query).strip()

    management = [
        args.list_models,
        args.set_model is not None,
        args.show_config,
        args.doctor,
    ]
    if sum(1 for item in management if item) > 1:
        raise UsageError(
            "Use only one of --list-models, --set-model, --show-config, or --doctor."
        )

    if args.json and args.converse:
        raise UsageError("--json cannot be combined with --converse.")
    if args.model and args.set_model:
        raise UsageError("Use either --model (one invocation) or --set-model (persist), not both.")
    if args.doctor and (args.converse or args.explain):
        raise UsageError("--doctor cannot be combined with --converse or --explain.")
    if any(management) and query:
        raise UsageError("Management flags do not take a question.")

    cfg = load_config(create=True)
    if args.model:
        cfg.model.name = args.model.strip()
    if args.no_context:
        cfg.behavior.context_detection = False
    if args.no_cheatsheet:
        cfg.behavior.cheatsheet = False

    execution_enabled = args.execute or cfg.execution.enabled
    if (args.yes or args.allow_destructive or args.confirm_safe) and not execution_enabled:
        raise UsageError(
            "--yes, --allow-destructive, and --confirm-safe require --execute "
            "or [execution] enabled = true."
        )

    client = OllamaClient(cfg.ollama.host, timeout=cfg.ollama.timeout)

    if args.show_config:
        return _show_config(cfg, console)
    if args.list_models:
        return _list_models(cfg, client, console)
    if args.set_model:
        return _set_model(cfg, client, console, args.set_model)
    if args.doctor:
        return _doctor(cfg, client, console)

    mode = _resolve_mode(args, cfg)
    if mode == "converse" and args.json:
        raise UsageError("--json cannot be combined with conversation mode.")
    if mode == "converse":
        return _converse(cfg, client, console, query, args)
    if not query:
        if not sys.stdin.isatty():
            query = sys.stdin.read().strip()
        if not query:
            raise UsageError(
                "No question provided.",
                hint='Try: mira "How do I check disk space?"',
            )

    outcome = _generate(
        cfg,
        client,
        console,
        question=query,
        mode=mode,
        history=[],
        previous_user=None,
        stream=not args.json and cfg.ollama.stream and not execution_enabled,
        execution_enabled=execution_enabled,
    )

    if outcome.interrupted:
        return EXIT_INTERRUPTED

    command, issue = (None, None)
    if execution_enabled and outcome.direct_entry is None:
        command, issue = _prepare_execution(outcome)

    if args.json:
        report = (
            _execute_command(cfg, console, command, issue, args, interactive=False)
            if execution_enabled
            else None
        )
        payload = _payload(cfg, mode, outcome, report)
        failed = report is not None and report.status in (
            STATUS_AMBIGUOUS,
            STATUS_CONFIRMATION_REQUIRED,
            STATUS_REFUSED_DESTRUCTIVE,
            STATUS_SPAWN_FAILED,
        )
        if failed:
            payload["error"] = {
                "code": EXIT_GENERIC,
                "message": report.message or "The proposed command was not executed.",
                "hint": None,
            }
        elif not outcome.text.strip() and not (report and report.executed):
            payload["error"] = {
                "code": EXIT_GENERIC,
                "message": "The model returned an empty response.",
                "hint": None,
            }
            console.emit_json(payload)
            return EXIT_GENERIC
        console.emit_json(payload)
        return EXIT_GENERIC if failed else EXIT_OK

    if outcome.direct_entry is not None:
        console.print_cheatsheet(outcome.direct_entry.body)
    elif not outcome.streamed and outcome.text.strip():
        console.line(outcome.text.rstrip())

    report = None
    if execution_enabled:
        report = _execute_command(cfg, console, command, issue, args, interactive=True)
        if report is not None:
            console.print_execution(report)

    if not outcome.text.strip() and not (report and (report.executed or report.command)):
        if not (report and report.message):
            console.error("The model returned an empty response.")
        return EXIT_GENERIC
    if report is not None and report.status in (
        STATUS_AMBIGUOUS,
        STATUS_CONFIRMATION_REQUIRED,
        STATUS_REFUSED_DESTRUCTIVE,
        STATUS_SPAWN_FAILED,
    ):
        return EXIT_GENERIC
    return EXIT_OK


def _resolve_mode(args: argparse.Namespace, cfg: Config) -> str:
    if args.converse:
        return "converse"
    if args.explain:
        return "explain"
    if cfg.behavior.default_mode == "converse":
        return "converse"
    if cfg.behavior.default_mode == "explain":
        return "explain"
    return "oneshot"


def _generate(
    cfg: Config,
    client: OllamaClient,
    console: Console,
    question: str,
    mode: str,
    history: list[dict[str, str]],
    previous_user: str | None,
    stream: bool,
    execution_enabled: bool = False,
) -> TurnOutcome:
    started = time.perf_counter()
    snapshot = collect_context(cfg.behavior.context_detection)
    prompt_snapshot = snapshot if cfg.behavior.context_detection else None
    if prompt_snapshot is not None:
        console.debug("environment:\n" + prompt_snapshot.to_prompt())
    else:
        console.debug("environment: disabled")

    entries: list[Entry] = []
    scored: list[ScoredEntry] = []
    if cfg.behavior.cheatsheet:
        entries = load_entries(warn=console.debug)
        retrieval_context = previous_user if mode == "converse" and previous_user else ""
        scored = retrieve(
            question,
            entries,
            os_hint=snapshot.os_id,
            max_results=cfg.retrieval.max_results,
            context=retrieval_context,
        )
        console.debug(f"knowledge: {len(entries)} entries loaded, {len(scored)} matched")
        if not entries:
            console.debug(
                "knowledge: no entries found (checked bundled and user directories)"
            )
        for item in scored:
            console.debug(
                f"  match: {item.entry.topic} [{item.entry.source}] score={item.score:g}"
            )

    if mode == "oneshot" and cfg.behavior.direct_answers:
        direct = direct_answer(question, scored)
        if direct is not None:
            total_ms = (time.perf_counter() - started) * 1000.0
            console.debug(f"fast path: answered from {direct.entry.source}")
            console.debug(f"timing: total={total_ms:.0f}ms")
            return TurnOutcome(
                text=direct.entry.body,
                source="cheatsheet",
                snapshot=prompt_snapshot,
                retrieval=scored,
                direct_entry=direct.entry,
                total_ms=total_ms,
            )

    if mode == "explain":
        temperature = cfg.model.explain_temperature
        num_predict = cfg.model.explain_num_predict
    else:
        temperature = cfg.model.temperature
        num_predict = cfg.model.num_predict

    console.debug(
        "request:\n"
        f"  model: {cfg.model.name}\n"
        f"  mode: {mode}\n"
        f"  endpoint: {cfg.ollama.host}\n"
        f"  temperature: {temperature}\n"
        f"  num_predict: {num_predict}\n"
        f"  num_ctx: {cfg.model.num_ctx}\n"
        f"  keep_alive: {cfg.model.keep_alive}"
    )

    client.check_connection()
    client.ensure_model(cfg.model.name)

    think = client.resolve_think(cfg.model.name, cfg.behavior.thinking)
    if think is None:
        console.debug("thinking: model has no thinking control; parameter omitted")
    else:
        console.debug(f"thinking: {think}")

    messages, diagnostics = build_messages(
        question=question,
        snapshot=prompt_snapshot,
        entries=scored,
        history=history,
        num_ctx=cfg.model.num_ctx,
        output_reserve=num_predict,
        execution_enabled=execution_enabled,
    )
    console.debug(
        "prompt:\n"
        + json.dumps(diagnostics.to_dict(), indent=2)
    )

    options = {
        "temperature": temperature,
        "num_predict": num_predict,
        "num_ctx": cfg.model.num_ctx,
    }

    outcome = TurnOutcome(
        text="",
        source="llm",
        snapshot=prompt_snapshot,
        retrieval=scored,
        prompt_diag=diagnostics,
    )

    if stream:
        result = console.stream(
            client.chat(
                model=cfg.model.name,
                messages=messages,
                options=options,
                think=think,
                stream=True,
                keep_alive=cfg.model.keep_alive,
            )
        )
        outcome.text = result.text
        outcome.stream_result = result
        outcome.interrupted = result.interrupted
        outcome.streamed = True
        outcome.ttft_ms = result.ttft_ms
        outcome.prompt_tokens = result.prompt_tokens
        outcome.completion_tokens = result.completion_tokens
        outcome.total_ms = (time.perf_counter() - started) * 1000.0
        if result.thinking_chars:
            console.debug(f"thinking text suppressed: {result.thinking_chars} chars")
    else:
        chunks = list(
            client.chat(
                model=cfg.model.name,
                messages=messages,
                options=options,
                think=think,
                stream=False,
                keep_alive=cfg.model.keep_alive,
            )
        )
        chunk = chunks[-1] if chunks else None
        outcome.text = chunk.content if chunk else ""
        outcome.prompt_tokens = chunk.prompt_eval_count if chunk else None
        outcome.completion_tokens = chunk.eval_count if chunk else None
        outcome.total_ms = (time.perf_counter() - started) * 1000.0
        if chunk and chunk.thinking:
            console.debug(f"thinking text suppressed: {len(chunk.thinking)} chars")

    if outcome.interrupted:
        console.debug("generation interrupted")
        return outcome

    console.debug(
        f"timing: total={outcome.total_ms:.0f}ms"
        + (f" ttft={outcome.ttft_ms:.0f}ms" if outcome.ttft_ms is not None else "")
    )
    console.debug(
        f"tokens: prompt={outcome.prompt_tokens if outcome.prompt_tokens is not None else 'n/a'}"
        f" completion={outcome.completion_tokens if outcome.completion_tokens is not None else 'n/a'}"
    )
    return outcome


def _converse(
    cfg: Config,
    client: OllamaClient,
    console: Console,
    initial: str,
    args: argparse.Namespace,
) -> int:
    conversation = Conversation(cfg.conversation.max_messages)
    mode = "explain" if args.explain else "converse"
    execution_enabled = args.execute or cfg.execution.enabled

    def respond(question: str) -> None:
        try:
            outcome = _generate(
                cfg,
                client,
                console,
                question=question,
                mode=mode,
                history=conversation.history(),
                previous_user=conversation.previous_user(),
                stream=cfg.ollama.stream and not execution_enabled,
                execution_enabled=execution_enabled,
            )
        except MiraError as exc:
            console.error(exc.render())
            return
        if outcome.interrupted:
            console.debug("generation interrupted; conversation preserved")
            return

        command, issue = (None, None)
        if execution_enabled and outcome.direct_entry is None:
            command, issue = _prepare_execution(outcome)

        if not outcome.streamed and outcome.text.strip():
            console.line(outcome.text.rstrip())

        report = None
        if execution_enabled:
            report = _execute_command(cfg, console, command, issue, args, interactive=True)
            if report is not None:
                console.print_execution(report)

        if not outcome.text.strip() and not (
            report and (report.executed or report.command or report.message)
        ):
            console.error("The model returned an empty response.")
            return

        conversation.add_user(question)
        assistant = outcome.text.strip()
        if not assistant and report is not None and report.command:
            assistant = f"Command proposed: {report.command}"
        if assistant:
            conversation.add_assistant(assistant)

    return run_repl(respond, initial or None, conversation)


def _prepare_execution(outcome: TurnOutcome) -> tuple[str | None, str | None]:
    cleaned, command, issue = extract_command(outcome.text)
    outcome.text = cleaned
    return command, issue


def _execute_command(
    cfg: Config,
    console: Console,
    command: str | None,
    issue: str | None,
    args: argparse.Namespace,
    interactive: bool,
) -> ExecutionResult:
    if issue is not None:
        return ExecutionResult(status=STATUS_AMBIGUOUS, message=issue)
    if not command:
        return ExecutionResult(status=STATUS_NO_COMMAND)

    plan = classify(command)
    confirm_safe = args.confirm_safe or cfg.execution.confirm_safe
    if plan.auto_run and not confirm_safe:
        return execute_plan(
            plan,
            timeout=cfg.execution.timeout,
            max_output=cfg.execution.max_output,
        )

    if plan.risk == RISK_DESTRUCTIVE:
        allowed = args.allow_destructive or cfg.execution.allow_destructive
        if not allowed:
            return _plan_result(
                plan,
                STATUS_REFUSED_DESTRUCTIVE,
                "Destructive command blocked. Add --allow-destructive to permit it.",
            )

    if args.yes:
        return execute_plan(
            plan,
            timeout=cfg.execution.timeout,
            max_output=cfg.execution.max_output,
        )

    if interactive and console.is_interactive():
        prompt = f"Run this {plan.risk} command?\n  {plan.command}\n"
        if plan.shell_features:
            prompt += f"Shell features: {', '.join(plan.shell_features)}\n"
        prompt += "Execute? [y/N] "
        if console.confirm(prompt):
            return execute_plan(
                plan,
                timeout=cfg.execution.timeout,
                max_output=cfg.execution.max_output,
            )
        return _plan_result(plan, STATUS_DECLINED, "Not executed.")

    return _plan_result(
        plan,
        STATUS_CONFIRMATION_REQUIRED,
        "Command requires confirmation; rerun interactively or with --yes.",
    )


def _plan_result(plan: CommandPlan, status: str, message: str) -> ExecutionResult:
    return ExecutionResult(
        status=status,
        command=plan.command,
        risk=plan.risk,
        reason=plan.reason,
        shell=plan.shell,
        shell_features=list(plan.shell_features),
        executed=False,
        message=message,
    )


def _doctor(cfg: Config, client: OllamaClient, console: Console) -> int:
    checks: list[dict[str, object]] = []

    def add(name: str, status: str, detail: str, hint: str | None = None) -> None:
        checks.append(
            {"name": name, "status": status, "detail": detail, "hint": hint}
        )

    py = sys.version_info
    add(
        "Python",
        "ok" if py >= (3, 12) else "fail",
        f"{py.major}.{py.minor}.{py.micro}",
        None if py >= (3, 12) else "MIRA requires Python 3.12 or newer.",
    )
    add("Config", "ok", str(cfg.path))

    ollama_bin = shutil.which("ollama")
    add(
        "Ollama binary",
        "ok" if ollama_bin else "warn",
        ollama_bin or "not found",
        None if ollama_bin else "Install Ollama from https://ollama.com/download",
    )

    api_ok = False
    try:
        version = client.version()
        api_ok = True
        add("Ollama API", "ok", f"version {version.get('version', 'unknown')}")
    except MiraError as exc:
        add("Ollama API", "fail", exc.message, exc.hint)

    model_ok = False
    if api_ok:
        try:
            client.ensure_model(cfg.model.name)
            model_ok = True
            add("Model", "ok", cfg.model.name)
        except MiraError as exc:
            add("Model", "fail", exc.message, exc.hint)
    else:
        add("Model", "fail", cfg.model.name, "Start Ollama, then rerun --doctor.")

    if api_ok and model_ok:
        try:
            supported = client.supports_thinking(cfg.model.name)
            add(
                "Thinking control",
                "ok",
                "supported" if supported else "not supported; parameter omitted",
            )
        except MiraError as exc:
            add("Thinking control", "warn", exc.message)
    else:
        add("Thinking control", "warn", "not checked")

    try:
        entries = load_entries()
        dirs = knowledge_dirs()
        if entries:
            add(
                "Knowledge",
                "ok",
                f"{len(entries)} entries from {len(dirs)} director"
                f"{'y' if len(dirs) == 1 else 'ies'}",
            )
        else:
            add(
                "Knowledge",
                "fail",
                "no entries loaded",
                "Run: python scripts/validate_knowledge.py",
            )
    except Exception as exc:  # pragma: no cover - defensive
        add("Knowledge", "fail", str(exc))

    git_bin = shutil.which("git")
    add(
        "Git",
        "ok" if git_bin else "warn",
        git_bin or "not found",
        None if git_bin else "Install git for repository context.",
    )

    smi = shutil.which("nvidia-smi")
    if smi:
        try:
            proc = subprocess.run(
                [
                    smi,
                    "--query-gpu=name,memory.total,memory.used",
                    "--format=csv,noheader",
                ],
                stdin=subprocess.DEVNULL,
                capture_output=True,
                text=True,
                timeout=2,
                check=False,
            )
            detail = proc.stdout.strip().splitlines()
            add(
                "GPU",
                "ok" if proc.returncode == 0 and detail else "warn",
                detail[0] if detail else "nvidia-smi returned no data",
            )
        except (OSError, subprocess.TimeoutExpired) as exc:
            add("GPU", "warn", str(exc))
    else:
        add("GPU", "warn", "nvidia-smi not found")

    if cfg.behavior.context_detection:
        try:
            snapshot = collect_context(True)
            add(
                "Environment",
                "ok",
                f"{snapshot.os_name} {snapshot.os_version}; "
                f"{snapshot.arch}; shell={snapshot.shell}; cwd={snapshot.cwd_name}",
            )
        except Exception as exc:  # pragma: no cover - defensive
            add("Environment", "warn", str(exc))
    else:
        add("Environment", "warn", "context detection disabled")

    add(
        "Execution",
        "ok" if cfg.execution.enabled else "warn",
        f"enabled={_yes_no(cfg.execution.enabled)}, "
        f"timeout={cfg.execution.timeout:g}s, "
        f"destructive={_yes_no(cfg.execution.allow_destructive)}, "
        f"confirm_safe={_yes_no(cfg.execution.confirm_safe)}",
        None
        if cfg.execution.enabled
        else "Use --execute per invocation or set [execution] enabled = true.",
    )

    ok = not any(check["status"] == "fail" for check in checks)
    if console.json_mode:
        console.emit_json({"ok": ok, "checks": checks})
    else:
        labels = {"ok": "OK", "warn": "WARN", "fail": "FAIL"}
        for check in checks:
            console.line(f"[{labels[str(check['status'])]}] {check['name']}: {check['detail']}")
            if check["hint"]:
                console.line(f"       {check['hint']}")
        console.line()
        console.line(
            "Doctor: all required checks passed."
            if ok
            else "Doctor: one or more required checks failed."
        )
    return EXIT_OK if ok else EXIT_GENERIC


def _yes_no(value: bool) -> str:
    return "yes" if value else "no"


def _show_config(cfg: Config, console: Console) -> int:
    if console.json_mode:
        console.emit_json({"path": str(cfg.path), "config": _config_dict(cfg)})
    else:
        console.write(f"# {cfg.path}\n")
        console.write(cfg.render())
    return EXIT_OK


def _list_models(cfg: Config, client: OllamaClient, console: Console) -> int:
    client.check_connection()
    models = client.list_models()
    rows = []
    for item in models:
        name = item.get("name") or item.get("model") or "?"
        details = item.get("details") or {}
        rows.append(
            {
                "name": name,
                "size": _format_size(item.get("size")),
                "parameters": details.get("parameter_size") or "?",
                "quantization": details.get("quantization_level") or "?",
                "default": name == cfg.model.name,
            }
        )
    if console.json_mode:
        console.emit_json({"default": cfg.model.name, "models": rows})
        return EXIT_OK
    if not rows:
        console.line("No local Ollama models found.")
        return EXIT_OK
    width = max(len(row["name"]) for row in rows)
    console.line(f"{'NAME'.ljust(width)}  {'SIZE':>8}  {'PARAMS':>7}  {'QUANT':<8}  DEFAULT")
    for row in rows:
        marker = "*" if row["default"] else ""
        console.line(
            f"{row['name'].ljust(width)}  {row['size']:>8}  "
            f"{row['parameters']:>7}  {row['quantization']:<8}  {marker}"
        )
    return EXIT_OK


def _set_model(cfg: Config, client: OllamaClient, console: Console, model: str) -> int:
    model = model.strip()
    client.check_connection()
    client.ensure_model(model)
    set_config_value(cfg.path, "model", "name", model)
    if console.json_mode:
        console.emit_json({"model": model, "path": str(cfg.path)})
    else:
        console.line(f"Default model set to {model}")
        console.line(f"Configuration: {cfg.path}")
    return EXIT_OK


def _payload(
    cfg: Config,
    mode: str,
    outcome: TurnOutcome,
    execution: ExecutionResult | None = None,
) -> dict:
    return {
        "answer": outcome.text or None,
        "model": cfg.model.name,
        "mode": mode,
        "source": outcome.source,
        "retrieval": [item.to_dict() for item in outcome.retrieval],
        "context": outcome.snapshot.to_dict() if outcome.snapshot is not None else None,
        "usage": {
            "prompt_tokens": outcome.prompt_tokens,
            "completion_tokens": outcome.completion_tokens,
        },
        "timing": {
            "total_ms": round(outcome.total_ms, 1),
            "ttft_ms": round(outcome.ttft_ms, 1) if outcome.ttft_ms is not None else None,
        },
        "execution": execution.to_dict() if execution is not None else None,
        "error": None,
    }


def _report_error(exc: MiraError, console: Console, args: argparse.Namespace) -> None:
    if args.json:
        console.emit_json(_error_payload(exc, getattr(args, "model", None)))
        return
    console.error(exc.render())


def _error_payload(exc: MiraError, model: str | None = None) -> dict:
    return {
        "answer": None,
        "model": model,
        "mode": None,
        "source": None,
        "retrieval": [],
        "context": None,
        "usage": {"prompt_tokens": None, "completion_tokens": None},
        "timing": {"total_ms": 0, "ttft_ms": None},
        "execution": None,
        "error": {
            "code": exc.exit_code,
            "message": exc.message,
            "hint": exc.hint,
        },
    }


def _config_dict(cfg: Config) -> dict:
    return {
        "model": {
            "name": cfg.model.name,
            "temperature": cfg.model.temperature,
            "num_predict": cfg.model.num_predict,
            "num_ctx": cfg.model.num_ctx,
            "keep_alive": cfg.model.keep_alive,
            "explain_temperature": cfg.model.explain_temperature,
            "explain_num_predict": cfg.model.explain_num_predict,
        },
        "ollama": {
            "host": cfg.ollama.host,
            "stream": cfg.ollama.stream,
            "timeout": cfg.ollama.timeout,
        },
        "behavior": {
            "default_mode": cfg.behavior.default_mode,
            "thinking": cfg.behavior.thinking,
            "context_detection": cfg.behavior.context_detection,
            "cheatsheet": cfg.behavior.cheatsheet,
            "direct_answers": cfg.behavior.direct_answers,
        },
        "conversation": {"max_messages": cfg.conversation.max_messages},
        "retrieval": {"max_results": cfg.retrieval.max_results},
        "execution": {
            "enabled": cfg.execution.enabled,
            "timeout": cfg.execution.timeout,
            "max_output": cfg.execution.max_output,
            "allow_destructive": cfg.execution.allow_destructive,
            "confirm_safe": cfg.execution.confirm_safe,
        },
    }


def _format_size(value: object) -> str:
    if not isinstance(value, (int, float)) or value <= 0:
        return "?"
    size = float(value)
    for unit in ("B", "KB", "MB", "GB", "TB"):
        if size < 1024 or unit == "TB":
            return f"{size:.1f} {unit}"
        size /= 1024
    return "?"

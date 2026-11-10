# AGENTS.md — MIRA

MIRA is a local, offline-first Linux CLI assistant backed by Ollama. It answers
one question at a time, optionally explains in depth, or holds a bounded
conversation. It never executes commands.

## Quick commands

```bash
python3 -m venv .venv && . .venv/bin/activate
pip install -e ".[dev]"
mira "How do I check disk space?"
mira --debug "How do I allow HTTP through firewalld?"
mira --explain "How does firewalld work?"
mira -converse
pytest
MIRA_INTEGRATION=1 pytest -m integration
python scripts/benchmark.py
```

`mira` must work from any directory after installation. Knowledge ships as
package data; `~/.config/mira/knowledge/*.md` overrides bundled entries.

## Architecture

| Module | Responsibility |
|---|---|
| `src/mira/cli.py` | argparse, orchestration, exit codes, mode dispatch |
| `src/mira/config.py` | TOML load/validate, XDG paths, atomic writes |
| `src/mira/context.py` | OS/shell/workspace/git/tool snapshot |
| `src/mira/retrieval.py` | knowledge parser, scoring, OS filter, fast path |
| `src/mira/prompt_builder.py` | system prompt, context/reference assembly, token budget |
| `src/mira/ollama_client.py` | `/api/chat`, `/api/tags`, `/api/show`, streaming, errors |
| `src/mira/conversation.py` | bounded history and REPL commands |
| `src/mira/output.py` | streaming, ANSI/TTY rules, JSON, debug-to-stderr |
| `src/mira/errors.py` | exception types mapped to exit codes |
| `scripts/benchmark.py` | live latency/throughput benchmark |
| `knowledge/*.md` | curated cheatsheets (also copied into the package) |

## Hard constraints

- Python 3.12+; **no runtime dependencies**. Use the standard library
  (`urllib`, `tomllib`, `http.server` in tests). `pytest` is dev-only.
- Never add LangChain/CrewAI/vector databases/embeddings. No cloud APIs.
- Never execute a generated command. No subprocess execution of user output.
- Never send environment variable values, SSH keys, git remotes, or absolute
  workspace paths to the model.
- No silent model downloads. No auto-installing packages or starting services.
- Streaming by default; `--json` is a single complete object; debug goes to
  stderr only.
- Thinking is disabled with `think: false` only when `/api/show` reports
  support. Otherwise omit the parameter. Never retry with thinking enabled.
- Do not claim a response is verified unless it came from a curated entry with
  `direct: true`.

## Knowledge entry format

One entry per `## Topic` section, with a strict metadata block:

```markdown
## Apache configuration
---
os: fedora
keywords: apache, httpd, config, configuration
aliases: apache config, httpd config
direct: true
---
Main configuration: `/etc/httpd/conf/httpd.conf`

Verify: `systemctl status httpd`
```

`os` accepts `any`, `linux`, or a distribution token such as `fedora`.
`direct: true` allows the deterministic fast path. Keep bodies short and put
the command or path first. Add a `Warning:` line for risky actions.

## Conventions

- Exit codes: 0 success, 1 generic, 2 usage/config, 3 Ollama unreachable,
  4 model missing, 130 interrupted.
- User-facing errors start with `MIRA:` and never include tracebacks unless
  `--debug`.
- Keep responses under ~100 words in one-shot mode; explain mode may be longer.
- Tests must not require Ollama unless marked `integration`.
- Prefer deterministic Python over LLM reasoning for environment facts,
  retrieval, and fast-path answers.
- Preserve comments when rewriting config; write atomically.

## Gotchas

- Fedora's Python may be externally managed. A venv is the recommended install.
- `gemma4:e4b-it-q4_K_M` is ~6.6 GB and may partially offload on a 6 GB GPU.
- `num_ctx = 4096` is deliberate; raise only after checking VRAM and latency.
- The local Python is 3.14; target remains >=3.12.

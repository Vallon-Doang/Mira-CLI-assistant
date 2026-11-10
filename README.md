# MIRA

**M**inimal **I**nference **R**esource **A**ssistant — a fast, local, offline-first
Linux command-line assistant powered by [Ollama](https://ollama.com/).

MIRA answers one question at a time, explains topics in more depth on request,
or holds a bounded conversation. It never executes commands. All inference runs
locally; no cloud API is used.

```text
$ mira where is apache config

Main configuration on Fedora: `/etc/httpd/conf/httpd.conf`

Additional configuration: `/etc/httpd/conf.d/*.conf`

Fedora's package and service are named `httpd`. Debian and Ubuntu use
`/etc/apache2/apache2.conf`.

(local cheatsheet)
```

## Features

- **One-shot answers** by default: one request, one response, no history.
- **Explain mode** for longer, step-by-step answers.
- **Conversation mode** with bounded history, `/clear`, `/help`, and `/exit`.
- **Fresh environment snapshot** for every query: distro, kernel, shell,
  workspace project type, Git branch, and available tools.
- **Deterministic local cheatsheets** with keyword/alias scoring and OS
  filtering; common questions can be answered without loading the model.
- **Thinking disabled** where the model and Ollama support it.
- **Streaming** output in the terminal; a single JSON object with `--json`.
- **Zero runtime dependencies**: Python standard library only.
- **Read-only**: MIRA may suggest commands, but never runs them.

## Requirements

- Linux (developed on Fedora 44; other distributions work, with Fedora-specific
  knowledge filtered by OS tag).
- Python **3.12+**.
- [Ollama](https://ollama.com/download) running locally.
- The default model:

  ```bash
  ollama pull gemma4:e4b-it-q4_K_M
  ```

  If that tag is not available on your Ollama installation, use any installed
  model with `--model`, or persist it with `--set-model`.

MIRA never downloads models or installs packages automatically.

## Installation

Fedora's system Python is externally managed, so a virtual environment is
recommended:

```bash
git clone <repository-url> mira
cd mira
python3 -m venv .venv
source .venv/bin/activate
pip install -e .
```

For development and tests:

```bash
pip install -e ".[dev]"
```

The `mira` console script is installed into the active environment. If you
install with `pip --user` outside a virtual environment, make sure
`~/.local/bin` is on your `PATH`.

Verify:

```bash
mira --version
mira --show-config
```

## Quick start

```bash
mira "Where is Apache's configuration file?"
mira how do I check my IP address
mira "How do I allow HTTP through firewalld?"
mira --explain "How does firewalld work?"
mira -converse "Help me configure Apache"
```

## Modes

### One-shot (default)

One question, one answer, no retained history. Responses are kept short and
practical; commands and paths come first.

### Explain

```bash
mira --explain "How does systemd work?"
mira -explain "How does systemd work?"
```

Allows a longer answer, examples, prerequisites, warnings, and troubleshooting
detail. Uses its own generation limits (`explain_temperature`,
`explain_num_predict`).

### Conversation

```bash
mira -converse
mira --converse "Help me configure Apache"
```

Inside the session:

| Command | Action |
|---|---|
| `/help` | Show available commands |
| `/clear` | Clear conversation history |
| `/exit`, `/quit`, `exit` | Leave the session |
| `Ctrl+C` | Cancel the current generation; stay in the session |
| `Ctrl+D` | Exit |

History keeps the last `conversation.max_messages` individual messages, dropping
the oldest turns first. The environment snapshot is refreshed and rebuilt on
every turn. `--json` cannot be combined with `--converse`.

`--explain --converse` starts a conversation that uses explain-mode generation
limits.

## CLI reference

```text
mira [options] [question ...]
```

| Option | Meaning |
|---|---|
| `-explain`, `--explain` | Longer, step-by-step answer |
| `-converse`, `--converse` | Interactive session |
| `--model MODEL` | Override the model for this invocation |
| `--list-models` | List installed Ollama models |
| `--set-model MODEL` | Validate and persist a new default model |
| `--show-config` | Print the effective configuration and path |
| `--debug` | Timing, context, retrieval, and token diagnostics on stderr |
| `--no-context` | Disable environment detection |
| `--no-cheatsheet` | Disable local knowledge retrieval |
| `--json` | Emit one complete JSON object |
| `--version` | Print the version |
| `--help` | Print help |

Unquoted multiword questions work: `mira how do I check disk space`. Quote the
question if it contains something that looks like a flag.

If no question is given and stdin is piped, MIRA reads the question from stdin:

```bash
echo "How do I check disk space?" | mira
```

## Configuration

Configuration lives at:

```text
~/.config/mira/config.toml
```

`XDG_CONFIG_HOME` is honoured. `MIRA_CONFIG` can point to a different file.
The file is created with defaults on first run. CLI flags override file values.

```toml
[model]
name = "gemma4:e4b-it-q4_K_M"
temperature = 0.2
num_predict = 256
num_ctx = 4096
keep_alive = "5m"
explain_temperature = 0.3
explain_num_predict = 768

[ollama]
host = "http://127.0.0.1:11434"
stream = true
timeout = 120

[behavior]
default_mode = "oneshot"     # oneshot | explain | converse
thinking = false
context_detection = true
cheatsheet = true
direct_answers = true

[conversation]
max_messages = 12

[retrieval]
max_results = 3
```

Invalid values produce a clear error and exit code 2. `--set-model` validates
the model against `/api/tags` before writing atomically, preserving comments.

A commented example is available in [`config.example.toml`](config.example.toml).

## Environment detection

Before every query, Python collects a small snapshot:

```text
OS: Fedora Linux 44
Kernel: 7.2.11-200.fc44.x86_64
Architecture: x86_64
Shell: bash
Workspace: Python project (mira)
Project files: pyproject.toml
Git branch: main
Available tools: git, python3, dnf, systemctl, firewall-cmd, nvidia-smi
```

- OS facts come from `/etc/os-release` and `os.uname()`.
- The shell is taken from `$SHELL`, then the parent process, then the passwd
  entry.
- Project type is detected from markers such as `pyproject.toml`,
  `composer.json` + `artisan`, `package.json`, `Cargo.toml`, and
  `project.godot`, in the current directory and up to three parents.
- Git branch and dirty state use short, read-only `git` calls with a 1-second
  timeout.
- Tool presence uses `shutil.which()` only; versions are not queried.
- Static facts are cached per process; workspace data is refreshed each query.

**Privacy:** MIRA does not collect environment variable values, API keys, SSH
keys, passwords, file contents, Git remote URLs, or personal documents. Only the
workspace directory *name* is sent, never its absolute path. `--no-context`
removes the snapshot entirely.

## Local knowledge base

Curated Markdown files live in `knowledge/` and are shipped as package data.
User overrides go in:

```text
~/.config/mira/knowledge/*.md
```

User entries with the same topic replace bundled ones. Retrieval is
deterministic: keyword hits (+2), alias phrases (+3), topic-word overlap (+1),
with the entry's first keyword acting as its subject. Results are filtered by
OS (`any`, `linux`, or a distribution token such as `fedora`) and limited to
`retrieval.max_results` entries (default 3). No embeddings or vector database
are used.

Entry format:

```markdown
## Apache configuration file
---
os: fedora
keywords: apache, httpd, config, configuration, path, file
aliases: apache config, apache configuration, httpd config
direct: true
---
Main configuration on Fedora: `/etc/httpd/conf/httpd.conf`

Verify: `sudo apachectl configtest`
```

`direct: true` allows the fast path. MIRA answers without the model only when
the match is unique, the query is short (≤ 20 words), the entry is marked
direct, and one-shot mode is active. Such answers are labelled
`(local cheatsheet)`. Ties always fall back to the model.

## JSON output

```bash
mira --json "How do I check disk space?"
```

```json
{
  "answer": "```bash\ndf -h\n```\n...",
  "model": "gemma4:e4b-it-q4_K_M",
  "mode": "oneshot",
  "source": "cheatsheet",
  "retrieval": [
    {"topic": "Check available disk space", "file": "filesystems.md", "score": 13.0}
  ],
  "context": {
    "os": "Fedora Linux",
    "os_id": "fedora",
    "os_version": "44",
    "kernel": "7.2.11-200.fc44.x86_64",
    "arch": "x86_64",
    "shell": "bash",
    "workspace": "Python project (mira)",
    "cwd_name": "mira",
    "project_types": ["Python"],
    "project_files": ["pyproject.toml"],
    "git_repo": true,
    "git_branch": "main",
    "git_dirty": false,
    "tools": ["git", "python3", "dnf", "systemctl"]
  },
  "usage": {"prompt_tokens": 334, "completion_tokens": 2},
  "timing": {"total_ms": 1485.2, "ttft_ms": 620.1},
  "error": null
}
```

`--json` always emits exactly one object and never streams. Debug output goes to
stderr, so stdout remains valid JSON. On failure, `answer` is `null` and `error`
contains `code`, `message`, and `hint`.

## Exit codes

| Code | Meaning |
|---|---|
| `0` | Success |
| `1` | Generic failure or empty model response |
| `2` | Usage or configuration error |
| `3` | Ollama unreachable or not running |
| `4` | Requested model is not installed |
| `130` | Interrupted with `Ctrl+C` |

User-facing errors start with `MIRA:` and never print a traceback unless
`--debug` is enabled.

## Testing

The default suite is offline and uses a fake Ollama HTTP server:

```bash
pytest
```

Live acceptance tests are opt-in and require the configured model:

```bash
MIRA_INTEGRATION=1 pytest -m integration
```

This runs the ten acceptance questions twice: once through the deterministic
fast path and once through the full Ollama pipeline with retrieval disabled.

## Benchmark

```bash
python scripts/benchmark.py
python scripts/benchmark.py --json
python scripts/benchmark.py --questions my-questions.txt
```

It reports time to first token, total time, tokens per second (from Ollama's
`eval_count`/`eval_duration`), prompt and completion token counts, and whether
retrieval was used. Unavailable metrics are shown as `n/a`. See
[`docs/benchmarks.md`](docs/benchmarks.md) for measured results and caveats.

## Troubleshooting

See [`docs/troubleshooting.md`](docs/troubleshooting.md) for Ollama, model,
VRAM, configuration, and installation issues.

## Architecture

```text
src/mira/
├── cli.py             # argument parsing and orchestration
├── config.py          # TOML loading, validation, atomic updates
├── context.py         # OS/shell/workspace/git/tool snapshot
├── retrieval.py       # knowledge parsing, scoring, fast path
├── prompt_builder.py  # system prompt and token budget
├── ollama_client.py   # /api/chat, /api/tags, /api/show
├── conversation.py    # bounded history and REPL
├── output.py          # streaming, ANSI, JSON, debug
├── errors.py          # exception types and exit codes
└── knowledge/         # packaged cheatsheets
```

Design rules: standard library only, deterministic Python for facts and
retrieval, minimal prompts, no execution engine, and no agent framework.

## Limitations

- MIRA is a **read-only assistant**. It never executes suggested commands.
- Thinking controls depend on the model and Ollama version. When unsupported,
  MIRA omits the parameter rather than pretending reasoning is disabled.
- `num_ctx = 4096` is deliberate for a 6 GB GPU. Very long questions or
  conversations may have older history or lower-ranked reference entries
  dropped; `--debug` reports this.
- `gemma4:e4b-it-q4_K_M` is ~6.6 GB and may partially offload to CPU on a 6 GB
  GPU. First response after a cold load is noticeably slower.
- Retrieval is keyword-based, not semantic. Unusual phrasing may miss a
  cheatsheet entry and fall back to the model.
- No persistent memory, scheduled tasks, voice interface, or desktop
  integration.

## Roadmap (not implemented)

Read-only tools, explicit command execution with confirmation and risk
classification, and longer-term assistant features are deliberately out of
scope for this release. No autonomous tool calling exists.

## License

MIT. See [`LICENSE`](LICENSE).

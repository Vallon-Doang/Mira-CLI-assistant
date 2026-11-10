# MIRA

> Just another vibe coded project.

**M**inimal **I**nference **R**esource **A**ssistant — a fast, local, offline-first
Linux command-line assistant powered by [Ollama](https://ollama.com/).

MIRA answers one question at a time, explains topics in more depth on request,
or holds a bounded conversation. Command execution is opt-in and guarded by a
deterministic risk policy. All inference runs locally; no cloud API is used.

```text
$ mira where is apache config

Main configuration on Fedora: `/etc/httpd/conf/httpd.conf`

Additional configuration: `/etc/httpd/conf.d/*.conf`

Fedora's package and service are named `httpd`. Debian and Ubuntu use
`/etc/apache2/apache2.conf`.

(local cheatsheet)
```

## What, why, how, when

### What

MIRA is a small Linux assistant that runs against a local Ollama model. It has
three modes: one-shot answers, longer explanations, and a bounded conversation.
It can also use curated local cheatsheets for common questions, and with
`--execute` it can run a single command proposed by the model after a
deterministic risk check.

It is not a chatbot platform, not an agent framework, and not a cloud wrapper.

### Why

Cloud assistants are convenient, but they send the question, the context, and
sometimes the answer to someone else's computer. MIRA keeps inference local,
uses no API keys, and has no runtime dependencies. The deterministic parts —
environment detection, keyword retrieval, token budgeting, and command risk —
are ordinary Python so they are inspectable, testable, and predictable.

The project is deliberately small. It favours a clear prompt and a small set of
curated notes over a large retrieval pipeline. That makes it easy to run on a
laptop GPU and easy to audit.

### How

- Python 3.12+ with the standard library only.
- Talks to Ollama over its local HTTP API (`/api/chat`, `/api/tags`, `/api/show`).
- Builds a fresh environment snapshot for each question: distro, kernel, shell,
  workspace type, Git branch, and available tools.
- Retrieves up to three curated Markdown entries with deterministic keyword and
  alias scoring, filtered by OS.
- Builds a token-budgeted prompt and streams the response.
- In execution mode, extracts at most one `COMMAND:` line, classifies it as
  `safe`, `moderate`, or `destructive`, and follows the policy:
  safe runs automatically, moderate asks, destructive is refused unless
  explicitly allowed. Output is shown locally and never sent back to the model.
- Ships with offline tests, a fake Ollama server, a knowledge validator,
  `--doctor`, CI, and a clean wheel/sdist release script.

### When

Use MIRA when you want a quick Linux answer from a local model, when you are
offline, or when you do not want to send the question to a cloud service. It
fits paths, services, packages, Git basics, and the common Fedora questions
covered by the bundled cheatsheets. It also fits a local demo of how a small
LLM assistant can be built with the standard library.

Do not use it for unattended automation, multi-step agent loops, or running
risky commands without reading them first. The risk classifier is a guard
rail, not a sandbox.

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
- **Opt-in command execution** with deterministic risk classification, shell
  feature warnings, confirmation prompts, timeouts, and output limits.
- **`--doctor`** for local installation, Ollama, model, knowledge, GPU, and
  environment diagnostics.
- **Zero runtime dependencies**: Python standard library only.

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
mira --execute "How much disk space is free?"
mira --doctor
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

## Command execution

Execution is **off by default**. Enable it for one invocation with `--execute`,
or persistently with `[execution] enabled = true` in the config. MIRA never
executes commands from the fast-path cheatsheets; only a command proposed by the
model in the current response is considered.

```bash
mira --execute "How much disk space is free?"
mira --execute --yes "Create /tmp/mira-demo"
mira --execute --allow-destructive "Remove /tmp/mira-demo"
```

The model is instructed to propose at most one command:

```text
COMMAND: df -h
```

MIRA extracts it, removes the marker from the displayed answer, classifies it,
and then follows this policy:

| Risk | Examples | Default behaviour |
|---|---|---|
| `safe` | `df -h`, `git status`, `systemctl status sshd`, `journalctl -u ollama` | Runs automatically when execution is enabled |
| `moderate` | `systemctl restart sshd`, `dnf install`, `touch`, `curl` | Shows the command and asks for confirmation |
| `destructive` | `rm`, `dd`, `mkfs`, `chmod`, `systemctl stop`, `sudo ...` | Refused unless `--allow-destructive` is also given, then still confirmed |

`--yes` skips confirmation for `safe` and `moderate` commands. It does **not**
override the destructive guard; destructive commands need both
`--allow-destructive` and either an interactive confirmation or `--yes`.

Shell features such as pipes, redirection, command substitution, and globs are
detected. A command using them is run through `bash -lc`, labelled with the
detected features, and always requires confirmation; it never auto-runs. Command
substitution and elevated commands are treated as destructive.

Execution details:

- Commands run in the current directory with stdin set to `/dev/null`.
- Interactive programs and password prompts (including most `sudo` uses) are not
  supported; `sudo` is classified as destructive.
- Default timeout is 30 seconds and output is capped at 20,000 characters per
  stream. Both are configurable under `[execution]`.
- Command output is shown locally and is **never sent back to the model**.
- `--execute` disables streaming for that turn so the proposed command can be
  parsed and the answer cleaned before display.
- In a non-interactive context (piped output, `--json`, or no TTY), a command
  that needs confirmation is not executed and MIRA exits with code 1 unless
  `--yes` (and, for destructive commands, `--allow-destructive`) is supplied.
- A command's own non-zero exit code does not change MIRA's exit code; the exit
  code is reported in the output and in the JSON `execution` object.

`--json --execute` adds an `execution` object with `status`, `command`, `risk`,
`reason`, `shell`, `shell_features`, `executed`, `exit_code`, `stdout`,
`stderr`, `timed_out`, `truncated`, and `duration_ms`. A refusal or required
confirmation also populates the top-level `error` and exits with code 1.

## Diagnostics

```bash
mira --doctor
mira --doctor --json
```

`--doctor` checks Python, the config file, the Ollama binary and API, the
configured model, thinking support, knowledge entries, Git, GPU visibility,
environment detection, and whether execution is enabled. Required failures exit
with code 1; warnings do not. It never downloads models or changes config.

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
| `-execute`, `--execute` | Allow one model-proposed command to run under the risk policy |
| `--yes` | Skip confirmation for safe/moderate commands (destructive still needs `--allow-destructive`) |
| `--allow-destructive` | Permit destructive commands; still confirmed unless `--yes` |
| `--doctor` | Run local installation diagnostics |
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

[execution]
enabled = false
timeout = 30
max_output = 20000
allow_destructive = false
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

Validate the repository knowledge and its packaged copy with:

```bash
python scripts/validate_knowledge.py
```

The validator reports missing keywords, duplicate topics, invalid OS tokens,
oversized bodies, direct entries containing risky commands, and differences
between `knowledge/` and `src/mira/knowledge/`. Retrieval quality is covered by
`tests/test_retrieval_eval.py`.

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
  "execution": null,
  "error": null
}
```

With `--execute`, `execution` is an object:

```json
{
  "status": "executed",
  "command": "df -h",
  "risk": "safe",
  "reason": "read-only diagnostic command",
  "shell": false,
  "shell_features": [],
  "executed": true,
  "exit_code": 0,
  "stdout": "Filesystem ...",
  "stderr": "",
  "timed_out": false,
  "truncated": false,
  "duration_ms": 12.4,
  "message": null
}
```

`--json` always emits exactly one object and never streams. Debug output goes to
stderr, so stdout remains valid JSON. On failure, `answer` is `null` and `error`
contains `code`, `message`, and `hint`. A command that needs confirmation or is
refused is not executed; `execution.status` explains why and the process exits
with code 1.

## Exit codes

| Code | Meaning |
|---|---|
| `0` | Success |
| `1` | Generic failure, empty model response, or a proposed command that was refused/needs confirmation |
| `2` | Usage or configuration error |
| `3` | Ollama unreachable or not running |
| `4` | Requested model is not installed |
| `130` | Interrupted with `Ctrl+C` |

User-facing errors start with `MIRA:` and never print a traceback unless
`--debug` is enabled.

## Testing

The default suite is offline and uses a fake Ollama HTTP server:

```bash
python scripts/validate_knowledge.py
pytest
```

Live acceptance tests are opt-in and require the configured model:

```bash
MIRA_INTEGRATION=1 pytest -m integration
```

This runs the ten acceptance questions twice: once through the deterministic
fast path and once through the full Ollama pipeline with retrieval disabled.

Build a wheel and sdist, then smoke-test the wheel in a clean virtual
environment:

```bash
./scripts/release.sh
```

The script validates knowledge, runs the offline tests, builds both artifacts,
installs the wheel without runtime dependencies, and checks that the packaged
fast path still answers a disk-space question. CI runs the same offline checks
on Python 3.12, 3.13, and 3.14 (see `.github/workflows/ci.yml`).

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
├── execution.py       # command extraction, risk policy, safe execution
├── knowledge_validation.py # knowledge and packaged-copy checks
├── output.py          # streaming, ANSI, JSON, debug, execution display
├── errors.py          # exception types and exit codes
└── knowledge/         # packaged cheatsheets
```

Design rules: standard library only, deterministic Python for facts, retrieval,
and command risk, minimal prompts, explicit opt-in execution, and no agent
framework. Command output is never fed back into the model.

## Limitations

- Command execution is **opt-in** and limited to one model-proposed command per
  turn. It is not an autonomous agent and does not plan or chain commands.
- Risk classification is deterministic and conservative, not a sandbox. It can
  miss dangerous intent inside a command it considers moderate. Review every
  command before confirming, and do not use `--yes` casually.
- Interactive commands, password prompts, and most `sudo` workflows are not
  supported because stdin is `/dev/null`.
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

Longer-term assistant features are deliberately out of scope for this release.
There is no autonomous tool calling, multi-command planning, background
execution, or sandboxing. Command execution remains explicit and
confirmation-oriented.

## License

MIT. See [`LICENSE`](LICENSE).

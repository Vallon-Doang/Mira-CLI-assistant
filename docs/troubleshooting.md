# Troubleshooting MIRA

Run `mira --debug ...` for timing, context, retrieval, prompt-budget, and token
diagnostics. Debug output always goes to stderr, so it is safe with `--json`.

## `mira: command not found`

The console script is installed into the Python environment you used:

```bash
python3 -m venv .venv
source .venv/bin/activate
pip install -e .
which mira
```

For a `pip --user` install, add `~/.local/bin` to `PATH`.

## Fedora says the environment is externally managed

Fedora protects system Python. Use a virtual environment:

```bash
python3 -m venv .venv
source .venv/bin/activate
pip install -e ".[dev]"
```

Do not use `--break-system-packages` unless you understand the risk.

## Ollama is not installed

MIRA does not install it. Install Ollama from the official instructions, then:

```bash
ollama --version
```

## Ollama is not running

```bash
systemctl status ollama
sudo systemctl start ollama
```

Without systemd:

```bash
ollama serve
```

Check the API directly:

```bash
curl -s http://127.0.0.1:11434/api/version
```

If the connection is refused, MIRA exits with code 3.

## Ollama is on a different host or port

Edit `~/.config/mira/config.toml`:

```toml
[ollama]
host = "http://127.0.0.1:11434"
timeout = 120
```

Or point `MIRA_CONFIG` at another file. MIRA does not fall back to a cloud
service.

## Model is missing

```bash
mira --list-models
ollama pull gemma4:e4b-it-q4_K_M
```

Or select an installed model for one invocation:

```bash
mira --model qwen3:4b-instruct "How do I check disk space?"
```

Persist it after validation:

```bash
mira --set-model qwen3:4b-instruct
```

MIRA exits with code 4 when the selected model is not installed. It never
downloads a model silently.

## Model fails to load or runs out of memory

Symptoms: a 500 response, a long pause, or an Ollama "out of memory" message.

```bash
nvidia-smi
ollama ps
journalctl -u ollama -n 100 --no-pager
```

Options:

- Close GPU-heavy applications.
- Use a smaller model with `--model`.
- Lower `num_ctx` in the config (for example, `2048`).
- Lower `keep_alive` so the model unloads sooner.

A 6.58 GB model on a 6 GB GPU may partially offload to CPU. That is slower but
not necessarily an error.

## First response is slow

Ollama loads the model on first use. Later requests reuse it for `keep_alive`
(default `5m`). Check the load separately:

```bash
time curl -s http://127.0.0.1:11434/api/generate \
  -d '{"model":"gemma4:e4b-it-q4_K_M","prompt":"Say OK","stream":false}'
```

## Generation times out

Raise the timeout:

```toml
[ollama]
timeout = 300
```

Long explain-mode answers on CPU fallback can take a while. Prefer one-shot
mode for quick commands.

## Streaming is interrupted

`Ctrl+C` cancels the current generation. In one-shot mode MIRA exits with code
130; in conversation mode it stays in the session. Partial text already printed
is not saved to history.

## Configuration is malformed

MIRA reports the file path and the TOML error, then exits with code 2.

```bash
mira --show-config
```

If necessary, back up and regenerate:

```bash
mv ~/.config/mira/config.toml ~/.config/mira/config.toml.bak
mira --show-config
```

The new file contains commented defaults.

## Knowledge files are missing or ignored

Bundled files ship inside the package. User overrides live at:

```text
~/.config/mira/knowledge/*.md
```

Check retrieval with:

```bash
mira --debug "How do I allow HTTP through firewalld?"
```

A malformed entry is skipped; the reason appears in debug output. Verify that
the file starts entries with `## Topic`, followed by a `---` metadata block.
`--no-cheatsheet` disables retrieval entirely.

## A cheatsheet answer is wrong for my system

Entries are tagged `os: fedora`, `os: linux`, or `os: any`. Fedora-specific
paths are filtered on other distributions, but generic commands may still
differ. Override the topic in `~/.config/mira/knowledge/` or use
`--no-cheatsheet` to force the model.

## Git information is missing

```bash
git --version
```

MIRA only runs short, read-only `git` commands inside the detected repository.
If Git is absent or the command times out, the snapshot omits branch data.
Remotes and file contents are never collected.

## The current directory is inaccessible

MIRA catches the error and continues without workspace data. Change to a
readable directory, or use `--no-context`.

## JSON output looks wrong

- `--json` writes exactly one object to stdout.
- Debug and errors go to stderr.
- `--json` cannot be used with `--converse`.
- Pipe through a JSON parser to check:

  ```bash
  mira --json "How do I check disk space?" | python3 -m json.tool
  ```

## Answers contain thinking text

MIRA sends `think: false` only when `/api/show` reports thinking support. It
also ignores any `thinking` field in streamed responses. If a model emits
reasoning inside normal `content`, that is a model limitation, not a supported
control. Document it and switch models if it matters.

## Tests fail with connection errors

The default test suite is offline and uses a fake HTTP server. If you see
connection failures, run:

```bash
pytest -q
```

Live tests require explicit opt-in:

```bash
MIRA_INTEGRATION=1 pytest -m integration
```

## Still stuck

Collect:

```bash
mira --version
mira --show-config
mira --debug "your question" 2>debug.log
journalctl -u ollama -n 50 --no-pager
```

Do not paste API keys or private file contents into a report.

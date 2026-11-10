# Ollama

## Check Ollama status
---
os: linux
keywords: ollama, status, service, running, systemctl, active
aliases: ollama status, is ollama running, ollama service
direct: true
---
```bash
systemctl status ollama
```

Quick API check:

```bash
curl -s http://127.0.0.1:11434/api/version
```

## Start Ollama
---
os: linux
keywords: start, ollama, service, serve, systemctl, run
aliases: start ollama, ollama serve, run ollama
direct: true
---
```bash
sudo systemctl start ollama
```

For a foreground session without systemd:

```bash
ollama serve
```

## List installed models
---
os: linux
keywords: list, models, ollama, installed, local
aliases: ollama list, list models, installed models
direct: true
---
```bash
ollama list
```

MIRA shows the same list with `mira --list-models`.

## Run a model
---
os: linux
keywords: run, model, ollama, prompt, chat, use
aliases: ollama run, run model, use model
direct: true
---
```bash
ollama run MODEL
```

Type `/bye` to exit the interactive prompt.

## Download a model
---
os: linux
keywords: pull, download, model, ollama, install
aliases: ollama pull, download model, install model
direct: true
---
```bash
ollama pull MODEL
```

MIRA never downloads models automatically. Pull explicitly, then select it with `mira --model MODEL` or persist it with `mira --set-model MODEL`.

## Inspect an Ollama service failure
---
os: linux
keywords: ollama, service, fail, failure, failed, logs, systemctl, journalctl, inspect, debug
aliases: ollama service failure, ollama failed, debug ollama, ollama logs
direct: true
---
```bash
systemctl status ollama
journalctl -u ollama -n 100 --no-pager
```

Check whether the API is listening:

```bash
ss -tulpn | grep 11434
```

Common causes are a port conflict, insufficient memory, or a bad model file. Do not reinstall blindly; read the first error in the journal.

## Check the Ollama API
---
os: linux
keywords: ollama, api, check, endpoint, curl, tags, version
aliases: ollama api, test ollama, ollama endpoint
direct: true
---
```bash
curl -s http://127.0.0.1:11434/api/tags
curl -s http://127.0.0.1:11434/api/version
```

If the connection is refused, the service is not running.

## Show model details
---
os: linux
keywords: show, model, ollama, details, parameters, info
aliases: ollama show, model info, model details
direct: true
---
```bash
ollama show MODEL
```

## See which models are loaded
---
os: linux
keywords: ps, loaded, models, ollama, memory, running
aliases: ollama ps, loaded models, running models
direct: false
---
```bash
ollama ps
```

This shows loaded models and how long they will stay in memory.

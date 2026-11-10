# Python

## Create a virtual environment
---
os: linux
keywords: virtual, venv, environment, python, activate, isolate
aliases: virtual environment, python venv, create venv, activate venv
direct: true
---
```bash
python3 -m venv .venv
source .venv/bin/activate
```

Your prompt changes to show the environment. Deactivate with `deactivate`.

## Install a Python package
---
os: linux
keywords: install, pip, package, python, dependency, module
aliases: pip install, install python package, install module
direct: true
---
```bash
python3 -m pip install PACKAGE
```

Inside a virtual environment, `pip install PACKAGE` is equivalent.

## Install from requirements
---
os: linux
keywords: requirements, pip, install, dependencies, freeze, txt
aliases: install requirements, requirements.txt, pip freeze
direct: true
---
```bash
python3 -m pip install -r requirements.txt
```

Record the current environment:

```bash
python3 -m pip freeze > requirements.txt
```

## Check the Python version
---
os: linux
keywords: version, python, python3, interpreter, check
aliases: python version, check python, which python
direct: true
---
```bash
python3 --version
which python3
```

## Find Python files recursively
---
os: linux
keywords: find, python, files, recursive, recursively, py, search
aliases: find python files, recursive python files, search py files
direct: true
---
```bash
find . -name '*.py' -type f
```

If `ripgrep` is installed, this respects `.gitignore`:

```bash
rg --files -g '*.py'
```

## Run a Python module
---
os: linux
keywords: run, module, python, execute, script, package
aliases: run module, python -m, execute python
direct: true
---
```bash
python3 -m MODULE
```

For a script:

```bash
python3 script.py
```

## Understand a pyproject.toml project
---
os: linux
keywords: pyproject, project, layout, src, packaging, python
aliases: pyproject.toml, python project, project layout
direct: false
---
A modern Python project usually has `pyproject.toml` at its root. Source code often lives under `src/`, tests under `tests/`, and the package is installed in editable mode with:

```bash
python3 -m pip install -e .
```

## Install a CLI tool with pipx
---
os: linux
keywords: pipx, install, cli, tool, isolated, python
aliases: pipx install, install cli tool, isolated python tool
direct: true
---
```bash
pipx install PACKAGE
```

`pipx` keeps each tool in its own environment. Install it on Fedora with `sudo dnf install pipx`.

## Upgrade pip
---
os: linux
keywords: upgrade, pip, update, python, package manager
aliases: upgrade pip, update pip
direct: true
---
```bash
python3 -m pip install --upgrade pip
```

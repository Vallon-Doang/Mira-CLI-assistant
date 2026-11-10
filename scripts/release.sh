#!/usr/bin/env bash
# Build a wheel and sdist, then smoke-test the wheel in a clean venv.
set -euo pipefail

ROOT="$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)"
cd "$ROOT"

if ! python3 -c "import build" >/dev/null 2>&1; then
    echo "MIRA: the 'build' package is required. Install it with:" >&2
    echo "  python3 -m pip install build" >&2
    exit 2
fi

python3 scripts/validate_knowledge.py
pytest -q

rm -rf dist build
python3 -m build

TMPDIR="$(mktemp -d "${TMPDIR:-/tmp}/mira-release.XXXXXX")"
trap 'rm -rf "$TMPDIR"' EXIT
python3 -m venv "$TMPDIR/venv"
"$TMPDIR/venv/bin/python" -m pip install --quiet --no-deps dist/*.whl

VERSION="$("$TMPDIR/venv/bin/mira" --version)"
echo "Installed: $VERSION"
"$TMPDIR/venv/bin/mira" "How do I check available disk space?" >"$TMPDIR/smoke.txt"
grep -q "df -h" "$TMPDIR/smoke.txt"
echo "Smoke test: fast path answered from packaged knowledge"
echo "Artifacts:"
ls -1 dist

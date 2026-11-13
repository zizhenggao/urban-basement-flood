#!/usr/bin/env bash
# One-time setup for macOS and Linux. Safe to run again.
#   ./setup.sh
set -euo pipefail
cd "$(dirname "$0")"

MODEL="qwen2.5:3b"

fail() { echo "ERROR: $1" >&2; exit 1; }

echo "1/4 Checking the tools"
PYTHON=""
for candidate in python3.12 python3.11 python3.10 python3; do
  if command -v "$candidate" >/dev/null 2>&1 && "$candidate" -c 'import sys; sys.exit(sys.version_info < (3, 10))'; then
    PYTHON="$candidate"; break
  fi
done
[ -n "$PYTHON" ] || fail "Python 3.10 or newer is needed. Install it from https://www.python.org/downloads/"
command -v node >/dev/null 2>&1 || fail "Node.js 18 or newer is needed. Install it from https://nodejs.org/"
node -e 'process.exit(Number(process.versions.node.split(".")[0]) < 18)' || fail "Node.js 18 or newer is needed (found $(node --version))."
command -v ollama >/dev/null 2>&1 || fail "Ollama is needed. Install it from https://ollama.com/download and run this script again."
[ -d "policy context" ] || fail "The folder 'policy context' is missing. Run: git pull"
echo "    python: $($PYTHON --version), node: $(node --version), ollama: found"

echo "2/4 Python packages (first time takes a few minutes)"
[ -d .venv ] || "$PYTHON" -m venv .venv
.venv/bin/python -m pip install --quiet --upgrade pip
.venv/bin/python -m pip install --quiet -r requirements.txt

echo "3/4 Local model $MODEL (about 2 GB the first time)"
if ! ollama list >/dev/null 2>&1; then
  echo "    Ollama is not running. Starting it in the background for the download."
  (ollama serve >/dev/null 2>&1 &)
  for _ in $(seq 1 20); do ollama list >/dev/null 2>&1 && break; sleep 1; done
fi
ollama list >/dev/null 2>&1 || fail "Ollama did not start. Open a terminal, run 'ollama serve', then run this script again."
ollama pull "$MODEL"

echo "4/4 Web app packages"
(cd web && npm install --no-audit --no-fund --loglevel=error)

cat <<DONE

Setup finished. Start the app in three terminals, from this folder:

  1) ollama serve                (skip if Ollama is already running)
  2) .venv/bin/python -m uvicorn api.main:app --reload
  3) cd web && npm run dev

Then open http://localhost:5173
DONE

#!/usr/bin/env bash
# activate.sh — quick launcher for project virtual environment (Linux/macOS)
# Usage: ./activate.sh

set -euo pipefail

# 1) Activate local virtual environment
# Assumes .venv is in the repository root (next to this script)
REPO_DIR="$(cd "$(dirname "$0")" && pwd)"
VENV_ACTIVATE="$REPO_DIR/.venv/bin/activate"

if [[ -f "$VENV_ACTIVATE" ]]; then
  # shellcheck disable=SC1090
  source "$VENV_ACTIVATE"
else
  echo "❌ Virtual environment not found. Run 'python3.11 -m poetry install' first."
  exit 1
fi

# 2) Try to locate Poetry dynamically (avoid PATH duplicates)
# Common Poetry locations on Unix-like systems
POETRY_CANDIDATES=(
  "$HOME/.local/bin"
  "$HOME/.poetry/bin"
  "/usr/local/bin"
  "/opt/homebrew/bin"        # Apple Silicon Homebrew
  "/usr/bin"
)

poetry_found=false
for path in "${POETRY_CANDIDATES[@]}"; do
  exe="$path/poetry"
  if [[ -x "$exe" ]]; then
    case ":$PATH:" in
      *":$path:"*) : ;;      # already in PATH
      *) export PATH="$path:$PATH" ;;
    esac
    poetry_found=true
    echo "✅ Poetry detected at: $path"
    poetry --version || true
    break
  fi
done

if [[ "$poetry_found" == false ]]; then
  echo "⚠️ Poetry not found on this system."
  echo "   → Install: https://python-poetry.org/docs/#installation"
fi

echo "💡 Virtual environment ready."

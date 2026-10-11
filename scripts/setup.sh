#!/usr/bin/env bash
set -euo pipefail
cd "$(dirname "$0")/.."
runtime="${OPENJUTSU_DATA_DIR:-$HOME/.local/share/openjutsu}"
mkdir -p "$runtime"
runner="${OPENJUTSU_UV:-uv}"
if ! command -v "$runner" >/dev/null; then
  printf 'Install uv 0.13.0 first: https://docs.astral.sh/uv/getting-started/installation/\n' >&2
  exit 1
fi
UV_PROJECT_ENVIRONMENT="$runtime/api-venv" "$runner" sync --frozen --extra dev
"$runner" venv --python 3.12 --allow-existing "$runtime/venv"
"$runner" pip install --python "$runtime/venv/bin/python" --extra-index-url https://download.pytorch.org/whl/cu128 --index-strategy unsafe-best-match -r scripts/requirements-cuda.lock
"$runner" pip install --python "$runtime/venv/bin/python" --no-deps -e .
printf '\nBackend: %s\nModel Python: %s\n' "$runtime/api-venv/bin/openjutsu" "$runtime/venv/bin/python"
printf 'Model downloads are explicit: see docs/setup/models.md.\n'

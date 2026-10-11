#!/usr/bin/env bash
set -euo pipefail
cd "$(dirname "$0")/.."
runtime="${OPENJUTSU_DATA_DIR:-$HOME/.local/share/openjutsu}"
export OPENJUTSU_DATA_DIR="$runtime"
export OPENJUTSU_MODEL_DIR="${OPENJUTSU_MODEL_DIR:-$runtime/models}"
export OPENJUTSU_ML_PYTHON="${OPENJUTSU_ML_PYTHON:-$runtime/venv/bin/python}"
exec "$runtime/api-venv/bin/openjutsu" serve "$@"

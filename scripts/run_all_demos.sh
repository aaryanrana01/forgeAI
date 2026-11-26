#!/usr/bin/env bash
# One command to produce ALL committed evidence on a Mac/Linux machine with Ollama.
# Usage: bash scripts/run_all_demos.sh            (default model qwen2.5:7b-instruct)
#        FORGE_MODEL=qwen2.5:3b-instruct bash scripts/run_all_demos.sh   (faster, 8 GB RAM machines)
set -euo pipefail
cd "$(dirname "$0")/.."
MODEL="${FORGE_MODEL:-qwen2.5:7b-instruct}"
export FORGE_MODEL="$MODEL"

if ! command -v ollama >/dev/null; then
  echo "Ollama is not installed. Install it from https://ollama.com/download (or: brew install ollama)"; exit 1
fi
ollama list >/dev/null 2>&1 || { echo "Start the Ollama app first (or run: ollama serve)"; exit 1; }
ollama pull "$MODEL"
[ -n "${FORGE_JUDGE_MODEL:-}" ] && ollama pull "$FORGE_JUDGE_MODEL"
[ -n "${FORGE_EMBED_MODEL:-}" ] && ollama pull "$FORGE_EMBED_MODEL"

PY="${PY:-python3}"
$PY -m forgeai doctor
$PY -m pytest -q
start=$(date +%s)
$PY -m forgeai demo hr        2>&1 | tee runs/hr_policy.log
$PY -m forgeai demo spares    2>&1 | tee runs/ship_spares.log
$PY -m forgeai regress --old-run runs/hr_policy --new-docs demos/hr_policy/docs_v2 --out runs/hr_regression \
    --candidates 1 2>&1 | tee runs/hr_regression.log
$PY -m forgeai compare --run runs/hr_policy --definition baseline/hr_human_agent.json 2>&1 | tee runs/hr_compare.log
echo "Done in $(( ($(date +%s) - start) / 60 )) minutes. Evidence is in runs/ - commit the whole folder."

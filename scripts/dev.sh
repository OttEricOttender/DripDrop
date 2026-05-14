#!/usr/bin/env bash
# Quick dev helper for HydroCalc. Run from the repo root.
#
# Usage:
#   scripts/dev.sh test           — run the pytest suite
#   scripts/dev.sh api            — boot the FastAPI backend on port 8000
#   scripts/dev.sh lint           — run ruff + black --check + mypy
#   scripts/dev.sh format         — run ruff --fix + black
#   scripts/dev.sh worked-example — POST the worked example to the live API
#   scripts/dev.sh docker         — docker compose up the full stack
#
# Designed so Claude Code (and humans) can run common tasks without
# remembering the PYTHONPATH/uvicorn invocation each time.

set -euo pipefail

REPO_ROOT="$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)"
cd "$REPO_ROOT"

cmd="${1:-help}"

case "$cmd" in
  test)
    PYTHONPATH=. python -m pytest tests/ -v
    ;;
  api)
    PYTHONPATH=. python -m uvicorn backend.main:app --reload --host 0.0.0.0 --port 8000
    ;;
  lint)
    ruff check backend tests
    black --check backend tests
    mypy backend
    ;;
  format)
    ruff check --fix backend tests
    black backend tests
    ;;
  worked-example)
    curl -sS -X POST http://localhost:8000/api/hommik/calculate \
      -H "Content-Type: application/json" \
      -d '{
        "A_km2": 100.0,
        "p_percent": 10.0,
        "q_bar_k_l_per_s_km2": 7.0,
        "q95_l_per_s_km2": 2.0,
        "landcover": {
          "A_ms": 10.0, "A_r": 5.0, "A_km": 15.0,
          "B": 30.0, "C": 40.0,
          "maaparandus": 20.0,
          "a_wet_mineral_plus_akm": 20.0
        }
      }' | python -m json.tool
    ;;
  docker)
    docker compose up
    ;;
  help|*)
    grep -E '^#   ' "${BASH_SOURCE[0]}" | sed 's/^# *//'
    ;;
esac

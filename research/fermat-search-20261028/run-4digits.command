#!/usr/bin/env bash
set -euo pipefail
task_source="$(cd "$(dirname "$0")" && pwd)"
"$task_source/run.command" --min 1000 --max 9999 --min-power 3 --max-power 999 \
  --output "$task_source/results-1000-9999-p3-999.csv" "$@"
if [[ $# == 0 && -t 0 ]]; then
  read -r -p "Нажмите Enter, чтобы закрыть окно... " task_answer
fi

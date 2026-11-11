#!/usr/bin/env bash
set -euo pipefail
task_source="$(cd "$(dirname "$0")" && pwd)"
task_root="$(cd "$task_source/../.." && pwd)"
task_binary="$task_root/.build/fermat-search-20261028/fermat-search"
if [[ ! -x "$task_binary" ]]; then
  bash "$task_source/build.sh"
fi
"$task_binary" --threads 4 --output "$task_source/results-100-999-p3-999.csv" "$@"
if [[ $# == 0 && -t 0 ]]; then
  read -r -p "Нажмите Enter, чтобы закрыть окно... " task_answer
fi

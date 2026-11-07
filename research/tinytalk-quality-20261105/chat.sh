#!/bin/bash
set -euo pipefail
project_dir="$(cd -- "$(dirname -- "${BASH_SOURCE[0]}")/../.." && pwd)"
if [[ ! -f "$project_dir/.build/tinytalk-quality-20261105/final/model/model.safetensors" ]]; then
  printf '%s\n' 'Итоговая модель ещё не выбрана; обучение и независимые проверки продолжаются.' >&2
  exit 1
fi
exec "$project_dir/.build/squeal-chat-20261105/venv/bin/python" \
  "$project_dir/research/tinytalk-quality-20261105/local_chat.py" --profile tinytalk \
  --model-dir "$project_dir/.build/tinytalk-quality-20261105/final/model" \
  --packed-q4 "$project_dir/.build/tinytalk-quality-20261105/final/model.ttq4" \
  --context 128 --temperature 0 --max-new-tokens 40 --fp16-kv "$@"

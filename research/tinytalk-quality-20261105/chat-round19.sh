#!/bin/bash
set -euo pipefail
project_dir="$(cd -- "$(dirname -- "${BASH_SOURCE[0]}")/../.." && pwd)"
printf '%s\n' 'Эксперимент round19: уровень качества не достигнут; ошибки разговора сохраняются.' >&2
exec "$project_dir/.build/squeal-chat-20261105/venv/bin/python" \
  "$project_dir/research/tinytalk-quality-20261105/local_chat.py" --profile tinytalk \
  --model-dir "$project_dir/.build/tinytalk-quality-20261105/server-results/round19/typed/best" \
  --packed-q4 "$project_dir/.build/tinytalk-quality-20261105/server-results/round19/typed/model.ttq4" \
  --context 128 --temperature 0 --max-new-tokens 40 --threads 4 --fp16-kv "$@"

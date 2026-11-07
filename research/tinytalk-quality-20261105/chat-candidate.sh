#!/bin/bash
set -euo pipefail
project_dir="$(cd -- "$(dirname -- "${BASH_SOURCE[0]}")/../.." && pwd)"
printf '%s\n' 'Экспериментальный прототип: заданный уровень качества пока не достигнут.' >&2
exec "$project_dir/.build/squeal-chat-20261105/venv/bin/python" \
  "$project_dir/research/tinytalk-quality-20261105/local_chat.py" --profile tinytalk \
  --model-dir "$project_dir/.build/tinytalk-quality-20261105/candidate-round16/model" \
  --packed-q4 "$project_dir/.build/tinytalk-quality-20261105/candidate-round16/model.ttq4" \
  --context 128 --temperature 0 --max-new-tokens 40 --fp16-kv "$@"

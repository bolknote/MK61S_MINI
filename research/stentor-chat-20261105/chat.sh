#!/bin/bash
set -euo pipefail
project_dir="$(cd -- "$(dirname -- "${BASH_SOURCE[0]}")/../.." && pwd)"
exec "$project_dir/.build/squeal-chat-20261105/venv/bin/python" \
  "$project_dir/research/squeal-chat-20261105/chat.py" --profile stentor "$@"

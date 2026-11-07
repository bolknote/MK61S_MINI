#!/bin/bash
set -euo pipefail
project_dir="$(cd -- "$(dirname -- "${BASH_SOURCE[0]}")/../.." && pwd)"
exec bash "$project_dir/research/tinytalk-chat-20261105/chat.sh" \
  --model-dir "$project_dir/.build/tinytalk-chat-20261105/surgery/selected" \
  --temperature 0 "$@"

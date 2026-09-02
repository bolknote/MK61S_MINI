#!/usr/bin/env bash
set -euo pipefail

root="$(cd "$(dirname "$0")/.." && pwd)"
PYTHONPATH="$root/tests${PYTHONPATH:+:$PYTHONPATH}" \
  python3 "$root/tests/check_stack_usage_self_test.py"
PYTHONPATH="$root/tests${PYTHONPATH:+:$PYTHONPATH}" \
  python3 "$root/tests/analyze_stack_usage_self_test.py"

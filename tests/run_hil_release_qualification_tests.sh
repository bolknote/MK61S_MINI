#!/usr/bin/env bash
set -euo pipefail

root="$(cd "$(dirname "$0")/.." && pwd)"
PYTHONPATH="$root/tests${PYTHONPATH:+:$PYTHONPATH}" \
  python3 "$root/tests/hil_release_qualification_self_test.py"

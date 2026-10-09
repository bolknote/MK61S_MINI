#!/usr/bin/env bash
set -euo pipefail

root="$(cd "$(dirname "$0")/.." && pwd)"
PYTHONPATH="$root/tests${PYTHONPATH:+:$PYTHONPATH}" \
  python3 "$root/tests/hil_release_qualification_self_test.py"

python3 "$root/tests/hil_multi_device_identity_self_test.py"

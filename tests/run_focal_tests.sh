#!/usr/bin/env bash
set -euo pipefail
root="$(cd "$(dirname "$0")/.." && pwd)"
bash "$root/tests/run_focal_next_tests.sh"
bash "$root/tests/run_focal_compat_tests.sh"

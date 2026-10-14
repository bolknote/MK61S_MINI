#!/usr/bin/env bash
set -euo pipefail
root="$(cd "$(dirname "$0")/../.." && pwd)"
work="$(mktemp -d "${TMPDIR:-/tmp}/mk61-vm-scan.XXXXXX")"
trap 'rm -rf "$work"' EXIT
clang++ -std=c++17 -O1 -Wall -Wextra -Werror \
  -fsanitize=address,undefined -fno-omit-frame-pointer \
  "$root/tests/experimental/vm_scan_self_test.cpp" -o "$work/check"
"$work/check"

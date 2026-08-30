#!/usr/bin/env bash
set -euo pipefail

repo_root="$(cd "$(dirname "$0")/.." && pwd)"
build_dir="${TMPDIR:-/tmp}/mk61-rtc-backup-layout-tests"
mkdir -p "$build_dir"

"${CXX:-c++}" -std=c++17 -Wall -Wextra -Werror -pedantic \
  -I"$repo_root/code" \
  "$repo_root/tests/rtc_backup_layout_self_test.cpp" \
  -o "$build_dir/rtc_backup_layout_self_test"

"$build_dir/rtc_backup_layout_self_test"
echo "rtc backup layout tests: OK"

#!/usr/bin/env bash
set -euo pipefail

root="$(cd "$(dirname "$0")/.." && pwd)"
work="$(mktemp -d)"
trap 'rm -rf "$work"' EXIT

clang++ -std=c++17 -Wall -Wextra -Werror \
  -I"$root/code" \
  "$root/code/idle_sleep.cpp" \
  "$root/tests/idle_sleep_policy_self_test.cpp" \
  -o "$work/idle_sleep_policy_self_test"

"$work/idle_sleep_policy_self_test"

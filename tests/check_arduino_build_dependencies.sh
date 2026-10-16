#!/usr/bin/env bash
set -euo pipefail

root="$(cd "$(dirname "$0")/.." && pwd)"
arduino_cli="${MK61_ARDUINO_CLI:-arduino-cli}"
contract="$root/tools/release_contract.py"

fail() {
  printf 'Arduino compatibility dependencies: %s\n' "$1" >&2
  exit 2
}

command -v "$arduino_cli" >/dev/null 2>&1 ||
  fail "arduino-cli is not installed: $arduino_cli"
command -v python3 >/dev/null 2>&1 || fail 'python3 is required'
command -v c++ >/dev/null 2>&1 || fail 'a host C++17 compiler is required'
python3 "$contract" validate >/dev/null || fail 'release contract is invalid'
expected_cli="$(python3 "$contract" toolchain --field arduino_cli)"
expected_core="$(python3 "$contract" toolchain --field stm32_core)"

cli_version="$("$arduino_cli" version 2>/dev/null || true)"
[[ "$cli_version" =~ Version:[[:space:]]+([^[:space:]]+) ]] &&
  [[ "${BASH_REMATCH[1]}" == "$expected_cli" ]] ||
  fail "arduino-cli $expected_cli is required"
core_version="$("$arduino_cli" core list |
  awk '$1 == "STMicroelectronics:stm32" { print $2 }')"
[[ "$core_version" == "$expected_core" ]] ||
  fail "STM32 Core $expected_core is required"

printf 'Arduino compatibility dependencies: OK\n'

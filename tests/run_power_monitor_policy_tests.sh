#!/usr/bin/env bash
set -euo pipefail

root="$(cd "$(dirname "$0")/.." && pwd)"
work="$(mktemp -d)"
trap 'rm -rf "$work"' EXIT

clang++ -std=c++17 -Wall -Wextra -Werror \
  -I"$root/code" \
  "$root/tests/power_monitor_policy_self_test.cpp" \
  -o "$work/power_monitor_policy_self_test"

"$work/power_monitor_policy_self_test"

# Architectural gates: the last-moment NOR checks and the host-facing MSC
# gate must not disappear in a later refactor.
grep -q 'Operation::NOR_PROGRAM' "$root/code/spi_nor_flash.cpp"
grep -q 'Operation::NOR_ERASE' "$root/code/spi_nor_flash.cpp"
grep -q 'Operation::MSC_WRITE' "$root/code/usb_mass_storage.cpp"
grep -q 'PWR_PVD_MODE_IT_RISING_FALLING' "$root/code/power_monitor.cpp"

if grep -Eq 'Serial|virtual_fat|program_store|SpiNorFlash' \
    "$root/code/power_monitor.cpp"; then
  echo 'PVD module must not call terminal, filesystem, or NOR APIs' >&2
  exit 1
fi

printf 'power_monitor_policy_source_gates: ok\n'

#!/usr/bin/env bash
set -euo pipefail
root="$(cd "$(dirname "$0")/.." && pwd)"
work="$(mktemp -d "${TMPDIR:-/tmp}/mk61-workspace-vm-default.XXXXXX")"
trap 'rm -rf "$work"' EXIT
sanitizers=()
if [[ "${MK61_TEST_SANITIZERS:-0}" == 1 ]]; then sanitizers=(-fsanitize=address,undefined -fno-omit-frame-pointer); fi
for policy in f411 f401 explicit-off no-ram; do
  flags=(-DSTM32F411xE)
  case "$policy" in
    f401) flags=(-DSTM32F401xC) ;;
    explicit-off) flags+=(-DMK61_VM_FILE_CACHE=0) ;;
    no-ram) flags+=(-DMK61_LANGUAGE_VM_IMAGE_CACHE_BYTES=0) ;;
  esac
  clang++ -std=c++17 -Wall -Wextra -Werror "${sanitizers[@]}" "${flags[@]}" \
    -DARDUINO_ARCH_STM32 -DMK61_BOARD_CLASSIC_V3 -I"$root/tests/program_store_shim" -I"$root/code" \
    "$root/tests/language_workspace_vm_default_self_test.cpp" "$root/code/language_workspace.cpp" \
    -o "$work/$policy"
  "$work/$policy"
done

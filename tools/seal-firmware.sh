#!/usr/bin/env bash
set -euo pipefail

root="$(cd "$(dirname "$0")/.." && pwd)"
source_file="$root/tools/.mk61-firmware-seal/mk61_firmware_seal.cpp"
format_header="$root/code/resident_firmware_format.hpp"
tool_root="${MK61_SEAL_TOOL_ROOT:-$root/.build/tools}"
tool="$tool_root/mk61_firmware_seal"
host_cxx="${MK61_HOST_CXX:-${CXX:-c++}}"

if [[ ! -x "$tool" || "$source_file" -nt "$tool" ||
      "$format_header" -nt "$tool" ]]; then
  mkdir -p "$tool_root"
  temporary="$tool.tmp"
  "$host_cxx" -std=c++17 -O2 -Wall -Wextra -Werror -pedantic \
    -I"$root/code" "$source_file" -o "$temporary"
  mv "$temporary" "$tool"
fi

exec "$tool" "$@"

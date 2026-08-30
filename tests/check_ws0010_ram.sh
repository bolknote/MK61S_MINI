#!/usr/bin/env bash
set -euo pipefail

fail() {
  printf 'WS0010 RAM check: %s\n' "$1" >&2
  exit 2
}

[[ $# -eq 3 || $# -eq 4 ]] ||
  fail 'usage: check_ws0010_ram.sh ARM_SIZE A00_ELF WS0010_ELF [MAX_GROWTH]'

size_tool="$1"
a00_elf="$2"
ws0010_elf="$3"
maximum_growth="${4:-0}"
[[ -x "$size_tool" ]] || fail "size tool is not executable: $size_tool"
[[ -s "$a00_elf" ]] || fail "A00 ELF is missing: $a00_elf"
[[ -s "$ws0010_elf" ]] || fail "WS0010 ELF is missing: $ws0010_elf"
[[ "$maximum_growth" =~ ^[0-9]+$ ]] ||
  fail "invalid maximum growth: $maximum_growth"

global_ram() {
  local elf="$1"
  local report
  report="$("$size_tool" -A "$elf")" ||
    fail "arm-none-eabi-size failed: $elf"
  awk '
    $1 == ".data" || $1 == ".bss" || $1 == ".noinit" {
      bytes += $2
      sections++
    }
    END {
      if(sections != 3) exit 2
      print bytes
    }
  ' <<<"$report" || fail "RAM sections are incomplete: $elf"
}

a00_ram="$(global_ram "$a00_elf")"
ws0010_ram="$(global_ram "$ws0010_elf")"
[[ "$a00_ram" =~ ^[0-9]+$ && "$ws0010_ram" =~ ^[0-9]+$ ]] ||
  fail 'could not parse global RAM usage'

growth=$((ws0010_ram - a00_ram))
if (( growth > maximum_growth )); then
  fail "WS0010 static RAM growth $growth exceeds budget $maximum_growth bytes"
fi

printf 'WS0010 RAM check: OK (WS0010 %d, A00 %d, delta %d, budget %d bytes)\n' \
  "$ws0010_ram" "$a00_ram" "$growth" "$maximum_growth"

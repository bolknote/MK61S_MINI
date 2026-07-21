#!/usr/bin/env bash
set -euo pipefail

root="$(cd "$(dirname "$0")/.." && pwd)"
tool="$root/tools/.mk61-firmware/mk61-firmware.sh"
launcher="$root/tools/mk61-firmware.cmd"

test -x "$tool"
test -x "$launcher"
test ! -e "$root/tools/mk61-firmware"
test ! -e "$root/tools/mk61-firmware.ps1"
bash -n "$tool"

actual=$($tool --list-profiles)
expected=$(printf '%s\n' \
  $'mini-v3-a00\tmini V3 · LCD1602 A00\t-DMK61_LCD1602_A00' \
  $'mini-v3-a02\tmini V3 · LCD1602 A02\t-DMK61_LCD1602_A02' \
  $'mini-v2-a00\tmini V2 · LCD1602 A00\t-DREVISION_V2 -DMK61_LCD1602_A00' \
  $'mini-v2-a02\tmini V2 · LCD1602 A02\t-DREVISION_V2 -DMK61_LCD1602_A02' \
  $'classic-v2\tClassic V2 · UC1609 192×64\t-DMK61_BOARD_CLASSIC_V2' \
  $'classic-v3\tClassic V3 · UC1609 192×64\t-DMK61_BOARD_CLASSIC_V3' \
  $'40th\tMK61s 40th · UC1609 192×64\t-DMK61_BOARD_40TH')

if [[ "$actual" != "$expected" ]]; then
  printf 'firmware profile matrix differs from the release matrix\n' >&2
  diff <(printf '%s\n' "$expected") <(printf '%s\n' "$actual") >&2 || true
  exit 1
fi

launcher_actual=$($launcher --list-profiles)
if [[ "$launcher_actual" != "$expected" ]]; then
  printf 'polyglot launcher did not dispatch to the shell tool\n' >&2
  diff <(printf '%s\n' "$expected") <(printf '%s\n' "$launcher_actual") >&2 || true
  exit 1
fi

set +e
$tool --profile unsupported --build >/dev/null 2>&1
status=$?
set -e
if [[ "$status" -ne 2 ]]; then
  printf 'invalid profile returned %d, expected 2\n' "$status" >&2
  exit 1
fi

$tool --help | grep -q -- '--profile ID'

config_file=$(mktemp "${TMPDIR:-/tmp}/mk61-firmware-config.XXXXXX")
pty_config=$(mktemp "${TMPDIR:-/tmp}/mk61-firmware-pty-config.XXXXXX")
legacy_root=$(mktemp -d "${TMPDIR:-/tmp}/mk61-firmware-legacy.XXXXXX")
legacy_config="$legacy_root/persisted.conf"
trap 'rm -f "$config_file" "$pty_config" "$legacy_root/selected-profile" "$legacy_config"; rmdir "$legacy_root" 2>/dev/null || true' EXIT
printf '%s\n' \
  'PROFILE=classic-v3' \
  'DFU_UTIL_PATH=/bin/sh' \
  'MK61_ENABLE_FOCAL=0' \
  'MK61_ENABLE_TINYBASIC=1' \
  'MK61_ENABLE_WBMP_VIEWER=0' \
  'MK61_ENABLE_EXTENDED_FONT_SETTINGS=1' \
  'MK61_USER_EXPLORER_SHORTCUT=0' \
  'MK61_MATH_BACKEND=1' > "$config_file"

if command -v expect >/dev/null 2>&1; then
  cp "$config_file" "$pty_config"
  MK61_CONFIG_FILE="$pty_config" MK61_TEST_LAUNCHER="$launcher" expect <<'EXPECT'
set timeout 3
set env(TERM) xterm-256color
log_user 0

spawn $env(MK61_TEST_LAUNCHER)
after 900
send -- "\033OB"
set timeout 1
expect {
  eof {
    send_user "application-cursor Down was interpreted as Esc\n"
    exit 1
  }
  timeout {}
}
send -- q
set timeout 2
expect {
  eof {}
  timeout {
    send_user "firmware menu did not exit after q\n"
    exit 1
  }
}

spawn $env(MK61_TEST_LAUNCHER)
after 900
send -- "\033"
set timeout 2
expect {
  eof {}
  timeout {
    send_user "firmware menu did not exit after Esc\n"
    exit 1
  }
}
EXPECT
fi

config=$(MK61_CONFIG_FILE="$config_file" "$tool" --show-config)
grep -q '^PLATFORM=classic-v3$' <<< "$config"
grep -q '^SCREEN=uc1609$' <<< "$config"
grep -q '^PROFILE=classic-v3$' <<< "$config"
grep -q '^DFU_UTIL_PATH=/bin/sh$' <<< "$config"
grep -q '^MK61_ENABLE_FOCAL=0$' <<< "$config"
grep -q '^MK61_ENABLE_WBMP_VIEWER=0$' <<< "$config"
grep -q '^MK61_ENABLE_EXTENDED_FONT_SETTINGS=1$' <<< "$config"
grep -q '^MK61_MATH_BACKEND=1$' <<< "$config"
grep -q -- 'COMPILE_FLAGS=-DMK61_BOARD_CLASSIC_V3 .*MK61_ENABLE_FOCAL=0 .*MK61_MATH_BACKEND=1$' <<< "$config"
grep -q '^PLATFORM=classic-v3$' "$config_file"
grep -q '^SCREEN=uc1609$' "$config_file"
grep -q '^DFU_UTIL_PATH=/bin/sh$' "$config_file"

override=$(MK61_CONFIG_FILE="$config_file" "$tool" --profile mini-v3-a00 --show-config)
grep -q '^PROFILE=mini-v3-a00$' <<< "$override"
grep -q -- 'COMPILE_FLAGS=-DMK61_LCD1602_A00 ' <<< "$override"
grep -qFx '/.mk61-firmware.conf' "$root/.gitignore"

printf '%s\n' 'PLATFORM=classic-v3' 'SCREEN=lcd1602-a00' > "$config_file"
incompatible=$(MK61_CONFIG_FILE="$config_file" "$tool" --show-config)
grep -q '^PLATFORM=classic-v3$' <<< "$incompatible"
grep -q '^SCREEN=lcd1602-a00$' <<< "$incompatible"
grep -q '^PROFILE=$' <<< "$incompatible"

printf 'mini-v2-a02\n' > "$legacy_root/selected-profile"
legacy=$(MK61_BUILD_ROOT="$legacy_root" MK61_CONFIG_FILE="$legacy_config" \
  "$tool" --show-config)
grep -q '^PROFILE=mini-v2-a02$' <<< "$legacy"
grep -q '^PLATFORM=mini-v2$' "$legacy_config"
grep -q '^SCREEN=lcd1602-a02$' "$legacy_config"
grep -q '^MK61_ENABLE_FOCAL=1$' "$legacy_config"

printf 'firmware_tool_tests: ok\n'

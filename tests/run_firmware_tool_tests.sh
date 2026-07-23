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
$tool --mcu unsupported --profile mini-v3-a00 --build >/dev/null 2>&1
mcu_status=$?
set -e
if [[ "$status" -ne 2 ]]; then
  printf 'invalid profile returned %d, expected 2\n' "$status" >&2
  exit 1
fi
if [[ "$mcu_status" -ne 2 ]]; then
  printf 'invalid MCU returned %d, expected 2\n' "$mcu_status" >&2
  exit 1
fi

$tool --help | grep -q -- '--profile ID'
$tool --help | grep -q -- '--mcu MCU'
$tool --help | grep -q -- '--install-apps'

config_file=$(mktemp "${TMPDIR:-/tmp}/mk61-firmware-config.XXXXXX")
pty_config=$(mktemp "${TMPDIR:-/tmp}/mk61-firmware-pty-config.XXXXXX")
legacy_root=$(mktemp -d "${TMPDIR:-/tmp}/mk61-firmware-legacy.XXXXXX")
installer_root=$(mktemp -d "${TMPDIR:-/tmp}/mk61-firmware-installer.XXXXXX")
legacy_config="$legacy_root/persisted.conf"
trap 'rm -f "$config_file" "$pty_config"; rm -rf "$legacy_root" "$installer_root"' EXIT
printf '%s\n' \
  'PROFILE=classic-v3' \
  'DFU_UTIL_PATH=/bin/sh' \
  'MK61_ENABLE_FOCAL=0' \
  'MK61_ENABLE_TINYBASIC=1' \
  'MK61_ENABLE_WBMP_VIEWER=0' \
  'MK61_ENABLE_USB_SCREEN=0' \
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
expect {
  "CORE math" {}
  timeout {
    send_user "compile-option summary wrapped at 80 columns\n"
    exit 1
  }
}
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
expect "Esc назад"
send -- "\033OB\033OB\033OB\033OB"
expect -re {\x1b\[30;46m[^\r\n]*Платформа}
send -- "\r"
expect "Выберите ревизию платы"
send -- "\033"
expect -re {\x1b\[30;46m[^\r\n]*Платформа}
send -- q
set timeout 2
expect {
  eof {}
  timeout {
    send_user "main menu did not retain the selected row\n"
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
grep -q '^MCU=f411$' <<< "$config"
grep -q '^PLATFORM=classic-v3$' <<< "$config"
grep -q '^SCREEN=uc1609$' <<< "$config"
grep -q '^PROFILE=classic-v3$' <<< "$config"
grep -q '^DFU_UTIL_PATH=/bin/sh$' <<< "$config"
grep -q '^MK61_ENABLE_FOCAL=0$' <<< "$config"
grep -q '^MK61_ENABLE_WBMP_VIEWER=0$' <<< "$config"
grep -q '^MK61_ENABLE_USB_SCREEN=0$' <<< "$config"
grep -q '^MK61_ENABLE_EXTENDED_FONT_SETTINGS=1$' <<< "$config"
grep -q '^MK61_MATH_BACKEND=1$' <<< "$config"
grep -q -- 'COMPILE_FLAGS=-DMK61_BOARD_CLASSIC_V3 .*MK61_ENABLE_FOCAL=0 .*MK61_ENABLE_USB_SCREEN=0 .*MK61_MATH_BACKEND=1$' <<< "$config"
grep -q '^PLATFORM=classic-v3$' "$config_file"
grep -q '^SCREEN=uc1609$' "$config_file"
grep -q '^MCU=f411$' "$config_file"
grep -q '^DFU_UTIL_PATH=/bin/sh$' "$config_file"

override=$(MK61_CONFIG_FILE="$config_file" "$tool" --profile mini-v3-a00 --show-config)
grep -q '^PROFILE=mini-v3-a00$' <<< "$override"
grep -q -- 'COMPILE_FLAGS=-DMK61_LCD1602_A00 ' <<< "$override"
f401_override=$(MK61_CONFIG_FILE="$config_file" "$tool" \
  --mcu f401 --profile mini-v3-a00 --show-config)
grep -q '^MCU=f401$' <<< "$f401_override"
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
grep -q '^MK61_ENABLE_USB_SCREEN=0$' "$legacy_config"

install_config="$installer_root/install.conf"
install_output="$installer_root/output"
install_mount="$installer_root/MK61S C5"
bundle="$install_output/mk61s-M-mini-v3-lcd1602-a00-f401"
mkdir -p "$bundle/System" "$install_mount/System"
printf '%s\n' \
  'MCU=f401' \
  'PLATFORM=mini-v3' \
  'SCREEN=lcd1602-a00' \
  'MK61_ENABLE_FOCAL=1' \
  'MK61_ENABLE_TINYBASIC=0' \
  'MK61_ENABLE_WBMP_VIEWER=1' \
  'MK61_ENABLE_USB_SCREEN=0' \
  'MK61_ENABLE_EXTENDED_FONT_SETTINGS=0' \
  'MK61_USER_EXPLORER_SHORTCUT=1' \
  'MK61_MATH_BACKEND=0' > "$install_config"
install_selection=$(MK61_CONFIG_FILE="$install_config" "$tool" --show-config)
install_flags=$(sed -n 's/^COMPILE_FLAGS=//p' <<< "$install_selection")
printf '%s\n' "$install_flags" > "$bundle/build.flags"
printf 'resident-f401\n' > "$bundle/mk61s-M-mini-v3-lcd1602-a00-f401.bin"
printf 'focal-app\n' > "$bundle/System/FOCAL.APP"
printf 'wbmp-app\n' > "$bundle/System/WBMP.APP"
printf 'keep-me\n' > "$install_mount/System/KEEP.APP"
printf 'stale-basic\n' > "$install_mount/System/BASIC.APP"

install_result=$(MK61_CONFIG_FILE="$install_config" \
  MK61_OUTPUT_DIR="$install_output" MK61_C5_MOUNT="$install_mount" \
  "$tool" --install-apps)
grep -q 'Меню → USB-диск' <<< "$install_result"
grep -q 'Synchronized and verified' <<< "$install_result"
cmp "$bundle/System/FOCAL.APP" "$install_mount/System/FOCAL.APP"
cmp "$bundle/System/WBMP.APP" "$install_mount/System/WBMP.APP"
grep -q '^keep-me$' "$install_mount/System/KEEP.APP"
test ! -e "$install_mount/System/BASIC.APP"

sed -e 's/^MK61_ENABLE_FOCAL=1$/MK61_ENABLE_FOCAL=0/' \
    -e 's/^MK61_ENABLE_WBMP_VIEWER=1$/MK61_ENABLE_WBMP_VIEWER=0/' \
    "$install_config" > "$install_config.disabled"
mv "$install_config.disabled" "$install_config"
disabled_selection=$(MK61_CONFIG_FILE="$install_config" "$tool" --show-config)
disabled_flags=$(sed -n 's/^COMPILE_FLAGS=//p' <<< "$disabled_selection")
printf '%s\n' "$disabled_flags" > "$bundle/build.flags"
disabled_result=$(MK61_CONFIG_FILE="$install_config" \
  MK61_OUTPUT_DIR="$install_output" MK61_C5_MOUNT="$install_mount" \
  "$tool" --install-apps)
grep -q 'Removed disabled canonical System APP' <<< "$disabled_result"
test ! -e "$install_mount/System/FOCAL.APP"
test ! -e "$install_mount/System/BASIC.APP"
test ! -e "$install_mount/System/WBMP.APP"
grep -q '^keep-me$' "$install_mount/System/KEEP.APP"

set +e
MK61_CONFIG_FILE="$install_config" MK61_OUTPUT_DIR="$install_output" \
  MK61_C5_MOUNT="$install_mount" "$tool" \
  --mcu f411 --profile mini-v3-a00 --install-apps >/dev/null 2>&1
f411_install_status=$?
set -e
if [[ "$f411_install_status" -ne 1 ]]; then
  printf 'F411 APP installation returned %d, expected 1\n' \
    "$f411_install_status" >&2
  exit 1
fi

printf 'firmware_tool_tests: ok\n'

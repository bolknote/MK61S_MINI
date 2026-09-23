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
  $'mini-v3-ws0010\tmini V3 · OLED1602 WS0010\t-DMK61_OLED1602_WS0010' \
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
  'MK61_ENABLE_MARKDOWN_VIEWER=1' \
  'MK61_ENABLE_CHIP8=0' \
  'MK61_ENABLE_USB_SCREEN=0' \
  'MK61_ENABLE_LOADABLE_MODULES=1' \
  'MK61_ENABLE_EXTENDED_FONT_SETTINGS=1' \
  'MK61_USER_EXPLORER_SHORTCUT=0' \
  'MK61_MATH_BACKEND=1' \
  'MK61_APP_LOCAL_FLOAT_MATH=0' > "$config_file"

if command -v expect >/dev/null 2>&1; then
  cp "$config_file" "$pty_config"
  nested_config="$installer_root/nested.conf"
  cp "$config_file" "$nested_config"
  detect_config="$installer_root/detect.conf"
  detect_log="$installer_root/detect.tty"
  fake_dfu="$installer_root/dfu-util"
  fake_arduino="$installer_root/arduino-cli"
  sed "s#^DFU_UTIL_PATH=.*#DFU_UTIL_PATH=$fake_dfu#" \
    "$config_file" > "$detect_config"
  printf '%s\n' '#!/bin/sh' 'sleep 0.2' 'exit 0' > "$fake_dfu"
  printf '%s\n' '#!/bin/sh' 'sleep 0.3' \
    'printf '\''{"detected_ports":[]}'\''"\n"' > "$fake_arduino"
  chmod +x "$fake_dfu" "$fake_arduino"
  MK61_CONFIG_FILE="$pty_config" MK61_TEST_LAUNCHER="$launcher" \
  MK61_TEST_NESTED_CONFIG="$nested_config" \
  MK61_TEST_DETECT_CONFIG="$detect_config" \
  MK61_TEST_DETECT_LOG="$detect_log" \
  MK61_TEST_ARDUINO_CLI="$fake_arduino" expect <<'EXPECT'
set timeout 3
set env(TERM) xterm-256color
log_user 0

spawn $env(MK61_TEST_LAUNCHER)
after 900
expect {
  "MATH CORE" {}
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
send -- "\033OB\033OB\033OB"
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

# The compile-key screen is a real settings menu: math is entered explicitly
# and returning from it does not save until the dedicated save item is chosen.
set env(MK61_CONFIG_FILE) $env(MK61_TEST_NESTED_CONFIG)
spawn $env(MK61_TEST_LAUNCHER)
after 900
send -- "7"
expect "Enter переключает ключ"
send -- "\033OF\033OA\r"
expect "Выберите точность и размер математической библиотеки"
send -- "\033OB\r"
expect "Математика: CORE + APP FLOAT"
send -- "\033OF\r"
expect "MATH CORE + APP FLOAT"
send -- q
set timeout 2
expect {
  eof {}
  timeout {
    send_user "firmware menu did not exit after nested math selection\n"
    exit 1
  }
}

# Keys pressed while detection owns the foreground used to be echoed by the
# tty as literal ^[[B/^[[A and remained painted over the menu.
set env(MK61_CONFIG_FILE) $env(MK61_TEST_DETECT_CONFIG)
set env(MK61_ARDUINO_CLI) $env(MK61_TEST_ARDUINO_CLI)
log_file -noappend $env(MK61_TEST_DETECT_LOG)
spawn $env(MK61_TEST_LAUNCHER)
after 900
send -- "8"
after 100
send -- "\033OB\033OA"
set timeout 8
expect {
  "Enter или Esc закрыть" {}
  timeout {
    send_user "device-detection result dialog did not appear\n"
    exit 1
  }
}
send -- "\033"
expect "Устройство: устройство не найдено"
send -- q
set timeout 3
expect {
  eof {}
  timeout {
    send_user "firmware menu did not exit after device-detection key burst\n"
    exit 1
  }
}
log_file
EXPECT
  grep -q '^MK61_MATH_BACKEND=1$' "$nested_config"
  grep -q '^MK61_APP_LOCAL_FLOAT_MATH=1$' "$nested_config"
  if grep -Eq '\^\[\[[AB]' "$detect_log"; then
    printf 'arrow escape sequence was echoed during device detection\n' >&2
    exit 1
  fi
fi

config=$(MK61_CONFIG_FILE="$config_file" "$tool" --show-config)
grep -q '^MCU=f411$' <<< "$config"
grep -q '^PLATFORM=classic-v3$' <<< "$config"
grep -q '^SCREEN=uc1609$' <<< "$config"
grep -q '^PROFILE=classic-v3$' <<< "$config"
grep -q '^DFU_UTIL_PATH=/bin/sh$' <<< "$config"
grep -q '^MK61_ENABLE_FOCAL=0$' <<< "$config"
grep -q '^MK61_ENABLE_WBMP_VIEWER=0$' <<< "$config"
grep -q '^MK61_ENABLE_MARKDOWN_VIEWER=1$' <<< "$config"
grep -q '^MK61_ENABLE_CHIP8=0$' <<< "$config"
grep -q '^MK61_ENABLE_USB_SCREEN=0$' <<< "$config"
grep -q '^MK61_ENABLE_LOADABLE_MODULES=1$' <<< "$config"
grep -q '^MK61_ENABLE_EXTENDED_FONT_SETTINGS=1$' <<< "$config"
grep -q '^MK61_MATH_BACKEND=1$' <<< "$config"
grep -q '^MK61_APP_LOCAL_FLOAT_MATH=0$' <<< "$config"
grep -q -- 'COMPILE_FLAGS=-DMK61_BOARD_CLASSIC_V3 .*MK61_ENABLE_FOCAL=0 .*MK61_ENABLE_USB_SCREEN=0 .*MK61_ENABLE_LOADABLE_MODULES=1 .*MK61_MATH_BACKEND=1 .*HAL_UART_MODULE_ONLY .*USBD_CLASS_USER_STRING_DESC=0$' <<< "$config"
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

hybrid_config="$legacy_root/hybrid.conf"
printf '%s\n' \
  'MCU=f401' \
  'PLATFORM=classic-v2' \
  'SCREEN=uc1609' \
  'MK61_MATH_BACKEND=1' \
  'MK61_APP_LOCAL_FLOAT_MATH=1' > "$hybrid_config"
hybrid=$(MK61_CONFIG_FILE="$hybrid_config" "$tool" --show-config)
grep -q '^MK61_MATH_BACKEND=1$' <<< "$hybrid"
grep -q '^MK61_APP_LOCAL_FLOAT_MATH=1$' <<< "$hybrid"
grep -q -- 'COMPILE_FLAGS=.*-DMK61_MATH_BACKEND=1 -DMK61_APP_LOCAL_FLOAT_MATH=1 ' <<< "$hybrid"
grep -q -- "-LocalFloatMath.*State.AppLocalFloat" "$root/tools/.mk61-firmware/mk61-firmware.ps1"
grep -q -- '-LocalFloatMath "$APP_LOCAL_FLOAT"' "$tool"
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
grep -q '^MK61_ENABLE_MARKDOWN_VIEWER=1$' "$legacy_config"
grep -q '^MK61_ENABLE_CHIP8=0$' "$legacy_config"
grep -q '^MK61_ENABLE_USB_SCREEN=0$' "$legacy_config"
grep -q '^MK61_ENABLE_LOADABLE_MODULES=1$' "$legacy_config"
! grep -q '^MK61_ENABLE_USER_APPS=' "$legacy_config"

install_config="$installer_root/install.conf"
install_output="$installer_root/output"
install_mount="$installer_root/MK61S C6"
bundle="$install_output/mk61s-M-mini-v3-lcd1602-a00-f401"
mkdir -p "$bundle/System" "$install_mount/System"
printf '%s\n' \
  'MCU=f401' \
  'PLATFORM=mini-v3' \
  'SCREEN=lcd1602-a00' \
  'MK61_ENABLE_FOCAL=1' \
  'MK61_ENABLE_TINYBASIC=0' \
  'MK61_ENABLE_WBMP_VIEWER=1' \
  'MK61_ENABLE_MARKDOWN_VIEWER=1' \
  'MK61_ENABLE_CHIP8=1' \
  'MK61_ENABLE_USB_SCREEN=1' \
  'MK61_ENABLE_LOADABLE_MODULES=1' \
  'MK61_ENABLE_EXTENDED_FONT_SETTINGS=0' \
  'MK61_USER_EXPLORER_SHORTCUT=1' \
  'MK61_MATH_BACKEND=0' > "$install_config"
install_selection=$(MK61_CONFIG_FILE="$install_config" "$tool" --show-config)
grep -q '^MK61_ENABLE_WBMP_VIEWER=0$' <<< "$install_selection"
install_flags=$(sed -n 's/^COMPILE_FLAGS=//p' <<< "$install_selection")
printf '%s\n' "$install_flags" > "$bundle/build.flags"
printf 'format 1\nabi 6\n' > "$bundle/build.apps"
printf 'resident-f401\n' > "$bundle/mk61s-M-mini-v3-lcd1602-a00-f401.bin"
printf 'focal-app\n' > "$bundle/System/FOCAL.APP"
printf 'markdown-app\n' > "$bundle/System/MARKDOWN.APP"
printf 'chip8-app\n' > "$bundle/System/CHIP8.APP"
for resource in SETUP.APP USBDISK.APP HELP0.TXT HELP1.TXT; do
  printf 'service-resource\n' > "$bundle/System/$resource"
done
printf 'keep-me\n' > "$install_mount/System/KEEP.APP"
printf 'stale-basic\n' > "$install_mount/System/BASIC.APP"
printf 'stale-wbmp\n' > "$install_mount/System/WBMP.APP"

install_result=$(MK61_CONFIG_FILE="$install_config" \
  MK61_OUTPUT_DIR="$install_output" MK61_C6_MOUNT="$install_mount" \
  "$tool" --install-apps)
grep -q 'Меню → USB-диск' <<< "$install_result"
grep -q 'Synchronized and verified' <<< "$install_result"
cmp "$bundle/System/FOCAL.APP" "$install_mount/System/FOCAL.APP"
cmp "$bundle/System/MARKDOWN.APP" "$install_mount/System/MARKDOWN.APP"
cmp "$bundle/System/CHIP8.APP" "$install_mount/System/CHIP8.APP"
grep -q '^keep-me$' "$install_mount/System/KEEP.APP"
test ! -e "$install_mount/System/BASIC.APP"
test ! -e "$install_mount/System/WBMP.APP"

sed -e 's/^MK61_ENABLE_FOCAL=1$/MK61_ENABLE_FOCAL=0/' \
    -e 's/^MK61_ENABLE_WBMP_VIEWER=1$/MK61_ENABLE_WBMP_VIEWER=0/' \
    -e 's/^MK61_ENABLE_MARKDOWN_VIEWER=1$/MK61_ENABLE_MARKDOWN_VIEWER=0/' \
    -e 's/^MK61_ENABLE_CHIP8=1$/MK61_ENABLE_CHIP8=0/' \
    "$install_config" > "$install_config.disabled"
mv "$install_config.disabled" "$install_config"
disabled_selection=$(MK61_CONFIG_FILE="$install_config" "$tool" --show-config)
disabled_flags=$(sed -n 's/^COMPILE_FLAGS=//p' <<< "$disabled_selection")
printf '%s\n' "$disabled_flags" > "$bundle/build.flags"
disabled_result=$(MK61_CONFIG_FILE="$install_config" \
  MK61_OUTPUT_DIR="$install_output" MK61_C6_MOUNT="$install_mount" \
  "$tool" --install-apps)
grep -q 'Synchronized and verified' <<< "$disabled_result"
for resource in SETUP.APP USBDISK.APP HELP0.TXT HELP1.TXT; do
  cmp "$bundle/System/$resource" "$install_mount/System/$resource"
done
test ! -e "$install_mount/System/FOCAL.APP"
test ! -e "$install_mount/System/BASIC.APP"
test ! -e "$install_mount/System/WBMP.APP"
test ! -e "$install_mount/System/MARKDOWN.APP"
test ! -e "$install_mount/System/CHIP8.APP"
grep -q '^keep-me$' "$install_mount/System/KEEP.APP"

f411_bundle="$install_output/mk61s-M-mini-v3-lcd1602-a00-f411"
mkdir -p "$f411_bundle/System"
f411_selection=$(MK61_CONFIG_FILE="$install_config" "$tool" \
  --mcu f411 --profile mini-v3-a00 --show-config)
f411_flags=$(sed -n 's/^COMPILE_FLAGS=//p' <<< "$f411_selection")
printf '%s\n' "$f411_flags" > "$f411_bundle/build.flags"
printf 'format 1\nabi 6\n' > "$f411_bundle/build.apps"
printf 'resident-f411\n' > "$f411_bundle/mk61s-M-mini-v3-lcd1602-a00-f411.bin"
for resource in HELP0.TXT HELP1.TXT; do
  printf 'f411-resource\n' > "$f411_bundle/System/$resource"
done
MK61_CONFIG_FILE="$install_config" MK61_OUTPUT_DIR="$install_output" \
  MK61_C6_MOUNT="$install_mount" "$tool" \
  --mcu f411 --profile mini-v3-a00 --install-apps >/dev/null
test ! -e "$install_mount/System/SETUP.APP"
test ! -e "$install_mount/System/USBDISK.APP"

printf 'firmware_tool_tests: ok\n'

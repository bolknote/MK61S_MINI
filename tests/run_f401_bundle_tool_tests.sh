#!/usr/bin/env bash
set -euo pipefail

root="$(cd "$(dirname "$0")/.." && pwd)"
tool="$root/tools/build_f401_bundle.sh"
work="$(mktemp -d "${TMPDIR:-/tmp}/mk61-f401-bundle-test.XXXXXX")"
trap 'rm -rf "$work"' EXIT

test -x "$tool"
bash -n "$tool"
"$tool" --help | grep -q -- '--profile ID'
"$tool" --help | grep -q 'MK61_ENABLE_WBMP_VIEWER'
"$tool" --help | grep -q -- '--app-manifest FILE'

app_dir="$work/app"
mkdir -p "$app_dir/include"
printf '%s\n' \
  'format 1' \
  'name DEMO' \
  'source demo.cpp' \
  'file include/demo.hpp' > "$app_dir/app.mk61"
printf '%s\n' '#include "include/demo.hpp"' > "$app_dir/demo.cpp"
printf '%s\n' '#pragma once' > "$app_dir/include/demo.hpp"
"$tool" --check-app-manifests \
  --app-manifest "$app_dir/app.mk61" > "$work/app-check.log"
grep -q '^Validated APP manifests: 1$' "$work/app-check.log"
grep -q '^Apps/DEMO.APP <- ' "$work/app-check.log"
MK61_APP_MANIFESTS="$app_dir/app.mk61" \
  "$tool" --check-app-manifests > "$work/app-env-check.log"
grep -q '^Validated APP manifests: 1$' "$work/app-env-check.log"
printf '%s\n' \
  'format 1' \
  'name EXTRA' \
  'source demo.cpp' > "$app_dir/extra.mk61"
MK61_APP_MANIFESTS="$app_dir/app.mk61;$app_dir/extra.mk61" \
  "$tool" --check-app-manifests > "$work/app-env-list-check.log"
grep -q '^Validated APP manifests: 2$' "$work/app-env-list-check.log"

printf '%s\n' \
  'format 1' \
  'name BROKEN' \
  'source ../escape.cpp' > "$app_dir/broken.mk61"
set +e
"$tool" --check-app-manifests \
  --app-manifest "$app_dir/broken.mk61" > /dev/null 2>&1
status=$?
set -e
test "$status" -ne 0

printf '%s\n' \
  'format 1' \
  'name CASEPATH' \
  'source demo.cpp' \
  'file DEMO.CPP' > "$app_dir/case-path.mk61"
set +e
"$tool" --check-app-manifests \
  --app-manifest "$app_dir/case-path.mk61" > /dev/null 2>&1
status=$?
set -e
test "$status" -ne 0

printf '%s\n' 'void helper(void) {}' > "$app_dir/helper.c"
printf '%s\n' \
  'format 1' \
  'name BADFILE' \
  'source demo.cpp' \
  'file helper.c' > "$app_dir/compiled-file.mk61"
set +e
"$tool" --check-app-manifests \
  --app-manifest "$app_dir/compiled-file.mk61" > /dev/null 2>&1
status=$?
set -e
test "$status" -ne 0

printf '%s\n' \
  'format 1' \
  'name CON' \
  'source demo.cpp' > "$app_dir/reserved-name.mk61"
set +e
"$tool" --check-app-manifests \
  --app-manifest "$app_dir/reserved-name.mk61" > /dev/null 2>&1
status=$?
set -e
test "$status" -ne 0

printf '%s\n' \
  'format 1' \
  'name demo' \
  'source demo.cpp' > "$app_dir/duplicate.mk61"
set +e
"$tool" --check-app-manifests \
  --app-manifest "$app_dir/app.mk61" \
  --app-manifest "$app_dir/duplicate.mk61" > /dev/null 2>&1
status=$?
set -e
test "$status" -ne 0

set +e
"$tool" --profile unsupported > /dev/null 2>&1
status=$?
set -e
test "$status" -eq 2

set +e
MK61_ENABLE_FOCAL=2 "$tool" > /dev/null 2>&1
status=$?
set -e
test "$status" -eq 2

# При выключенных ключах сборщик не должен требовать overlay/toolchain и не
# должен оставлять старые системные APP в комплекте. Arduino CLI здесь заменён
# минимальной моделью только resident-сборки.
fake_cli="$work/arduino-cli"
cat > "$fake_cli" <<'EOF'
#!/usr/bin/env bash
set -euo pipefail
case "${1:-}" in
  version)
    printf 'arduino-cli Version: 1.2.2\n'
    exit 0
    ;;
  core)
    if [ "${2:-}" = list ]; then
      printf 'STMicroelectronics:stm32 2.12.0 2.12.0 STM32 MCU based boards\n'
      exit 0
    fi
    ;;
  lib)
    if [ "${2:-}" = list ]; then
      printf 'LiquidCrystal 1.0.7 -\nSTM32duino RTC 1.9.0 -\n'
      exit 0
    fi
    ;;
esac
build_path=
while [ "$#" -gt 0 ]; do
  case "$1" in
    --build-path) build_path=$2; shift 2 ;;
    *) shift ;;
  esac
done
[ -n "$build_path" ]
mkdir -p "$build_path"
printf 'resident-elf' > "$build_path/mk61s-M.ino.elf"
printf 'resident-bin' > "$build_path/mk61s-M.ino.bin"
EOF
chmod +x "$fake_cli"

bundle="$work/output/mk61s-M-mini-v3-lcd1602-a00-f401"
mkdir -p "$bundle"
mkdir -p "$bundle/System"
mkdir -p "$bundle/Apps"
printf 'stale' > "$bundle/System/FOCAL.APP"
printf 'stale' > "$bundle/System/BASIC.APP"
printf 'stale' > "$bundle/System/WBMP.APP"
printf 'stale' > "$bundle/Apps/STALE.APP"

MK61_ARDUINO_CLI="$fake_cli" \
MK61_F401_BUILD_ROOT="$work/build" \
MK61_OUTPUT_DIR="$work/output" \
MK61_ENABLE_FOCAL=0 \
MK61_ENABLE_TINYBASIC=0 \
MK61_ENABLE_WBMP_VIEWER=0 \
  "$tool" --profile mini-v3-a00 > "$work/output.log"

test -s "$bundle/mk61s-M-mini-v3-lcd1602-a00-f401.bin"
test -s "$bundle/build.flags"
test -s "$bundle/build.apps"
test ! -e "$bundle/System/FOCAL.APP"
test ! -e "$bundle/System/BASIC.APP"
test ! -e "$bundle/System/WBMP.APP"
test ! -e "$bundle/Apps/STALE.APP"
grep -q -- '-DMK61_ENABLE_FOCAL=0' "$bundle/build.flags"
grep -q '^format 1$' "$bundle/build.apps"
grep -q 'Built F401 bundle:' "$work/output.log"

# Публичный mk61-firmware должен направлять F401 в тот же bundle-builder,
# передавать сохранённые ключи и сообщать, нужен ли второй шаг.
firmware_tool="$root/tools/.mk61-firmware/mk61-firmware.sh"
"$firmware_tool" --help | grep -q 'MK61_APP_MANIFESTS'
firmware_config="$work/firmware.conf"
firmware_output="$work/firmware-output"
printf '%s\n' \
  'MCU=f401' \
  'PLATFORM=mini-v3' \
  'SCREEN=lcd1602-a00' \
  'MK61_ENABLE_FOCAL=0' \
  'MK61_ENABLE_TINYBASIC=0' \
  'MK61_ENABLE_WBMP_VIEWER=0' \
  'MK61_ENABLE_USB_SCREEN=0' \
  'MK61_ENABLE_EXTENDED_FONT_SETTINGS=0' \
  'MK61_USER_EXPLORER_SHORTCUT=1' \
  'MK61_MATH_BACKEND=0' > "$firmware_config"
MK61_ARDUINO_CLI="$fake_cli" \
MK61_BUILD_ROOT="$work/firmware-build" \
MK61_OUTPUT_DIR="$firmware_output" \
MK61_CONFIG_FILE="$firmware_config" \
  "$firmware_tool" --build > "$work/firmware-output.log"

firmware_bundle="$firmware_output/mk61s-M-mini-v3-lcd1602-a00-f401"
test -s "$firmware_bundle/mk61s-M-mini-v3-lcd1602-a00-f401.bin"
test -s "$firmware_bundle/build.flags"
grep -q -- '-DMK61_ENABLE_FOCAL=0' "$firmware_bundle/build.flags"
grep -q 'Built F401 bundle:' "$work/firmware-output.log"
grep -q 'step 2 is only needed to remove previously installed canonical System APP' \
  "$work/firmware-output.log"

printf 'f401_bundle_tool_tests: ok\n'

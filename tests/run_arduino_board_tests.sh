#!/usr/bin/env bash
set -euo pipefail

root="$(cd "$(dirname "$0")/.." && pwd)"
launcher="$root/tools/mk61-arduino-board.cmd"
package="$root/tools/.mk61-arduino-board"
platform="$package/hardware/mk61/stm32"
hook="$platform/tools/mk61-app-postbuild.sh"
work="$(mktemp -d "${TMPDIR:-/tmp}/mk61-arduino-board-test.XXXXXX")"
trap 'rm -rf "$work"' EXIT

test -x "$launcher"
test -x "$package/install.sh"
test -x "$hook"
bash -n "$package/install.sh"
bash -n "$hook"

"$launcher" --help > "$work/help.txt"
grep -q 'MK61s F401 + APP' "$work/help.txt"
grep -q -- '--sketchbook DIR' "$work/help.txt"
grep -q 'does not install Arduino CLI' "$work/help.txt"

shell_sketchbook="$work/shell-sketchbook"
"$launcher" --sketchbook "$shell_sketchbook" > "$work/install.txt"
"$launcher" --check --sketchbook "$shell_sketchbook" > "$work/check.txt"
target="$shell_sketchbook/hardware/mk61/stm32"
cmp "$platform/boards.txt" "$target/boards.txt"
cmp "$platform/platform.txt" "$target/platform.txt"
cmp "$platform/tools/mk61_module.ld" "$target/tools/mk61_module.ld"
cmp "$hook" "$target/tools/mk61-app-postbuild.sh"
cmp "$platform/tools/mk61-app-postbuild.ps1" \
    "$target/tools/mk61-app-postbuild.ps1"

grep -q '^mk61_f401_app.name=MK61s F401 + APP$' "$target/boards.txt"
grep -q '^mk61_f401_app.build.core=STMicroelectronics:arduino$' \
  "$target/boards.txt"
grep -q '^mk61_f401_app.upload.tool=stm32CubeProg$' "$target/boards.txt"
grep -q '^mk61_f401_app.menu.mk61_platform.mini_v3=' \
  "$target/boards.txt"
grep -q '^mk61_f401_app.menu.mk61_display.lcd_a00=' \
  "$target/boards.txt"
grep -q 'recipe.hooks.objcopy.postobjcopy.20.pattern.windows=' \
  "$target/platform.txt"

"$hook" check-profile --platform mini-v3 --display lcd1602-a00 \
  --sketch "$root/code"
if "$hook" check-profile --platform mini-v3 --display uc1609 \
    --sketch "$root/code" >/dev/null 2>&1; then
  echo 'invalid Arduino platform/display pair was accepted' >&2
  exit 1
fi

grep -q 'MK61_ARDUINO_IDE_SYSTEM_APPS' \
  "$root/code/mk61_ide_focal_app.cpp"
grep -q 'MK61_ARDUINO_IDE_SYSTEM_APPS' \
  "$root/code/mk61_ide_basic_app.cpp"
grep -q 'MK61_ARDUINO_IDE_SYSTEM_APPS' \
  "$root/code/mk61_ide_wbmp_app.cpp"
grep -q 'mk61_arduino_sketch_anchor' "$root/code/code.ino"

if command -v pwsh >/dev/null 2>&1; then
  ps_sketchbook="$work/powershell-sketchbook"
  pwsh -NoLogo -NoProfile -File "$package/install.ps1" \
    -Sketchbook "$ps_sketchbook" > "$work/install-ps.txt"
  pwsh -NoLogo -NoProfile -File "$package/install.ps1" \
    -Check -Sketchbook "$ps_sketchbook" > "$work/check-ps.txt"
  cmp "$platform/boards.txt" \
      "$ps_sketchbook/hardware/mk61/stm32/boards.txt"
  pwsh -NoLogo -NoProfile -File \
    "$platform/tools/mk61-app-postbuild.ps1" check-profile \
    -Platform mini-v3 -Display lcd1602-a00 -Sketch "$root/code"
fi

if [ "${MK61_RUN_ARDUINO_BOARD_INTEGRATION:-0}" = 1 ]; then
  command -v arduino-cli >/dev/null 2>&1 ||
    { echo 'arduino-cli is required for integration test' >&2; exit 1; }
  library_root=${MK61_ARDUINO_LIBRARY_ROOT:-}
  if [ -z "$library_root" ] && [ -d "$HOME/Documents/Arduino/libraries" ]; then
    library_root="$HOME/Documents/Arduino/libraries"
  fi
  [ -d "$library_root/LiquidCrystal" ] &&
    [ -d "$library_root/STM32duino_RTC" ] ||
    { echo 'Arduino integration libraries were not found' >&2; exit 1; }

  ln -s "$library_root" "$shell_sketchbook/libraries"
  mkdir -p "$shell_sketchbook/sketches/code" "$work/build"
  cp -R "$root/code/." "$shell_sketchbook/sketches/code/"
  ARDUINO_DIRECTORIES_USER="$shell_sketchbook" arduino-cli compile \
    --fqbn 'mk61:stm32:mk61_f401_app:mk61_platform=mini_v3,mk61_display=lcd_a00,mk61_focal=enabled,mk61_basic=enabled,mk61_wbmp=enabled,mk61_usb_screen=disabled,mk61_font_settings=disabled,mk61_explorer=enabled,mk61_math=libm' \
    --build-path "$work/build" "$shell_sketchbook/sketches/code"

  bundle="$shell_sketchbook/sketches/binary/mk61s-M-mini-v3-lcd1602-a00-f401"
  resident="$bundle/mk61s-M-mini-v3-lcd1602-a00-f401.bin"
  module_root="$work/build/mk61-system-apps/mk61s-M-mini-v3-lcd1602-a00-f401/modules"
  test -s "$resident"
  grep -q 'mk61_ide_focal_module_entry' "$module_root/focal/focal.map"
  grep -q 'mk61_ide_basic_module_entry' "$module_root/basic/basic.map"
  grep -q 'mk61_ide_wbmp_module_entry' "$module_root/wbmp/wbmp.map"
  grep -q 'mk61_ide_wbmp_view' "$module_root/wbmp/wbmp.map"
  for app in FOCAL.APP BASIC.APP WBMP.APP; do
    file="$bundle/System/$app"
    test -s "$file"
    test "$(wc -c < "$file" | tr -d '[:space:]')" -le 20544
    test "$(od -An -tu1 -j15 -N1 "$file" | tr -d '[:space:]')" = 0
    test "$(od -An -tx1 -N8 "$file" | tr -d '[:space:]')" = \
      4d4b363141505000
  done

  mkdir -p "$work/build-all-options"
  ARDUINO_DIRECTORIES_USER="$shell_sketchbook" arduino-cli compile \
    --fqbn 'mk61:stm32:mk61_f401_app:mk61_platform=mini_v3,mk61_display=lcd_a00,mk61_focal=enabled,mk61_basic=enabled,mk61_wbmp=enabled,mk61_usb_screen=enabled,mk61_font_settings=enabled,mk61_explorer=enabled,mk61_math=libm' \
    --build-path "$work/build-all-options" "$shell_sketchbook/sketches/code"
  for app in FOCAL.APP BASIC.APP WBMP.APP; do
    test -s "$bundle/System/$app"
    test "$(wc -c < "$bundle/System/$app" | tr -d '[:space:]')" -le 20544
  done

  mkdir -p "$work/build-disabled"
  ARDUINO_DIRECTORIES_USER="$shell_sketchbook" arduino-cli compile \
    --fqbn 'mk61:stm32:mk61_f401_app:mk61_platform=mini_v3,mk61_display=lcd_a00,mk61_focal=disabled,mk61_basic=disabled,mk61_wbmp=disabled,mk61_usb_screen=disabled,mk61_font_settings=disabled,mk61_explorer=enabled,mk61_math=libm' \
    --build-path "$work/build-disabled" "$shell_sketchbook/sketches/code"
  test ! -e "$bundle/System"
  grep -q -- '-DMK61_ENABLE_FOCAL=0' "$bundle/build.flags"
  grep -q -- '-DMK61_ENABLE_TINYBASIC=0' "$bundle/build.flags"
  grep -q -- '-DMK61_ENABLE_WBMP_VIEWER=0' "$bundle/build.flags"

  mkdir -p "$work/build-classic"
  ARDUINO_DIRECTORIES_USER="$shell_sketchbook" arduino-cli compile \
    --fqbn 'mk61:stm32:mk61_f401_app:mk61_platform=classic_v3,mk61_display=uc1609,mk61_focal=enabled,mk61_basic=enabled,mk61_wbmp=enabled,mk61_usb_screen=disabled,mk61_font_settings=disabled,mk61_explorer=enabled,mk61_math=libm' \
    --build-path "$work/build-classic" "$shell_sketchbook/sketches/code"
  classic_bundle="$shell_sketchbook/sketches/binary/mk61s-M-classic-v3-uc1609-f401"
  test -s "$classic_bundle/mk61s-M-classic-v3-uc1609-f401.bin"
  test -s "$classic_bundle/System/FOCAL.APP"
  test -s "$classic_bundle/System/BASIC.APP"
  test -s "$classic_bundle/System/WBMP.APP"
fi

printf 'arduino_board_tests: ok\n'

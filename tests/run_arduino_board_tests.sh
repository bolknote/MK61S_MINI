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
cmp "$root/tools/.mk61-firmware-seal/mk61_firmware_seal.cpp" \
    "$target/tools/mk61_firmware_seal.cpp"
cmp "$root/code/resident_firmware_format.hpp" \
    "$target/tools/resident_firmware_format.hpp"
cmp "$root/code/rust_types.h" "$target/tools/rust_types.h"
cmp "$root/tools/seal-firmware.ps1" \
    "$target/tools/seal-firmware.ps1"

grep -q '^mk61_f401_app.name=MK61s F401 + APP$' "$target/boards.txt"
grep -q '^mk61_f401_app.build.core=STMicroelectronics:arduino$' \
  "$target/boards.txt"
grep -q '^mk61_f401_app.upload.tool=stm32CubeProg$' "$target/boards.txt"
grep -q '^mk61_f401_app.menu.mk61_platform.mini_v3=' \
  "$target/boards.txt"
grep -q '^mk61_f401_app.menu.mk61_platform.mini_v2=' \
  "$target/boards.txt"
grep -q '^mk61_f401_app.menu.mk61_platform.classic_v2=' \
  "$target/boards.txt"
grep -q '^mk61_f401_app.menu.mk61_display.lcd_a00=' \
  "$target/boards.txt"
grep -q '^mk61_f401_app.menu.mk61_display.oled_ws0010=' \
  "$target/boards.txt"
grep -q '^mk61_f401_app.menu.mk61_documents.markdown=MARKDOWN.APP · T2 + I1$' \
  "$target/boards.txt"
grep -q 'recipe.hooks.objcopy.postobjcopy.20.pattern.windows=' \
  "$target/platform.txt"
grep -q -- '-DMK61_REQUIRE_RESIDENT_CRC=1' "$target/boards.txt"
grep -q -- '-DMK61_ENABLE_LOADABLE_MODULES=1' "$target/boards.txt"
grep -q -- '-DMK61_F401_PRODUCT_BUILD=1' "$target/boards.txt"
grep -q -- '-DMK61_REQUIRE_F401_SELECTIVE_O3=1' "$target/boards.txt"
grep -q -- '-DMK61_APP_LOCAL_FLOAT_MATH={build.mk61_app_math}' \
  "$target/boards.txt"
! grep -q 'mk61_user_apps' "$target/boards.txt"
core_math_line="$(grep -n '^mk61_f401_app\.menu\.mk61_math\.core=' \
  "$target/boards.txt" | cut -d: -f1)"
core_app_float_math_line="$(grep -n \
  '^mk61_f401_app\.menu\.mk61_math\.core_app_float=' \
  "$target/boards.txt" | cut -d: -f1)"
libm_math_line="$(grep -n '^mk61_f401_app\.menu\.mk61_math\.libm=' \
  "$target/boards.txt" | cut -d: -f1)"
test "$core_math_line" -lt "$core_app_float_math_line"
test "$core_app_float_math_line" -lt "$libm_math_line"
! grep -q '^mk61_f401_app.menu.mk61_math.float=' "$target/boards.txt"
grep -q '^mk61_f401_app.menu.mk61_math.core_app_float.build.mk61_math=1$' \
  "$target/boards.txt"
grep -q '^mk61_f401_app.menu.mk61_math.core_app_float.build.mk61_app_math=1$' \
  "$target/boards.txt"
grep -q -- '--local-float-math "{build.mk61_app_math}"' \
  "$target/platform.txt"
grep -q -- '-LocalFloatMath "{build.mk61_app_math}"' \
  "$target/platform.txt"

"$hook" check-profile --platform mini-v3 --display lcd1602-a00 \
  --sketch "$root/code"
"$hook" check-profile --platform mini-v3 --display oled1602-ws0010 \
  --sketch "$root/code"
if "$hook" check-profile --platform mini-v3 --display uc1609 \
    --sketch "$root/code" >/dev/null 2>&1; then
  echo 'invalid Arduino platform/display pair was accepted' >&2
  exit 1
fi

grep -q 'build_system_app_bundle.py' "$hook"
grep -q 'build_system_app_bundle.py' \
  "$platform/tools/mk61-app-postbuild.ps1"
grep -q 'package_ui_font_licenses.py' "$hook"
grep -q 'package_ui_font_licenses.py' \
  "$platform/tools/mk61-app-postbuild.ps1"
for obsolete in focal basic wbmp markdown chip8; do
  test ! -e "$root/code/mk61_ide_${obsolete}_app.cpp"
done
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
  pwsh -NoLogo -NoProfile -File \
    "$platform/tools/mk61-app-postbuild.ps1" check-profile \
    -Platform mini-v3 -Display oled1602-ws0010 -Sketch "$root/code"

  # A Windows Store App Execution Alias is visible to Get-Command but exits
  # with 9009.  The PowerShell hook must use the working `py -3` launcher
  # instead and preserve its prefix argument for both probing and execution.
  launcher_dir="$work/python-launcher"
  launcher_log="$work/python-launcher.log"
  launcher_build="$work/python-launcher-build"
  mkdir -p "$launcher_dir" "$launcher_build"
  for alias in python python3; do
    printf '%s\n' '#!/usr/bin/env bash' 'exit 73' > "$launcher_dir/$alias"
    chmod +x "$launcher_dir/$alias"
  done
  printf '%s\n' \
    '#!/usr/bin/env bash' \
    'printf "%s\\n" "$*" >> "$MK61_TEST_PY_LOG"' \
    'test "$1" = -3 || exit 74' \
    'shift' \
    'exec "$MK61_TEST_REAL_PYTHON" "$@"' > "$launcher_dir/py"
  chmod +x "$launcher_dir/py"
  printf '%s\n' \
    'SECTIONS' \
    '{' \
    '  PROVIDE ( _end = . );' \
    '    *(.bss)' \
    '}' > "$work/variant.ld"
  MK61_TEST_PY_LOG="$launcher_log" \
  MK61_TEST_REAL_PYTHON="$(command -v python3)" \
  PATH="$launcher_dir:$PATH" \
    pwsh -NoLogo -NoProfile -File \
      "$platform/tools/mk61-app-postbuild.ps1" check-profile \
      -Platform mini-v3 -Display lcd1602-a00 -Sketch "$root/code" \
      -BuildPath "$launcher_build" -VariantLd "$work/variant.ld"
  test -s "$launcher_build/mk61-portable.ld"
  grep -q '^-3 --version$' "$launcher_log"
  grep -q '^-3 .*portable-layout.py ' "$launcher_log"

  # STM32's Windows platform passes compiler.cpp.cmd without `.exe`, even
  # though the packaged executable has that suffix.  Exercise the resolver
  # without requiring a Windows host or a complete firmware build.
  compiler_stub="$work/arm-none-eabi-g++.exe"
  : > "$compiler_stub"
  MK61_TEST_HOOK="$platform/tools/mk61-app-postbuild.ps1" \
  MK61_TEST_SKETCH="$root/code" \
  MK61_TEST_COMPILER="${compiler_stub%.exe}" \
    pwsh -NoLogo -NoProfile -Command '
      . $env:MK61_TEST_HOOK check-profile `
          -Platform mini-v3 -Display lcd1602-a00 `
          -Sketch $env:MK61_TEST_SKETCH
      $resolved = Resolve-Mk61Executable $env:MK61_TEST_COMPILER
      $expected = [IO.Path]::GetFullPath($env:MK61_TEST_COMPILER + ".exe")
      if ($resolved -ne $expected) {
          throw "extensionless ARM compiler did not resolve: $resolved"
      }
    '
fi

if [ "${MK61_RUN_ARDUINO_BOARD_INTEGRATION:-0}" = 1 ]; then
  command -v arduino-cli >/dev/null 2>&1 ||
    { echo 'arduino-cli is required for integration test' >&2; exit 1; }
  command -v pwsh >/dev/null 2>&1 ||
    { echo 'pwsh is required for System APP integration test' >&2; exit 1; }
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
  ln -s "$root/tools" "$shell_sketchbook/sketches/tools"
  ARDUINO_DIRECTORIES_USER="$shell_sketchbook" arduino-cli compile \
    --fqbn 'mk61:stm32:mk61_f401_app:mk61_platform=mini_v2,mk61_display=lcd_a00,mk61_focal=enabled,mk61_basic=enabled,mk61_documents=markdown,mk61_chip8=disabled,mk61_usb_screen=disabled,mk61_font_settings=disabled,mk61_explorer=enabled,mk61_math=core' \
    --build-path "$work/build" "$shell_sketchbook/sketches/code"

  bundle="$shell_sketchbook/sketches/binary/mk61s-M-mini-v2-lcd1602-a00-f401"
  resident="$bundle/mk61s-M-mini-v2-lcd1602-a00-f401.bin"
  resident_elf="$work/build/code.ino.elf"
  test -s "$resident"
  test -s "$resident_elf"
  "$root/tests/check_core_native_hot_paths_elf.sh" "$resident_elf"
  "$root/tests/check_no_resident_fmk_decoder_elf.sh" "$resident_elf"
  for app in FOCAL.APP BASIC.APP MARKDOWN.APP SETUP.APP; do
    file="$bundle/System/$app"
    test -s "$file"
    test "$(wc -c < "$file" | tr -d '[:space:]')" -le 20544
    test "$(od -An -tu1 -j12 -N1 "$file" | tr -d '[:space:]')" = 5
    test "$(od -An -tu1 -j15 -N1 "$file" | tr -d '[:space:]')" = 1
    test "$(od -An -tx1 -N8 "$file" | tr -d '[:space:]')" = \
      4d4b363141505000
  done
  for resource in HELP0.TXT HELP1.TXT; do test -s "$bundle/System/$resource"; done
  test ! -e "$bundle/System/WBMP.APP"
  test ! -e "$bundle/System/CHIP8.APP"
  test "$(od -An -tx1 -j56 -N2 "$bundle/System/MARKDOWN.APP" |
      tr -d '[:space:]')" = 5432

  direct_system="$work/direct-system"
  pwsh -NoLogo -NoProfile -File \
    "$root/system_apps/.tool/build.ps1" \
    -BuildPath "$work/build" \
    -OutputDirectory "$direct_system" \
    -Graphics 0 -UiFonts 0 -Focal 1 -Basic 1 -Wbmp 0 -Markdown 1 -Chip8 0
  for app in FOCAL.APP BASIC.APP MARKDOWN.APP SETUP.APP; do
    file="$direct_system/$app"
    cmp "$file" "$bundle/System/$app"
    case "$app" in
      FOCAL.APP) expected_kind=1 ;;
      BASIC.APP) expected_kind=2 ;;
      MARKDOWN.APP) expected_kind=6 ;;
      SETUP.APP) expected_kind=7 ;;
    esac
    test -s "$file"
    test "$(wc -c < "$file" | tr -d '[:space:]')" -le 20544
    test "$(od -An -tu1 -j14 -N1 "$file" | tr -d '[:space:]')" = \
      "$expected_kind"
    test "$(od -An -tu1 -j12 -N1 "$file" | tr -d '[:space:]')" = 5
    test "$(od -An -tu1 -j15 -N1 "$file" | tr -d '[:space:]')" = 1
  done
  for resource in HELP0.TXT HELP1.TXT; do cmp "$direct_system/$resource" "$bundle/System/$resource"; done
  test ! -e "$direct_system/WBMP.APP"
  test ! -e "$direct_system/CHIP8.APP"
  test "$(od -An -tx1 -j56 -N2 "$direct_system/MARKDOWN.APP" |
      tr -d '[:space:]')" = 5432

  mkdir -p "$work/build-all-options"
  ARDUINO_DIRECTORIES_USER="$shell_sketchbook" arduino-cli compile \
    --fqbn 'mk61:stm32:mk61_f401_app:mk61_platform=mini_v2,mk61_display=lcd_a00,mk61_focal=enabled,mk61_basic=enabled,mk61_documents=markdown,mk61_chip8=enabled,mk61_usb_screen=enabled,mk61_font_settings=enabled,mk61_explorer=enabled,mk61_math=core' \
    --build-path "$work/build-all-options" "$shell_sketchbook/sketches/code"
  for app in FOCAL.APP BASIC.APP MARKDOWN.APP CHIP8.APP SETUP.APP; do
    test -s "$bundle/System/$app"
    test "$(wc -c < "$bundle/System/$app" | tr -d '[:space:]')" -le 20544
  done
  test "$(od -An -tx1 -j56 -N2 "$bundle/System/CHIP8.APP" |
      tr -d '[:space:]')" = 4331

  mkdir -p "$work/build-disabled"
  ARDUINO_DIRECTORIES_USER="$shell_sketchbook" arduino-cli compile \
    --fqbn 'mk61:stm32:mk61_f401_app:mk61_platform=mini_v2,mk61_display=lcd_a00,mk61_focal=disabled,mk61_basic=disabled,mk61_documents=disabled,mk61_chip8=disabled,mk61_usb_screen=disabled,mk61_font_settings=disabled,mk61_explorer=enabled,mk61_math=core' \
    --build-path "$work/build-disabled" "$shell_sketchbook/sketches/code"
  for resource in SETUP.APP HELP0.TXT HELP1.TXT; do test -s "$bundle/System/$resource"; done
  for app in FOCAL.APP BASIC.APP WBMP.APP MARKDOWN.APP CHIP8.APP; do test ! -e "$bundle/System/$app"; done
  grep -q -- '-DMK61_ENABLE_FOCAL=0' "$bundle/build.flags"
  grep -q -- '-DMK61_ENABLE_TINYBASIC=0' "$bundle/build.flags"
  grep -q -- '-DMK61_ENABLE_WBMP_VIEWER=0' "$bundle/build.flags"
  grep -q -- '-DMK61_ENABLE_MARKDOWN_VIEWER=0' "$bundle/build.flags"
  grep -q -- '-DMK61_ENABLE_CHIP8=0' "$bundle/build.flags"

  mkdir -p "$work/build-classic"
  ARDUINO_DIRECTORIES_USER="$shell_sketchbook" arduino-cli compile \
    --fqbn 'mk61:stm32:mk61_f401_app:mk61_platform=classic_v2,mk61_display=uc1609,mk61_focal=enabled,mk61_basic=enabled,mk61_documents=markdown,mk61_chip8=enabled,mk61_usb_screen=disabled,mk61_font_settings=disabled,mk61_explorer=enabled,mk61_math=core' \
    --build-path "$work/build-classic" "$shell_sketchbook/sketches/code"
  classic_bundle="$shell_sketchbook/sketches/binary/mk61s-M-classic-v2-uc1609-f401"
  test -s "$classic_bundle/mk61s-M-classic-v2-uc1609-f401.bin"
  test -s "$classic_bundle/System/FOCAL.APP"
  test -s "$classic_bundle/System/BASIC.APP"
  test ! -e "$classic_bundle/System/WBMP.APP"
  test -s "$classic_bundle/System/MARKDOWN.APP"
  test -s "$classic_bundle/System/CHIP8.APP"
  grep -q -- '-DMK61_PORTABLE_UI_FONTS=1' "$classic_bundle/build.flags"
  for notice in LICENSE-Ark-Pixel.txt LICENSE-DejaVu.txt FONT-SOURCES.md; do
    test -s "$classic_bundle/licenses/ui-fonts/$notice"
  done

  mkdir -p "$work/build-classic-wbmp"
  ARDUINO_DIRECTORIES_USER="$shell_sketchbook" arduino-cli compile \
    --fqbn 'mk61:stm32:mk61_f401_app:mk61_platform=classic_v2,mk61_display=uc1609,mk61_focal=disabled,mk61_basic=disabled,mk61_documents=wbmp,mk61_chip8=disabled,mk61_usb_screen=disabled,mk61_font_settings=disabled,mk61_explorer=enabled,mk61_math=core' \
    --build-path "$work/build-classic-wbmp" "$shell_sketchbook/sketches/code"
  test -s "$classic_bundle/System/WBMP.APP"
  test ! -e "$classic_bundle/System/MARKDOWN.APP"
fi

printf 'arduino_board_tests: ok\n'

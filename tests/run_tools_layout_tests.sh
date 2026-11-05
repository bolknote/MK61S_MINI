#!/usr/bin/env bash
set -euo pipefail

root="$(cd "$(dirname "$0")/.." && pwd)"
actual="$(
  find "$root/tools" -mindepth 1 -maxdepth 1 -type f ! -name '.*' \
    -exec basename {} \; | LC_ALL=C sort
)"
expected="$(
  printf '%s\n' \
    README.md \
    build-gcc.cmd \
    build-portable-app.ps1 \
    build-system-app-bundle.ps1 \
    build_f401_bundle.sh \
    build_fmk_font.sh \
    build_fmk_from_ui_atlas.py \
    build_mk61_program_pack.sh \
    build_picocalc.py \
    build_picocalc_apps.py \
    build_portable_app.py \
    build_system_app_bundle.py \
    font_preview_study.py \
    install_arduino_dependencies.ps1 \
    install_gcc_dependencies.ps1 \
    install_gcc_dependencies.py \
    mk61-arduino-board.cmd \
    mk61-firmware.cmd \
    mkc.cmd \
    package_picocalc.py \
    program_pack.py \
    program_bundle.py \
    sync_picocalc_clock.py \
    vfat_diagnostic.py | LC_ALL=C sort
)"

if [[ "$actual" != "$expected" ]]; then
  printf 'Unexpected public tools layout.\nExpected:\n%s\nActual:\n%s\n' \
    "$expected" "$actual" >&2
  exit 1
fi

test -f "$root/tools/.mk61-app/mk61_module_pack.cpp"
test -f "$root/tools/.mk61-app/mk61_module.ld"
test -f "$root/tools/.mk61-app/build.ps1"
test -f "$root/tools/.mk61-app/Mk61AppPacker.cs"
test -f "$root/tools/.mk61-app/mk61-module-pack.ps1"
test -f "$root/tools/.mk61-app/build-terminal-help.ps1"
test -f "$root/tools/.mk61-gcc/portable-layout.ps1"
test -f "$root/tools/.fmk-font/package-ui-font-licenses.ps1"
test -f "$root/tools/.fmk-font/fmk_font.cpp"
test -f "$root/dev/lib/.mk61-firmware-seal/mk61_firmware_seal.cpp"
test ! -e "$root/tools/fmk_font"
test ! -e "$root/tools/mk61_module_pack"

# programs/Fonts is copied to the public C6 /Fonts directory. Keep host-side
# documentation and notices out of the device filesystem: only loadable FMK
# assets and the folder's reviewed Explorer icon belong here.
unexpected_font_assets="$(
  find "$root/programs/Fonts" -mindepth 1 -maxdepth 1 \
    ! \( -type f \( -name '*.FMK' -o -name 'autoexec.wbmp' \) \) -print
)"
if [[ -n "$unexpected_font_assets" ]]; then
  printf 'Unexpected content in programs/Fonts:\n%s\n' \
    "$unexpected_font_assets" >&2
  exit 1
fi

# README.markdown is intentionally visible on GitHub but ignored by the
# programs-to-device deployment. A README.md here would be copied to MK61s.
unexpected_device_readmes="$(
  find "$root/programs" -type f -name 'README.md' -print
)"
if [[ -n "$unexpected_device_readmes" ]]; then
  printf 'README.md would be copied to MK61s; use README.markdown instead:\n%s\n' \
    "$unexpected_device_readmes" >&2
  exit 1
fi

printf 'tools_layout_tests: ok\n'

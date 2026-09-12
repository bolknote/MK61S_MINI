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
    build_f401_bundle.sh \
    build_fmk_font.sh \
    build_fmk_from_ui_atlas.py \
    build_mk61_module_pack.sh \
    build_portable_app.py \
    build-gcc.cmd \
    font_preview_study.py \
    generate_eliza_doctor.py \
    generate_ui_fonts.py \
    install_arduino_dependencies.ps1 \
    mk61-arduino-board.cmd \
    mk61-firmware.cmd \
    mkc.cmd \
    release-contract.json \
    release_contract.py \
    vfat_diagnostic.py \
    seal-firmware.ps1 \
    seal-firmware.sh |
    LC_ALL=C sort
)"

if [[ "$actual" != "$expected" ]]; then
  printf 'Unexpected public tools layout.\nExpected:\n%s\nActual:\n%s\n' \
    "$expected" "$actual" >&2
  exit 1
fi

test -f "$root/tools/.mk61-app/mk61_module_pack.cpp"
test -f "$root/tools/.mk61-app/mk61_module.ld"
test -f "$root/tools/.mk61-app/build.ps1"
test -f "$root/tools/.fmk-font/fmk_font.cpp"
test -f "$root/tools/.mk61-firmware-seal/mk61_firmware_seal.cpp"
test ! -e "$root/tools/fmk_font"
test ! -e "$root/tools/mk61_module_pack"

# programs/Fonts is copied to the public C5 /Fonts directory. Keep host-side
# documentation and notices out of the device filesystem: only loadable FMK
# assets belong here.
unexpected_font_assets="$(
  find "$root/programs/Fonts" -mindepth 1 -maxdepth 1 \
    ! \( -type f -name '*.FMK' \) -print
)"
if [[ -n "$unexpected_font_assets" ]]; then
  printf 'Unexpected non-FMK content in programs/Fonts:\n%s\n' \
    "$unexpected_font_assets" >&2
  exit 1
fi

printf 'tools_layout_tests: ok\n'

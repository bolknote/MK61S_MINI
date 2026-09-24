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
    build_mk61_program_pack.sh \
    build_portable_app.py \
    build_system_app_bundle.py \
    convert_fmk1_to_fmk2.py \
    build-gcc.cmd \
    font_preview_study.py \
    generate_eliza_doctor.py \
    generate_highnoon_font.py \
    generate_ui_fonts.py \
    install_arduino_dependencies.ps1 \
    m8_codec.py \
    mk61-arduino-board.cmd \
    mk61-firmware.cmd \
    mkc.cmd \
    program_pack.py \
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

# programs/Fonts is copied to the public C6 /Fonts directory. Keep host-side
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

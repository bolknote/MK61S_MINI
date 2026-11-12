#!/usr/bin/env bash
set -euo pipefail

root="$(cd "$(dirname "$0")/.." && pwd)"
actual="$(
  find "$root/tools" -mindepth 1 -maxdepth 1 -type f ! -name '.*' \
    -exec basename {} \; | LC_ALL=C sort
)"
expected="$(printf '%s\n' README.md games.cmd mk61-firmware.cmd mkc.cmd | LC_ALL=C sort)"

if [[ "$actual" != "$expected" ]]; then
  printf 'Only README.md and the games.cmd, mkc.cmd and mk61-firmware.cmd launchers belong in tools/.\n' >&2
  diff <(printf '%s\n' "$expected") <(printf '%s\n' "$actual") >&2 || true
  exit 1
fi

for directory in mkc firmware/cli firmware/stm32 firmware/picocalc firmware/dfu \
    apps/portable apps/system apps/packer programs fonts games arduino/compat device; do
  test -d "$root/tools/$directory"
done
test -f "$root/tools/apps/packer/mk61_module_pack.cpp"
test -f "$root/tools/apps/packer/mk61_module.ld"
test -f "$root/tools/apps/packer/build.ps1"
test -f "$root/tools/apps/packer/Mk61AppPacker.cs"
test -f "$root/tools/apps/system/build-terminal-help.ps1"
test -f "$root/tools/fonts/package-ui-font-licenses.ps1"
test -f "$root/tools/fonts/fmk_font.cpp"
test -f "$root/tools/games/catalog.json"
test -f "$root/tools/games/games.ps1"
test -f "$root/tools/games/games.sh"
test -f "$root/tools/games/manager.py"
test -f "$root/dev/lib/.mk61-firmware-seal/mk61_firmware_seal.cpp"
test ! -e "$root/tools/fmk_font"
test ! -e "$root/tools/mk61_module_pack"
for retired in .mkc .mk61-firmware .mk61-gcc .mk61-dfu .mk61-app .fmk-font .mk61-arduino-board \
    elite race runner turochamp; do
  test ! -e "$root/tools/$retired"
done

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

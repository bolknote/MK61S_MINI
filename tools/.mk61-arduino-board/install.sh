#!/usr/bin/env bash

set -euo pipefail

script_dir="$(cd "$(dirname "$0")" && pwd)"
project_root="$(cd "$script_dir/../.." && pwd)"
source_platform="$script_dir/hardware/mk61/stm32"
font_settings_compat_source="$script_dir/font-settings-compat.boards.local.txt"
sketchbook=${MK61_ARDUINO_SKETCHBOOK:-}
check_only=0

usage() {
  cat <<'EOF'
Install the "MK61s F401 + APP" and "MK61s F411 + APP" boards into an Arduino IDE sketchbook.

Usage:
  tools/mk61-arduino-board.cmd [--sketchbook DIR]
  tools/mk61-arduino-board.cmd --check [--sketchbook DIR]

Options:
  --sketchbook DIR  Arduino IDE sketchbook directory
  --check           check that the current board package is installed
  -h, --help        show this help

The installer does not install Arduino CLI.  The STM32 MCU based boards core
2.12.0 must be installed from Arduino IDE's Boards Manager.  The MK61s board
itself appears in Board Selector / Tools > Board, not in Boards Manager.
EOF
}

die() {
  printf 'MK61s Arduino board: %s\n' "$*" >&2
  exit 1
}

while [ "$#" -gt 0 ]; do
  case "$1" in
    --sketchbook)
      [ "$#" -ge 2 ] && [ -n "$2" ] ||
        die '--sketchbook requires a directory'
      sketchbook=$2
      shift 2
      ;;
    --check)
      check_only=1
      shift
      ;;
    -h|--help)
      usage
      exit 0
      ;;
    *)
      die "unknown option: $1"
      ;;
  esac
done

if [ -z "$sketchbook" ]; then
  case "$(uname -s 2>/dev/null || true)" in
    Darwin) sketchbook="$HOME/Documents/Arduino" ;;
    *) sketchbook="$HOME/Arduino" ;;
  esac
fi

target="$sketchbook/hardware/mk61/stm32"
font_settings_compat_target="$target/boards.local.txt"

# Arduino IDE persists the complete FQBN per sketch.  If an installed board is
# being upgraded, that FQBN may still contain the removed
# mk61_font_settings=disabled/enabled option.  Preserve a local compatibility
# menu only for upgrades; clean installations must not expose the obsolete
# setting.
install_font_settings_compat=0
if [ -f "$target/boards.txt" ] ||
   { [ -f "$font_settings_compat_target" ] &&
     grep -Fq '# MK61_FONT_SETTINGS_COMPAT_BEGIN' \
       "$font_settings_compat_target"; }; then
  install_font_settings_compat=1
fi

install_legacy_font_settings_menu() {
  [ "$install_font_settings_compat" -eq 1 ] || return 0
  if [ -f "$font_settings_compat_target" ] &&
     grep -Fq '# MK61_FONT_SETTINGS_COMPAT_BEGIN' \
       "$font_settings_compat_target"; then
    return 0
  fi
  if [ -s "$font_settings_compat_target" ]; then
    printf '\n' >> "$font_settings_compat_target"
    cat "$font_settings_compat_source" >> "$font_settings_compat_target"
  else
    cp "$font_settings_compat_source" "$font_settings_compat_target"
  fi
}

platform_installed() {
  [ -f "$target/boards.txt" ] &&
    [ -f "$target/platform.txt" ] &&
    [ -f "$target/tools/mk61-app-postbuild.sh" ] &&
    [ -f "$target/tools/mk61-app-postbuild.ps1" ] &&
    [ -f "$target/tools/mk61-app-upload.ps1" ] &&
    [ -f "$target/tools/mk61_firmware_seal.cpp" ] &&
    [ -f "$target/tools/resident_firmware_format.hpp" ] &&
    [ -f "$target/tools/rust_types.h" ] &&
    [ -f "$target/tools/seal-firmware.ps1" ] &&
    [ -f "$target/tools/seal-firmware-elf.py" ] &&
    [ -f "$target/tools/mk61_module.ld" ]
}

platform_current() {
  cmp -s "$source_platform/boards.txt" "$target/boards.txt" &&
    cmp -s "$source_platform/platform.txt" "$target/platform.txt" &&
    cmp -s "$source_platform/tools/mk61_module.ld" \
      "$target/tools/mk61_module.ld" &&
    cmp -s "$source_platform/tools/mk61-app-postbuild.sh" \
      "$target/tools/mk61-app-postbuild.sh" &&
    cmp -s "$source_platform/tools/mk61-app-postbuild.ps1" \
      "$target/tools/mk61-app-postbuild.ps1" &&
    cmp -s "$source_platform/tools/mk61-app-upload.ps1" \
      "$target/tools/mk61-app-upload.ps1" &&
    cmp -s "$project_root/tools/.mk61-firmware-seal/mk61_firmware_seal.cpp" \
      "$target/tools/mk61_firmware_seal.cpp" &&
    cmp -s "$project_root/code/resident_firmware_format.hpp" \
      "$target/tools/resident_firmware_format.hpp" &&
    cmp -s "$project_root/code/rust_types.h" \
      "$target/tools/rust_types.h" &&
    cmp -s "$project_root/tools/seal-firmware.ps1" \
      "$target/tools/seal-firmware.ps1" &&
    cmp -s "$project_root/tools/seal-firmware-elf.py" \
      "$target/tools/seal-firmware-elf.py"
}

if [ "$check_only" -eq 1 ]; then
  if platform_installed; then
    if ! platform_current; then
      printf 'MK61s Arduino boards are installed but stale in:\n  %s\n' \
        "$target" >&2
      printf '%s\n' \
        'Run tools/mk61-arduino-board.cmd without --check, then restart Arduino IDE.' >&2
      exit 1
    fi
    printf 'MK61s F401/F411 boards are installed in:\n  %s\n' "$target"
    exit 0
  fi
  printf 'MK61s F401/F411 boards are not installed in:\n  %s\n' "$target" >&2
  exit 1
fi

[ -f "$source_platform/boards.txt" ] &&
  [ -f "$source_platform/platform.txt" ] &&
  [ -f "$font_settings_compat_source" ] &&
  [ -f "$project_root/tools/.mk61-firmware-seal/mk61_firmware_seal.cpp" ] &&
  [ -f "$project_root/code/resident_firmware_format.hpp" ] &&
  [ -f "$project_root/code/rust_types.h" ] &&
  [ -f "$project_root/tools/seal-firmware.ps1" ] &&
  [ -f "$project_root/tools/seal-firmware-elf.py" ] ||
  die 'the board package is incomplete'

mkdir -p "$target/tools"
cp "$source_platform/boards.txt" "$target/boards.txt"
cp "$source_platform/platform.txt" "$target/platform.txt"
cp "$source_platform/tools/mk61_module.ld" \
   "$target/tools/mk61_module.ld"
cp "$source_platform/tools/mk61-app-postbuild.sh" \
   "$target/tools/mk61-app-postbuild.sh"
cp "$source_platform/tools/mk61-app-postbuild.ps1" \
   "$target/tools/mk61-app-postbuild.ps1"
cp "$source_platform/tools/mk61-app-upload.ps1" \
   "$target/tools/mk61-app-upload.ps1"
cp "$project_root/tools/.mk61-firmware-seal/mk61_firmware_seal.cpp" \
   "$target/tools/mk61_firmware_seal.cpp"
cp "$project_root/code/resident_firmware_format.hpp" \
   "$target/tools/resident_firmware_format.hpp"
cp "$project_root/code/rust_types.h" \
   "$target/tools/rust_types.h"
cp "$project_root/tools/seal-firmware.ps1" \
   "$target/tools/seal-firmware.ps1"
cp "$project_root/tools/seal-firmware-elf.py" \
   "$target/tools/seal-firmware-elf.py"
chmod +x "$target/tools/mk61-app-postbuild.sh"
install_legacy_font_settings_menu

platform_installed && platform_current ||
  die "installed board verification failed: $target"

printf 'MK61s F401/F411 boards installed in:\n  %s\n' "$target"
printf 'Verified uploader: mk61Upload (DFU + automatic /System install).\n'
if [ "$install_font_settings_compat" -eq 1 ]; then
  printf '%s\n' \
    'Accepted obsolete Arduino IDE font options saved by an earlier installation.'
fi
printf 'Restart Arduino IDE, then select MK61s F401 + APP or MK61s F411 + APP.\n'
printf 'STM32 MCU based boards core 2.12.0 is required.\n'

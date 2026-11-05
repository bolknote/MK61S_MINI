#!/usr/bin/env bash
set -euo pipefail
script_dir="$(cd "$(dirname "$0")" && pwd)"
project_root="$(cd "$script_dir/../.." && pwd)"
sketchbook=${MK61_ARDUINO_SKETCHBOOK:-}
toolchain=${MK61_ARDUINO_TOOLCHAIN:-${MK61_GCC_TOOLCHAIN:-}}
check_only=0
usage() {
  cat <<'HELP'
Install the "MK61s F401 + APP" and "MK61s F411 + APP" native Arduino IDE boards.
Usage: tools/mk61-arduino-board.cmd [--sketchbook DIR] [--toolchain DIR] [--check]
The board uses the project's runtime and SDK, without STM32 Core or Arduino libraries.
The installer does not install Arduino CLI. The MK61s board is not in Boards Manager;
it appears in Board Selector / Tools > Board.
Compatible GNU Arm GCC in Arduino15 is reused before downloading the pinned
compiler. --toolchain or MK61_ARDUINO_TOOLCHAIN / MK61_GCC_TOOLCHAIN overrides it.
HELP
}
while [ "$#" -gt 0 ]; do
  case "$1" in
    --sketchbook|--toolchain)
      [ "$#" -ge 2 ] && [ -n "$2" ] || { printf '%s requires a directory\n' "$1" >&2; exit 2; }
      if [ "$1" = --sketchbook ]; then sketchbook=$2; else toolchain=$2; fi
      shift 2 ;;
    --check) check_only=1; shift ;;
    -h|--help) usage; exit 0 ;;
    *) printf 'unknown option: %s\n' "$1" >&2; exit 2 ;;
  esac
done
if [ -z "$sketchbook" ]; then
  case "$(uname -s)" in Darwin) sketchbook="$HOME/Documents/Arduino" ;; *) sketchbook="$HOME/Arduino" ;; esac
fi
target="$sketchbook/hardware/mk61/stm32"
source_platform="$script_dir/hardware/mk61/stm32"
font_settings_compat_source="$script_dir/font-settings-compat.boards.local.txt"
font_settings_compat_target="$target/boards.local.txt"
package_version() {
  if [ -f "$1/platform.txt" ]; then sed -n 's/^version=//p' "$1/platform.txt" | tr -d '\r';
  else printf '%s\n' 'not installed / unknown'; fi
}
source_version="$(package_version "$source_platform")"
install_font_settings_compat=0
[ ! -f "$target/boards.txt" ] || install_font_settings_compat=1
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

if [ "$check_only" -eq 1 ]; then
  printf 'MK61s board package: installed %s; project %s\n' "$(package_version "$target")" "$source_version"
  if ! python3 "$script_dir/payload.py" check --project "$project_root" --target "$target"; then
    printf 'MK61s Arduino boards are installed but stale or incomplete in:\n  %s\n' "$target" >&2
    printf 'Close Arduino IDE, run:\n  "%s/tools/mk61-arduino-board.cmd" --sketchbook "%s"\nThen restart Arduino IDE.\n' "$project_root" "$sketchbook" >&2
    exit 1
  fi
else
  arguments=(install --project "$project_root" --target "$target")
  [ -z "$toolchain" ] || arguments+=(--toolchain "$toolchain")
  python3 "$script_dir/payload.py" "${arguments[@]}"
  install_legacy_font_settings_menu
fi
printf 'MK61s F401/F411 boards are installed in:\n  %s\n' "$target"
printf 'MK61s board package version: %s\n' "$source_version"
printf 'Verified uploader: mk61Upload (standalone DFU + automatic Windows /System install).\n'
if [ "$install_font_settings_compat" -eq 1 ]; then
  printf '%s\n' 'Accepted obsolete Arduino IDE font options saved by an earlier installation.'
fi
printf 'Restart Arduino IDE, then select MK61s F401 + APP (%s) or MK61s F411 + APP (%s).\n' "$source_version" "$source_version"
printf '%s\n' 'Runtime and header SDK belong to MK61s; STM32 Core is not required.'

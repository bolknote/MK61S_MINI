#!/usr/bin/env bash

set -euo pipefail

script_dir="$(cd "$(dirname "$0")" && pwd)"
source_platform="$script_dir/hardware/mk61/stm32"
sketchbook=${MK61_ARDUINO_SKETCHBOOK:-}
check_only=0

usage() {
  cat <<'EOF'
Install the "MK61s F401 + APP" board into an Arduino IDE sketchbook.

Usage:
  tools/mk61-arduino-board.cmd [--sketchbook DIR]
  tools/mk61-arduino-board.cmd --check [--sketchbook DIR]

Options:
  --sketchbook DIR  Arduino IDE sketchbook directory
  --check           only check whether the board is already installed
  -h, --help        show this help

The installer does not install Arduino CLI.  The STM32 MCU based boards core
2.12.0 must be installed from Arduino IDE's Boards Manager.
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

platform_installed() {
  [ -f "$target/boards.txt" ] &&
    [ -f "$target/platform.txt" ] &&
    [ -f "$target/tools/mk61-app-postbuild.sh" ] &&
    [ -f "$target/tools/mk61-app-postbuild.ps1" ] &&
    [ -f "$target/tools/mk61_module.ld" ]
}

if [ "$check_only" -eq 1 ]; then
  if platform_installed; then
    printf 'MK61s F401 + APP is installed in:\n  %s\n' "$target"
    exit 0
  fi
  printf 'MK61s F401 + APP is not installed in:\n  %s\n' "$target" >&2
  exit 1
fi

[ -f "$source_platform/boards.txt" ] &&
  [ -f "$source_platform/platform.txt" ] ||
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
chmod +x "$target/tools/mk61-app-postbuild.sh"

printf 'MK61s F401 + APP installed in:\n  %s\n' "$target"
printf 'Restart Arduino IDE, then select Tools > Board > MK61s F401 + APP.\n'
printf 'STM32 MCU based boards core 2.12.0 is required.\n'

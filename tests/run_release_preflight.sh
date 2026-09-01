#!/usr/bin/env bash
set -euo pipefail

root="$(cd "$(dirname "$0")/.." && pwd)"
preflight_root="$(mktemp -d "${TMPDIR:-/tmp}/mk61-release-preflight.XXXXXX")"
cleanup() {
  rm -rf "$preflight_root"
}
trap cleanup EXIT HUP INT TERM

# Fail on missing pinned firmware dependencies before starting the long host
# suite. The actual F411 matrix repeats this check before compiling.
"$root/tests/run_f411_release_matrix.sh" --check-dependencies

printf '\n=== CI-strict host suite ===\n'
"$root/tests/run_ci_strict.sh"

printf '\n=== Strict F411 release matrix ===\n'
f411_build_root="$preflight_root/f411-build"
MK61_F411_BUILD_ROOT="$f411_build_root" \
MK61_FIRMWARE_OUTPUT_DIR="$preflight_root/firmware" \
MK61_FIRMWARE_TAG=preflight \
  "$root/tests/run_f411_release_matrix.sh"

printf '\n=== F411 USB-preserving STOP production images ===\n'
MK61_F411_USB_SUSPEND_BUILD_ROOT="$preflight_root/f411-usb-suspend" \
  "$root/tests/run_f411_usb_suspend_compile_check.sh"

for artifact in \
  mk61s-M-lcd1602-a00-f411 \
  mk61s-M-lcd1602-a02-f411 \
  mk61s-M-mini-v3-oled1602-ws0010-f411 \
  mk61s-M-mini-v2-lcd1602-a00-f411 \
  mk61s-M-mini-v2-lcd1602-a02-f411 \
  mk61s-M-classic-v2-uc1609-f411 \
  mk61s-M-classic-v3-uc1609-f411 \
  mk61s-M-40th-f411; do
  [[ -s "$preflight_root/firmware/$artifact-preflight.bin" ]] || {
    printf 'Missing F411 preflight artifact: %s-preflight.bin\n' \
      "$artifact" >&2
    exit 1
  }
  "$root/tools/seal-firmware.sh" check --max-size 524288 \
    "$preflight_root/firmware/$artifact-preflight.bin"
done

printf '\n=== Arduino F401 Classic V3 UC1609 ===\n'
MK61_F401_UC1609_BUILD_ROOT="$preflight_root/f401-arduino-uc1609" \
  "$root/tests/run_f401_uc1609_compile_check.sh"
"$root/tools/seal-firmware.sh" check --max-size 262144 \
  "$preflight_root/f401-arduino-uc1609/build/mk61s-M.ino.bin"

printf '\n=== F401 release profiles ===\n'
f401_build_root="$preflight_root/f401-build"
f401_output="$preflight_root/firmware"
for profile in mini-v3-a00 mini-v3-ws0010 mini-v2-a00 classic-v3; do
  printf '\nF401 %s\n' "$profile"
  MK61_COLOR=never "$root/tools/build-gcc.cmd" \
    -Profile "$profile" \
    -Focal 1 \
    -Basic 1 \
    -Wbmp 0 \
    -Markdown 1 \
    -Chip8 0 \
    -UsbScreen 0 \
    -MathBackend 1 \
    -Lto 1 \
    -BuildRoot "$f401_build_root" \
    -OutputDirectory "$f401_output"
  "$root/tests/check_global_constructors.sh" \
    "$f401_build_root/$profile/resident.elf"
  "$root/tests/check_early_dfu_elf.sh" \
    "$f401_build_root/$profile/resident.elf"
  "$root/tests/check_usb_suspend_elf.sh" --disabled \
    "$f401_build_root/$profile/resident.elf"
done

printf '\n=== F401 WS0010 capability cross-matrix ===\n'
for case_id in a00-usb ws-usb ws-graphics ws-usb-graphics; do
  profile=mini-v3-ws0010
  usb=0
  graphics=0
  case "$case_id" in
    a00-usb) profile=mini-v3-a00; usb=1 ;;
    ws-usb) usb=1 ;;
    ws-graphics) graphics=1 ;;
    ws-usb-graphics) usb=1; graphics=1 ;;
  esac
  MK61_COLOR=never "$root/tools/build-gcc.cmd" \
    -Profile "$profile" \
    -Focal 0 -Basic 0 -Wbmp 0 -Markdown 0 -Chip8 0 \
    -UsbScreen "$usb" \
    -Ws0010Graphics "$graphics" \
    -MathBackend 1 -Lto 1 \
    -BuildRoot "$preflight_root/f401-$case_id" \
    -OutputDirectory "$preflight_root/output-$case_id"
  "$root/tests/check_global_constructors.sh" \
    "$preflight_root/f401-$case_id/$profile/resident.elf"
  if [[ "$profile" == mini-v3-ws0010 ]]; then
    # F401 may explicitly compile the laboratory GDRAM writer, but the
    # production-qualified readback/terminal path belongs to F411 only.  This
    # also protects the tight 256 KiB ws-usb-graphics image from accidental
    # qualification-code growth.
    "$root/tests/check_ws0010_graphics_elf.sh" --disabled \
      "$preflight_root/f401-$case_id/$profile/resident.elf"
  fi
done

size_tool="$(awk -F= '/^CMAKE_SIZE:FILEPATH=/ {print $2; exit}' \
  "$f401_build_root/mini-v3-a00/CMakeCache.txt")"
"$root/tests/check_release_ws0010_ram.sh" "$size_tool" \
  "$f401_build_root/mini-v3-a00/resident.elf" \
  "$f401_build_root/mini-v3-ws0010/resident.elf" \
  "$f411_build_root/build-lcd1602-a00/mk61s-M.ino.elf" \
  "$f411_build_root/build-oled1602-ws0010/mk61s-M.ino.elf" \
  "$preflight_root/f401-a00-usb/mini-v3-a00/resident.elf" \
  "$preflight_root/f401-ws-usb/mini-v3-ws0010/resident.elf" \
  "$preflight_root/f401-ws-usb-graphics/mini-v3-ws0010/resident.elf"

for bundle in \
  mk61s-M-mini-v3-lcd1602-a00-f401 \
  mk61s-M-mini-v3-oled1602-ws0010-f401 \
  mk61s-M-mini-v2-lcd1602-a00-f401 \
  mk61s-M-classic-v3-uc1609-f401; do
  bundle_root="$f401_output/$bundle"
  "$root/tools/seal-firmware.sh" check --max-size 262144 \
    "$bundle_root/$bundle.bin"
  for artifact in \
    "$bundle.bin" \
    build.flags \
    build.apps \
    System/FOCAL.APP \
    System/BASIC.APP \
    System/MARKDOWN.APP; do
    [[ -s "$bundle_root/$artifact" ]] || {
      printf 'Missing F401 preflight artifact: %s/%s\n' \
        "$bundle" "$artifact" >&2
      exit 1
    }
  done
  for disabled in System/WBMP.APP System/CHIP8.APP; do
    [[ ! -e "$bundle_root/$disabled" ]] || {
      printf 'Unexpected disabled F401 APP: %s/%s\n' \
        "$bundle" "$disabled" >&2
      exit 1
    }
  done
  for app in \
    System/FOCAL.APP \
    System/BASIC.APP \
    System/MARKDOWN.APP; do
    codec=$(od -An -tu1 -j15 -N1 "$bundle_root/$app" |
      tr -d '[:space:]')
    [[ "$codec" == 1 ]] || {
      printf 'F401 preflight APP is not ZX0: %s/%s\n' \
        "$bundle" "$app" >&2
      exit 1
    }
  done
done

printf '\nRelease preflight: OK\n'

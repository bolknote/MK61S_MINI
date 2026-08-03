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
MK61_FIRMWARE_OUTPUT_DIR="$preflight_root/firmware" \
MK61_FIRMWARE_TAG=preflight \
  "$root/tests/run_f411_release_matrix.sh"

for artifact in \
  mk61s-M-lcd1602-a00-f411 \
  mk61s-M-lcd1602-a02-f411 \
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
done

printf '\n=== Arduino F401 Classic V3 UC1609 ===\n'
MK61_F401_UC1609_BUILD_ROOT="$preflight_root/f401-arduino-uc1609" \
  "$root/tests/run_f401_uc1609_compile_check.sh"

printf '\n=== F401 release profiles ===\n'
f401_build_root="$preflight_root/f401-build"
f401_output="$preflight_root/firmware"
for profile in mini-v3-a00 mini-v2-a00 classic-v3; do
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
done

for bundle in \
  mk61s-M-mini-v3-lcd1602-a00-f401 \
  mk61s-M-mini-v2-lcd1602-a00-f401 \
  mk61s-M-classic-v3-uc1609-f401; do
  bundle_root="$f401_output/$bundle"
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

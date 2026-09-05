#!/usr/bin/env bash
set -euo pipefail

root="$(cd "$(dirname "$0")/.." && pwd)"
contract="$root/tools/release_contract.py"
preflight_root="$(mktemp -d "${TMPDIR:-/tmp}/mk61-release-preflight.XXXXXX")"
cleanup() {
  rm -rf "$preflight_root"
}
trap cleanup EXIT HUP INT TERM

# Fail on missing pinned firmware dependencies before starting the long host
# suite. The actual F411 matrix repeats this check before compiling.
"$root/tests/run_f411_release_matrix.sh" --check-dependencies
python3 "$contract" validate

printf '\n=== CI-strict host suite ===\n'
"$root/tests/run_ci_strict.sh"

printf '\n=== Strict F411 release matrix ===\n'
f411_build_root="$preflight_root/f411-build"
firmware_output="$preflight_root/firmware"
MK61_F411_BUILD_ROOT="$f411_build_root" \
MK61_FIRMWARE_OUTPUT_DIR="$firmware_output" \
MK61_FIRMWARE_TAG=preflight \
  "$root/tests/run_f411_release_matrix.sh"

printf '\n=== F411 USB-preserving STOP production images ===\n'
MK61_F411_USB_SUSPEND_BUILD_ROOT="$preflight_root/f411-usb-suspend" \
  "$root/tests/run_f411_usb_suspend_compile_check.sh"

while IFS=$'\t' read -r \
    _case_id _profile _optimization _defines artifact flash_capacity \
    _headroom _ram_capacity _ram_limit _stack _product publish _rest; do
  [[ "$publish" == 1 ]] || continue
  image="$firmware_output/$artifact-preflight.bin"
  [[ -s "$image" ]] || {
    printf 'Missing F411 preflight artifact: %s-preflight.bin\n' \
      "$artifact" >&2
    exit 1
  }
  "$root/tools/seal-firmware.sh" check --max-size "$flash_capacity" "$image"
done < <(python3 "$contract" cases --group f411-release --format tsv)

printf '\n=== Arduino F401 Classic V3 UC1609 ===\n'
MK61_F401_UC1609_BUILD_ROOT="$preflight_root/f401-arduino-uc1609" \
  "$root/tests/run_f401_uc1609_compile_check.sh"

printf '\n=== Contract-driven F401 product and capability matrix ===\n'
MK61_F401_MATRIX_ROOT="$preflight_root/f401-matrix" \
MK61_F411_MATRIX_ROOT="$f411_build_root" \
MK61_FIRMWARE_OUTPUT_DIR="$firmware_output" \
  "$root/tests/run_f401_release_matrix.sh"

python3 "$contract" aggregate-reports --reports-below "$preflight_root" \
  --output-prefix "$firmware_output/RESOURCE_REPORT"

printf '\nRelease preflight: OK\n'

#!/usr/bin/env bash
set -euo pipefail

root="$(cd "$(dirname "$0")/.." && pwd)"
matrix="$root/tests/run_f411_release_matrix.sh"

bash -n "$matrix"

# The matrix is a release gate, not a synthetic maximum-code-size exercise.
# Keep LTO size-oriented and retain explicit growth room in every F411 image.
grep -Fq 'usb=CDCgen,opt=oslto' "$matrix"
if grep -Fq 'usb=CDCgen,opt=o3lto' "$matrix"; then
  printf 'F411 release matrix must not use the unsafe O3+LTO profile\n' >&2
  exit 1
fi
grep -Eq '^minimum_flash_headroom=[1-9][0-9]*$' "$matrix"
grep -Fq 'unsafe Flash headroom' "$matrix"
grep -Fq 'MK61_REQUIRE_RESIDENT_CRC=1' "$matrix"
grep -Fq 'seal-firmware.sh" seal --max-size 524288' "$matrix"
grep -Fq 'seal-firmware.sh" check --max-size 524288' "$matrix"

printf 'f411_release_policy_tests: ok\n'

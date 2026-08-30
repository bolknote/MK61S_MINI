#!/usr/bin/env bash
set -euo pipefail

root="$(cd "$(dirname "$0")/.." && pwd)"
work="$(mktemp -d "${TMPDIR:-/tmp}/mk61-firmware-seal.XXXXXX")"
trap 'rm -rf "$work"' EXIT
cxx="${CXX:-clang++}"
sanitizer_flags=()
if [[ "${MK61_TEST_SANITIZERS:-0}" == "1" ]]; then
  sanitizer_flags=(-fsanitize=address,undefined -fno-omit-frame-pointer)
fi

"$cxx" -std=c++17 -Wall -Wextra -Werror -pedantic \
  "${sanitizer_flags[@]}" -I"$root/code" \
  "$root/tools/.mk61-firmware-seal/mk61_firmware_seal.cpp" \
  -o "$work/seal"
"$cxx" -std=c++17 -Wall -Wextra -Werror -pedantic \
  "${sanitizer_flags[@]}" -I"$root/code" \
  "$root/tests/resident_firmware_fixture.cpp" \
  -o "$work/fixture"

"$work/fixture" "$work/unsealed.bin"
if "$work/seal" check "$work/unsealed.bin" >/dev/null 2>&1; then
  echo 'firmware sealer accepted an unsealed image' >&2
  exit 1
fi
"$work/seal" seal "$work/unsealed.bin" "$work/sealed.bin" > "$work/seal.log"
"$work/seal" check "$work/sealed.bin" > "$work/check.log"
grep -q 'size=512 footer=128' "$work/seal.log"
grep -q 'crc=' "$work/check.log"
dd if="$work/sealed.bin" of="$work/crc-field.bin" bs=1 skip=148 count=4 \
  status=none
dd if="$work/sealed.bin" of="$work/build-field.bin" bs=1 skip=152 count=4 \
  status=none
cmp "$work/crc-field.bin" "$work/build-field.bin"

cp "$work/sealed.bin" "$work/resealed.bin"
"$work/seal" seal "$work/resealed.bin" >/dev/null
cmp "$work/sealed.bin" "$work/resealed.bin"

cp "$work/sealed.bin" "$work/corrupt.bin"
printf '\001' | dd of="$work/corrupt.bin" bs=1 seek=17 conv=notrunc \
  status=none
if "$work/seal" check "$work/corrupt.bin" >/dev/null 2>&1; then
  echo 'firmware sealer accepted a corrupted image' >&2
  exit 1
fi

cp "$work/sealed.bin" "$work/corrupt-build.bin"
printf '\001' | dd of="$work/corrupt-build.bin" bs=1 seek=152 conv=notrunc \
  status=none
if "$work/seal" check "$work/corrupt-build.bin" >/dev/null 2>&1; then
  echo 'firmware sealer accepted a corrupted build identity' >&2
  exit 1
fi

cp "$work/unsealed.bin" "$work/optional.bin"
printf '\000\000\000\000' | dd of="$work/optional.bin" bs=1 seek=160 \
  conv=notrunc status=none
if "$work/seal" seal "$work/optional.bin" >/dev/null 2>&1; then
  echo 'firmware sealer accepted an image without required CRC flag' >&2
  exit 1
fi

cp "$work/unsealed.bin" "$work/duplicate.bin"
dd if="$work/unsealed.bin" of="$work/duplicate.bin" bs=1 skip=128 seek=384 \
  count=40 conv=notrunc status=none
if "$work/seal" seal "$work/duplicate.bin" >/dev/null 2>&1; then
  echo 'firmware sealer accepted duplicate footers' >&2
  exit 1
fi

if "$work/seal" seal --max-size 511 "$work/unsealed.bin" \
    >/dev/null 2>&1; then
  echo 'firmware sealer ignored Flash capacity' >&2
  exit 1
fi

if command -v pwsh >/dev/null 2>&1; then
  "$work/fixture" "$work/powershell-input.bin"
  pwsh -NoLogo -NoProfile -File "$root/tools/seal-firmware.ps1" seal \
    -InputFile "$work/powershell-input.bin" \
    -OutputFile "$work/powershell-sealed.bin" -MaxSize 512 \
    > "$work/powershell-seal.log"
  pwsh -NoLogo -NoProfile -File "$root/tools/seal-firmware.ps1" check \
    -InputFile "$work/powershell-sealed.bin" -MaxSize 512 \
    > "$work/powershell-check.log"
  cmp "$work/sealed.bin" "$work/powershell-sealed.bin"
  grep -q 'size=512 footer=128' "$work/powershell-check.log"
fi

printf 'firmware_seal_tests: ok\n'

#!/usr/bin/env bash
set -euo pipefail

root="$(cd "$(dirname "$0")/.." && pwd)"
arduino_cli="${MK61_ARDUINO_CLI:-arduino-cli}"

fail() {
  printf 'F401 UC1609 compile check: %s\n' "$1" >&2
  exit 2
}

"$root/tests/run_f411_release_matrix.sh" --check-dependencies

temporary_root=0
if [[ -n "${MK61_F401_UC1609_BUILD_ROOT:-}" ]]; then
  build_root="$MK61_F401_UC1609_BUILD_ROOT"
  [[ ! -e "$build_root" ]] || fail "build root already exists: $build_root"
  mkdir -p "$build_root"
else
  build_root="$(mktemp -d "${TMPDIR:-/tmp}/mk61-f401-uc1609.XXXXXX")"
  temporary_root=1
fi

cleanup() {
  if [[ "$temporary_root" -eq 1 ]]; then
    rm -rf "$build_root"
  fi
}
trap cleanup EXIT HUP INT TERM

sketch="$build_root/mk61s-M"
compile_path="$build_root/build"
compile_log="$build_root/compile.log"
mkdir -p "$sketch" "$compile_path"
cp -R "$root/code/." "$sketch/"

fqbn='STMicroelectronics:stm32:GenF4:pnum=BLACKPILL_F401CC,upload_method=dfuMethod,xserial=generic,usb=CDCgen,opt=osstd'
strict_flags='-DMK61_BOARD_CLASSIC_V3 -Werror -Wno-error=cpp'

set +e
"$arduino_cli" compile \
  --warnings all \
  --fqbn "$fqbn" \
  --build-path "$compile_path" \
  --build-property "compiler.cpp.extra_flags=$strict_flags" \
  "$sketch" 2>&1 | tee "$compile_log"
pipeline_status=("${PIPESTATUS[@]}")
compile_status=${pipeline_status[0]}
tee_status=${pipeline_status[1]}
set -e

[[ "$compile_status" -eq 0 ]] ||
  fail "compile failed (status $compile_status)"
[[ "$tee_status" -eq 0 ]] || fail 'could not record compiler output'

unexpected_warnings="$(
  grep -F 'warning:' "$compile_log" |
    grep -Ev 'STM32RTC\.cpp:[0-9]+:[0-9]+: warning: #warning "only BCD mode is supported"|^lto-wrapper: warning: using serial compilation of [0-9]+ LTRANS jobs$' ||
    true
)"
if [[ -n "$unexpected_warnings" ]]; then
  printf 'Unexpected compiler warnings for F401 Classic V3 UC1609:\n%s\n' \
    "$unexpected_warnings" >&2
  exit 1
fi

test -s "$compile_path/mk61s-M.ino.elf" || fail 'missing ELF'
test -s "$compile_path/mk61s-M.ino.bin" || fail 'missing BIN'
"$root/tests/check_global_constructors.sh" \
  "$compile_path/mk61s-M.ino.elf"

printf '\nF401 Classic V3 UC1609 Arduino compile check: OK\n'

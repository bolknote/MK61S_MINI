#!/usr/bin/env bash
set -euo pipefail

root=$(cd "$(dirname "$0")/.." && pwd)
work=$(mktemp -d "${TMPDIR:-/tmp}/mkc-test.XXXXXX")
cleanup_test() {
  rm -rf "$work"
}
trap cleanup_test EXIT

mkdir -p "$work/local/Good" "$work/device/Programs" "$work/session"
printf '2+2\n' > "$work/local/demo.foc"
printf '001\n' > "$work/local/Good/program.m61"
printf 'raw\n' > "$work/local/blocked.bin"
printf '\000\001\177\200\377' > "$work/local/binary.wbmp"
dd if=/dev/zero of="$work/local/large.tbi" bs=1 count=1537 2>/dev/null

test "$("$root/tools/mkc.sh" --classify "$work/local/demo.foc")" = supported
test "$("$root/tools/mkc.sh" --classify "$work/local/Good")" = supported
test "$("$root/tools/mkc.sh" --classify "$work/local/blocked.bin" || true)" = \
  'unsupported: формат не поддерживается'
case "$("$root/tools/mkc.sh" --classify "$work/local/large.tbi" || true)" in
  'unsupported: слишком большой:'*) ;;
  *) echo 'mkc: oversized file was accepted' >&2; exit 1 ;;
esac

MKC_SOURCE_ONLY=1 MKC_CONFIG_FILE="$work/config" source "$root/tools/mkc.sh"
SESSION_DIR="$work/session"
MOCK_ROOT="$work/device"
shopt -s nullglob dotglob

remote_put_file "$work/local/demo.foc" /demo.foc
cmp "$work/local/demo.foc" "$work/device/demo.foc"
remote_get_file /demo.foc "$work/download.foc"
cmp "$work/local/demo.foc" "$work/download.foc"
file_to_hex "$work/local/binary.wbmp" > "$work/session/binary.hex"
hex_file_to_binary "$work/session/binary.hex" "$work/binary.roundtrip"
cmp "$work/local/binary.wbmp" "$work/binary.roundtrip"

plan_reset
if plan_local_tree "$work/local" /Imported; then
  echo 'mkc: a directory containing an unsupported file was accepted' >&2
  exit 1
fi
case "$PLAN_ERROR" in blocked.bin:*|large.tbi:*) ;;
  *) echo "mkc: unexpected preflight error: $PLAN_ERROR" >&2; exit 1 ;;
esac

plan_reset
plan_local_tree "$work/local/Good" /Good
test "${#PLAN_KINDS[@]}" -eq 2
test "$PLAN_TOTAL" -eq 4

if command -v expect >/dev/null 2>&1; then
  export MKC_TEST_LOCAL="$work/local/Good"
  export MKC_TEST_DEVICE="$work/device"
  expect -c '
    set timeout 8
    log_user 0
    spawn env TERM=xterm-256color MKC_CONFIG_FILE=/dev/null \
      "'"$root"'/tools/mkc.sh" --mock $env(MKC_TEST_DEVICE) \
      --local $env(MKC_TEST_LOCAL)
    after 400
    send "\033\[21~"
    expect eof
    catch wait result
    exit [lindex $result 3]
  '
fi

echo 'mkc_tests: ok'

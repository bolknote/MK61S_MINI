#!/usr/bin/env bash
set -euo pipefail
root="$(cd "$(dirname "$0")/.." && pwd)"
work=$(mktemp -d "${TMPDIR:-/tmp}/mkc-system-test.XXXXXX")
trap 'rm -rf "$work"' EXIT
mkdir -p "$work/source" "$work/device" "$work/session"
MKC_SOURCE_ONLY=1 source "$root/tools/.mkc/mkc.sh"
SESSION_DIR="$work/session"
LOCAL_PATH="$work/source"
MOCK_ROOT="$work/device"
shopt -s nullglob dotglob
RESIDENT_USBDISK=0
! install_system_unattended
[[ "$STATUS_TEXT" == *USBDISK.APP* ]]
test ! -e "$MOCK_ROOT/System"
RESIDENT_USBDISK=1
printf 'Справка\r\n' > "$LOCAL_PATH/HELP0.TXT"
(
  MOCK_ROOT=
  select_mk61_port() { DETECTED_PROFILE=picocalc-pico-h;return 0; }
  start_monitor() { echo 'Pico installer reached a write transport' >&2;exit 99; }
  ! install_system_unattended
  [[ "$STATUS_TEXT" == *PicoCalc*UF2* ]]
)
install_system_unattended
remote_get_file /System/HELP0.TXT "$work/help"
grep -q 'Справка' "$work/help"

# The one owned nested helper is synced; bytecode/user data is not deleted.
mkdir -p "$LOCAL_PATH/VMCache"
dd if=/dev/zero of="$LOCAL_PATH/VMCache/VMSTORE.APP" bs=64 count=1 2>/dev/null
dd if=/dev/zero of="$LOCAL_PATH/TERMINAL.APP" bs=64 count=1 2>/dev/null
dd if=/dev/zero of="$LOCAL_PATH/CLOCK.APP" bs=64 count=1 2>/dev/null
install_system_unattended
cmp "$LOCAL_PATH/TERMINAL.APP" "$MOCK_ROOT/System/TERMINAL.APP"
cmp "$LOCAL_PATH/CLOCK.APP" "$MOCK_ROOT/System/CLOCK.APP"
cmp "$LOCAL_PATH/VMCache/VMSTORE.APP" "$MOCK_ROOT/System/VMCache/VMSTORE.APP"
printf 'retained-cache' > "$MOCK_ROOT/System/VMCache/VMC-0042.APP"
rm "$LOCAL_PATH/VMCache/VMSTORE.APP" "$LOCAL_PATH/TERMINAL.APP" "$LOCAL_PATH/CLOCK.APP"
install_system_unattended
test ! -e "$MOCK_ROOT/System/VMCache/VMSTORE.APP"
test ! -e "$MOCK_ROOT/System/TERMINAL.APP"
test ! -e "$MOCK_ROOT/System/CLOCK.APP"
test "$(<"$MOCK_ROOT/System/VMCache/VMC-0042.APP")" = retained-cache

# A malformed source is rejected before old files can be removed.
printf x > "$LOCAL_PATH/BASIC.APP"
printf keep > "$MOCK_ROOT/System/FOCAL.APP"
! install_system_unattended
test -f "$MOCK_ROOT/System/FOCAL.APP"
rm "$LOCAL_PATH/BASIC.APP"

# The readback, not just the upload acknowledgement, is authoritative.
(
  remote_get_file() { printf broken > "$2"; }
  ! install_system_unattended
  [[ "$STATUS_TEXT" == *отличается* ]]
)

# Identity/profile mismatch must not start a modifying session.
(
  MOCK_ROOT=
  EXPECTED_PROFILE=classic-v3-uc1609
  select_mk61_port() { DETECTED_PROFILE=mini-v2-lcd1602-a00; return 0; }
  start_monitor() { touch "$work/unexpected-monitor"; return 0; }
  ! install_system_unattended
  [[ "$STATUS_TEXT" == *'не соответствует'* ]]
  test ! -e "$work/unexpected-monitor"
)

# Matching profile is insufficient when the resident is from another build.
(
  MOCK_ROOT=
  EXPECTED_PROFILE=mini-v2-a00
  EXPECTED_BUILD_ID=12345678
  select_mk61_port() { DETECTED_PROFILE=$EXPECTED_PROFILE; DETECTED_BUILD_ID=87654321; return 0; }
  start_monitor() { touch "$work/unexpected-monitor"; return 0; }
  ! install_system_unattended
  [[ "$STATUS_TEXT" == *'does not match bundle'* ]]
  test ! -e "$work/unexpected-monitor"
)

# A calculator may enumerate only after the DFU leave request.
(
  MOCK_ROOT=
  READY_WAIT_SECONDS=3
  EXPECTED_PROFILE=classic-v3-uc1609
  attempts=0
  select_mk61_port() {
    attempts=$((attempts + 1))
    if [ "$attempts" -lt 2 ]; then SELECT_ERROR=waiting; return 1; fi
    DETECTED_PROFILE=$EXPECTED_PROFILE
  }
  start_monitor() { MOCK_ROOT="$work/device"; return 0; }
  install_system_unattended
  test "$attempts" -eq 2
)
printf 'mkc_system_install_self_test: ok\n'

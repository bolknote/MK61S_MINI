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
install_system_unattended
remote_get_file /System/HELP0.TXT "$work/help"
grep -q 'Справка' "$work/help"

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

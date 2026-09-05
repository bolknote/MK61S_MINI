#!/usr/bin/env bash
set -euo pipefail

if [[ "$#" -ne 1 || ! -d "$1" ]]; then
  printf 'Usage: check_keyboard_handoff.sh <existing source directory>\n' >&2
  exit 2
fi

# grep is already a host-suite dependency on macOS and Linux. Do not use -q:
# an early match could hide an I/O error later in the source tree.
scan_status=0
grep -r -n -E -- \
  'exclude_before|drop_pending_key_events|drop_menu_exit_key_events|drop_key_events_until_release' \
  "$1" || scan_status=$?

case "$scan_status" in
  1) ;; # No matches: the only successful gate outcome.
  0)
    printf 'Legacy input discard path must not coexist with keyboard handoff.\n' >&2
    exit 1
    ;;
  *)
    printf 'Keyboard handoff source scan failed (grep exit %s).\n' "$scan_status" >&2
    exit "$scan_status"
    ;;
esac

#!/usr/bin/env bash
set -euo pipefail

root="$(cd "$(dirname "$0")/.." && pwd)"
out="${TMPDIR:-/tmp}/mk61_usb_screen_virtual_keys_self_test"
sanitizer_flags=()
if [[ "${MK61_TEST_SANITIZERS:-0}" == "1" ]]; then
  sanitizer_flags=(-fsanitize=address,undefined -fno-omit-frame-pointer)
fi

clang++ -std=c++17 -Wall -Wextra -Werror \
  "${sanitizer_flags[@]}" \
  -I"$root/code" \
  "$root/tests/usb_screen_virtual_keys_self_test.cpp" \
  -o "$out"

"$out"

# There must be no eager held-state update when a USB event is merely queued.
python3 - "$root/code/usb_screen.cpp" <<'PY'
import pathlib
import sys
source = pathlib.Path(sys.argv[1]).read_text()
assert source.count('kbd::set_external_key_pressed') == 1
assert 'deliverFront(kbd::push,' in source
PY

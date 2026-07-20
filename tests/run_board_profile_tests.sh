#!/usr/bin/env bash
set -euo pipefail

root="$(cd "$(dirname "$0")/.." && pwd)"
out="${TMPDIR:-/tmp}/mk61_board_profile_self_test"
sanitizer_flags=()
if [[ "${MK61_TEST_SANITIZERS:-0}" == "1" ]]; then
  sanitizer_flags=(-fsanitize=address,undefined -fno-omit-frame-pointer)
fi

common=(
  -std=c++17 -Wall -Wextra -Werror
  "${sanitizer_flags[@]}"
  -I"$root/tests/program_store_shim"
  -I"$root/code"
  "$root/tests/board_profile_self_test.cpp"
)

clang++ "${common[@]}" -o "$out-v3"
"$out-v3"

clang++ "${common[@]}" -DREVISION_V2 -DMK61_CONFIG_EXPECT_V2 -o "$out-v2"
"$out-v2"

if clang++ "${common[@]}" -DREVISION_V2 -DREVISION_V3 -o "$out-invalid" \
    >/dev/null 2>&1; then
  echo "conflicting board revisions unexpectedly compiled" >&2
  exit 1
fi

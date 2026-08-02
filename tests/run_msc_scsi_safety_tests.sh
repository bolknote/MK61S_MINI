#!/usr/bin/env bash
set -euo pipefail

root="$(cd "$(dirname "$0")/.." && pwd)"
out="${TMPDIR:-/tmp}/mk61_msc_scsi_safety_self_test"
policy_out="${TMPDIR:-/tmp}/mk61_msc_memory_policy_self_test"
sanitizer_flags=()
if [[ "${MK61_TEST_SANITIZERS:-0}" == "1" ]]; then
  sanitizer_flags=(-fsanitize=address,undefined -fno-omit-frame-pointer)
fi

clang -std=c11 -Wall -Wextra -Werror \
  "${sanitizer_flags[@]}" \
  -I"$root/code" \
  "$root/tests/msc_scsi_safety_self_test.c" \
  -o "$out"

"$out"

clang -std=c11 -Wall -Wextra -Werror \
  -DSTM32F401xC \
  -DMSC_MEDIA_PACKET=8192U \
  -DMK61_EXPECTED_MSC_PACKET_BYTES=512U \
  "$root/tests/msc_memory_policy_self_test.c" \
  -o "$policy_out-f401"
"$policy_out-f401"

clang -std=c11 -Wall -Wextra -Werror \
  -DSTM32F411xE \
  -DMSC_MEDIA_PACKET=512U \
  -DMK61_EXPECTED_MSC_PACKET_BYTES=8192U \
  "$root/tests/msc_memory_policy_self_test.c" \
  -o "$policy_out-f411"
"$policy_out-f411"

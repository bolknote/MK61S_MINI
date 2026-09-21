#!/usr/bin/env bash
set -euo pipefail

root="$(cd "$(dirname "$0")/.." && pwd)"
out="${TMPDIR:-/tmp}/mk61_terminal_self_test"
sanitizer_flags=()
if [[ "${MK61_TEST_SANITIZERS:-0}" == "1" ]]; then
  sanitizer_flags=(-fsanitize=address,undefined -fno-omit-frame-pointer)
fi

clang++ -std=c++17 -Wall -Wextra -Werror \
  "${sanitizer_flags[@]}" \
  -I"$root/code" \
  "$root/tests/terminal_self_test.cpp" \
  "$root/code/m61_ansi.cpp" \
  "$root/code/m61_print.cpp" \
  -o "$out"

"$out"

for screen in 0 1; do
  clang++ -std=c++17 -Wall -Wextra -Werror \
    "${sanitizer_flags[@]}" -DMK61_ENABLE_USB_SCREEN="$screen" \
    -I"$root/tests/mk_math_shim" -I"$root/code" \
    "$root/tests/terminal_catalog_self_test.cpp" \
    "$root/code/terminal_catalog.cpp" -o "${out}_catalog"
  "${out}_catalog"
done

# F411 with USB Screen enables the largest help catalog. Keep its two-page
# budget covered by fast host tests, before the full release matrix runs.
clang++ -std=c++17 -Wall -Wextra -Werror \
  "${sanitizer_flags[@]}" \
  -DSTM32F411xE -DMK61_ENABLE_USB_SCREEN=1 \
  -I"$root/tests/mk_math_shim" -I"$root/code" \
  "$root/tests/terminal_catalog_self_test.cpp" \
  "$root/code/terminal_catalog.cpp" -o "${out}_catalog_f411_usb_screen"
"${out}_catalog_f411_usb_screen"

# Product F401 omits service-only diagnostic commands. Characterize that exact
# conditional catalog as well.
clang++ -std=c++17 -Wall -Wextra -Werror \
  "${sanitizer_flags[@]}" \
  -DARDUINO_BLACKPILL_F401CC -DMK61_DISPLAY_UC1609 \
  -DMK61_F401_PRODUCT_BUILD=1 \
  -I"$root/tests/mk_math_shim" -I"$root/code" \
  "$root/tests/terminal_catalog_self_test.cpp" \
  "$root/code/terminal_catalog.cpp" -o "${out}_catalog_f401"
"${out}_catalog_f401"

#!/usr/bin/env bash
set -euo pipefail

root="$(cd "$(dirname "$0")/.." && pwd)"
font_test_dir="$(mktemp -d "${TMPDIR:-/tmp}/mk61-ui-font.XXXXXX")"
trap 'rm -f "$font_test_dir/ui-font-test" "$font_test_dir/lcd.o" "$font_test_dir/ws0010.o" "$font_test_dir/f401-uc1609.o" "$font_test_dir/f401-calculator-face.o"; rmdir "$font_test_dir"' EXIT
sanitizer_flags=()
if [[ "${MK61_TEST_SANITIZERS:-0}" == "1" ]]; then
  sanitizer_flags=(-fsanitize=address,undefined -fno-omit-frame-pointer)
fi

python3 "$root/tools/generate_ui_fonts.py" --check
clang++ -std=c++17 -Wall -Wextra -Werror -pedantic \
  "${sanitizer_flags[@]}" -DARDUINO=100 -DMK61_DISPLAY_UC1609 \
  -DMK61_PROPORTIONAL_UI_FONTS=1 \
  -I"$root/code" -I"$root/tests/mk_math_shim" \
  "$root/tests/ui_font_self_test.cpp" "$root/code/ui_font.cpp" \
  -o "$font_test_dir/ui-font-test"
"$font_test_dir/ui-font-test"
python3 "$root/tests/ui_font_source_self_test.py" "$font_test_dir/ui-font-test"

for variant in lcd ws0010 f401-uc1609; do
  variant_flags=()
  if [[ "$variant" == ws0010 ]]; then
    variant_flags=(-DMK61_OLED1602_WS0010)
  elif [[ "$variant" == f401-uc1609 ]]; then
    variant_flags=(-DMK61_DISPLAY_UC1609 -DARDUINO_BLACKPILL_F401CC)
  fi
  clang++ -std=c++17 -Wall -Wextra -Werror -pedantic \
    -DARDUINO=100 "${variant_flags[@]}" \
    -I"$root/code" -I"$root/tests/mk_math_shim" \
    -c "$root/code/ui_font.cpp" -o "$font_test_dir/$variant.o"
  if nm "$font_test_dir/$variant.o" | grep -q 'ui_font'; then
    echo "Unexpected UI font symbols in $variant build" >&2
    exit 1
  fi
done
clang++ -std=c++17 -Wall -Wextra -Werror -pedantic \
  -DARDUINO=100 -DMK61_DISPLAY_UC1609 -DARDUINO_BLACKPILL_F401CC \
  -I"$root/code" -I"$root/tests/mk_math_shim" \
  -c "$root/code/calculator_face.cpp" \
  -o "$font_test_dir/f401-calculator-face.o"
if nm "$font_test_dir/f401-calculator-face.o" | grep -q 'calculator_face'; then
  echo "Unexpected calculator-face symbols in F401/UC1609 build" >&2
  exit 1
fi
echo "A00/A02, WS0010 and F401/UC1609 exclusions passed"

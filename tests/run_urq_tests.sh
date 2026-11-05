#!/usr/bin/env bash
set -euo pipefail
root="$(cd "$(dirname "$0")/.." && pwd)"
work="$root/.build/urq-tests"
mkdir -p "$work"
clang++ -std=c++17 -O2 -Wall -Wextra -Werror -Wno-missing-field-initializers \
  -fsanitize=address,undefined -fno-omit-frame-pointer \
  "$root/tests/urq_host.cpp" "$root/code/urq/engine.cpp" \
  "$root/code/urq/pack.cpp" "$root/code/zx0.cpp" "$root/code/ecma_number.cpp" -o "$work/urq-host"
python3 "$root/tests/urq_self_test.py" "$work/urq-host"
python3 "$root/tests/urq_library_self_test.py" "$work/urq-host"
python3 - "$work/ui.qst" <<'PY'
import sys
from pathlib import Path
Path(sys.argv[1]).write_text(':start\npln X\nproc outer\nanykey code\nbtn done, ' +
    'Длинное действие, которое надо прочитать целиком, прежде чем выбрать. ' * 5 +
    '\nbtn done, Второе действие\nend\n:outer\nproc inner\nend\n:inner\ninput answer\nend\n:done\nquit\n')
PY
python3 "$root/tools/apps/urq/qst2urq.py" "$work/ui.qst" --mode urqw --encoding UTF-8 --output "$work/ui" >/dev/null
for profile in stm32 picocalc; do
  extra=()
  if [ "$profile" = picocalc ]; then extra+=(-DMK61_TARGET_PICOCALC=1); fi
  clang++ -std=c++17 -O1 -Wall -Wextra -Werror -Wno-missing-field-initializers \
    -fsanitize=address,undefined -fno-omit-frame-pointer "${extra[@]}" \
    -DARDUINO=100 -DMK61_DISPLAY_UC1609 -DMK61_PROPORTIONAL_UI_FONTS=1 \
    -I"$root/sdk/portable/include" -I"$root/code" -I"$root/tests/mk_math_shim" \
    "$root/tests/urq_ui_self_test.cpp" "$root/code/urq/engine.cpp" \
    "$root/code/urq/pack.cpp" "$root/code/zx0.cpp" "$root/code/ecma_number.cpp" \
    "$root/code/ui_font.cpp" "$root/code/builtin_font.cpp" "$root/code/ERM19264_graphics_font.cpp" -o "$work/urq-ui-$profile"
done
"$work/urq-ui-stm32" "$work/ui" "$work/m4.urs"
URQ_TEST_CLASSIC=1 "$work/urq-ui-stm32" "$work/ui" "$work/classic.urs"
"$work/urq-ui-picocalc" "$work/ui" "$work/m0.urs" "$work/m4.urs"
URQ_TEST_PSRAM=fail "$work/urq-ui-picocalc" "$work/ui" "$work/psram-failure.urs" "$work/m4.urs"
"$work/urq-ui-stm32" "$work/ui" "$work/roundtrip.urs" "$work/m0.urs"

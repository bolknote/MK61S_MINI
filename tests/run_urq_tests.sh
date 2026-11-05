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
printf ':start\npln X\nproc outer\nanykey code\nend\n:outer\nproc inner\nend\n:inner\ninput answer\nend\n' > "$work/ui.qst"
python3 "$root/tools/qst2urq.py" "$work/ui.qst" --mode urqw --encoding UTF-8 --output "$work/ui" >/dev/null
for profile in stm32 picocalc; do
  extra=()
  if [ "$profile" = picocalc ]; then extra+=(-DMK61_TARGET_PICOCALC=1); fi
  clang++ -std=c++17 -O1 -Wall -Wextra -Werror -Wno-missing-field-initializers \
    -fsanitize=address,undefined -fno-omit-frame-pointer "${extra[@]}" \
    -I"$root/sdk/portable/include" -I"$root/code" \
    "$root/tests/urq_ui_self_test.cpp" "$root/code/urq/engine.cpp" \
    "$root/code/urq/pack.cpp" "$root/code/zx0.cpp" "$root/code/ecma_number.cpp" -o "$work/urq-ui-$profile"
done
"$work/urq-ui-stm32" "$work/ui" "$work/m4.urs"
"$work/urq-ui-picocalc" "$work/ui" "$work/m0.urs" "$work/m4.urs"
URQ_TEST_PSRAM=fail "$work/urq-ui-picocalc" "$work/ui" "$work/psram-failure.urs" "$work/m4.urs"
"$work/urq-ui-stm32" "$work/ui" "$work/roundtrip.urs" "$work/m0.urs"

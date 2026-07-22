#!/usr/bin/env bash
set -euo pipefail

root="$(cd "$(dirname "$0")/.." && pwd)"
out="${TMPDIR:-/tmp}/mk61_mk_math_self_test"
sanitizer_flags=()
if [[ "${MK61_TEST_SANITIZERS:-0}" == "1" ]]; then
  sanitizer_flags=(-fsanitize=address,undefined -fno-omit-frame-pointer)
fi

# Собираем подсистему CORE вместе с настоящим ядром МК-61 на хосте.
# Заголовки-заглушки (Arduino.h/debug.h) идут первыми в пути включения, чтобы
# зависимости только для прошивки разрешались в хостовые заглушки.
clang++ -std=c++17 -Wall -Wextra -Wno-unused -Wno-unused-parameter \
  -Wno-cpp \
  "${sanitizer_flags[@]}" \
  -DMK61_MATH_BACKEND=1 \
  -include "$root/tests/mk_math_shim/debug.h" \
  -I"$root/tests/mk_math_shim" \
  -I"$root/code" \
  "$root/tests/mk_math_self_test.cpp" \
  "$root/code/mk_math_core.cpp" \
  "$root/code/mk61emu_core.cpp" \
  -o "$out"

"$out"

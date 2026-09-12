#!/usr/bin/env bash
set -euo pipefail

root="$(cd "$(dirname "$0")/.." && pwd)"
out="${TMPDIR:-/tmp}/mk61_startup_splash_self_test"
sanitizer_flags=()
if [[ "${MK61_TEST_SANITIZERS:-0}" == "1" ]]; then
  sanitizer_flags=(-fsanitize=address,undefined -fno-omit-frame-pointer)
fi

clang++ -std=c++17 -Wall -Wextra -Werror \
  "${sanitizer_flags[@]}" \
  -I"$root/code" \
  "$root/tests/startup_splash_self_test.cpp" \
  -o "$out"

"$out" "$@"

# The splash must hand the display directly to the calculator before setup()
# returns. Otherwise UC1609 flushes the restored angle label through the
# ordinary text renderer and leaves a small zero until the first core event.
python3 - "$root/code/mk61s-M.ino" <<'PY'
from pathlib import Path
import sys

source = Path(sys.argv[1]).read_text(encoding="utf-8")
begin = source.index("void setup() {")
end = source.index("\n//===================================================================", begin)
setup = source[begin:end]

angle = setup.index("(void) load_grade_switch();")
core = setup.index("core_61::enable();", angle)
redraw = setup.index("lcd_std_display_redraw();", core)
if not angle < core < redraw:
    raise SystemExit("startup calculator display order is not deterministic")
if "GRDLabel.print(load_grade_switch())" in setup:
    raise SystemExit("startup emits an intermediate text-mode angle frame")
print("startup calculator display handoff: ok")
PY

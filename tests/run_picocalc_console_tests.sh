#!/usr/bin/env bash
set -euo pipefail
root="$(cd "$(dirname "$0")/.." && pwd)"
build="$(mktemp -d "${TMPDIR:-/tmp}/mk61-pico-console.XXXXXX")"
trap 'rm -rf "$build"' EXIT
flags=()
if [[ "${MK61_TEST_SANITIZERS:-0}" == 1 ]]; then flags=(-fsanitize=address,undefined -fno-omit-frame-pointer); fi
cat > "$build/io-main.cpp" <<'CPP'
void picocalc_io_test();
int main() { picocalc_io_test(); }
CPP
clang++ -std=c++17 -O2 -Wall -Wextra -Werror "${flags[@]}" -pthread \
    -DMK61_CORE_STANDALONE=1 -I"$root/ports/picocalc" -I"$root/code" \
    "$root/tests/picocalc_io_self_test.cpp" "$build/io-main.cpp" -o "$build/io"
"$build/io"
# Compile the actual production main-loop input path in the existing host
# console harness. Keep one source of truth; hardware endpoints are fixtures.
python3 - "$root/ports/picocalc/main.cpp" "$build/picocalc_main_input_loop.inc" <<'PYINPUT'
from pathlib import Path
import sys
source=Path(sys.argv[1]).read_text()
first='        const unsigned input_budget=terminal.raw()?8U:terminal_core::INPUT_CAPACITY;\n'
last='        terminal.tick();\n'
assert source.count(first)==1 and source.count(last)==1
begin=source.index(first);end=source.index(last,begin)
Path(sys.argv[2]).write_text(source[begin:end])
PYINPUT
clang++ -std=c++17 -O2 -Wall -Wextra -Werror "${flags[@]}" \
    -DMK61_CORE_STANDALONE=1 -I"$build" -I"$root/ports/picocalc" -I"$root/code" \
    "$root/tests/picocalc_console_fairness_self_test.cpp" "$root/ports/picocalc/usb_screen.cpp" \
    "$root/code/usb_screen_protocol.cpp" -o "$build/fairness"
"$build/fairness"

#!/usr/bin/env bash
set -euo pipefail
root="$(cd "$(dirname "$0")/.." && pwd)"
python3 "$root/tests/app_relocations_self_test.py"
work="$(mktemp -d "${TMPDIR:-/tmp}/mk61-portable-tests.XXXXXX")"
trap 'rm -rf "$work"' EXIT
flags=(-std=c++17 -O1 -Wall -Wextra -Werror -I"$root/code")
if [[ "${MK61_TEST_SANITIZERS:-0}" == 1 ]]; then
  flags+=(-fsanitize=address,undefined -fno-omit-frame-pointer)
fi
clang++ "${flags[@]}" -DMK61_ENABLE_PORTABLE_APPS=1 \
  "$root/tests/portable_app_format_self_test.cpp" \
  "$root/code/loadable_module_format.cpp" "$root/code/zx0.cpp" \
  -o "$work/format"
"$work/format"
clang++ "${flags[@]}" \
  "$root/tests/portable_app_format_self_test.cpp" \
  "$root/code/loadable_module_format.cpp" "$root/code/zx0.cpp" \
  -o "$work/legacy-format"
MK61_MODULE_PACK_BIN="$work/packer" bash "$root/tools/build_mk61_module_pack.sh" \
  --help >/dev/null
python3 "$root/tests/portable_app_package_self_test.py" \
  "$work/packer" "$work/format" "$work/legacy-format"
clang++ "${flags[@]}" -I"$root/sdk/portable/include" \
  "$root/tests/portable_wbmp_self_test.cpp" \
  "$root/examples/portable-apps/WBMP/viewer.cpp" "$root/code/wbmp.cpp" \
  -o "$work/wbmp"
"$work/wbmp"
clang --target=arm-none-eabi -mcpu=cortex-m4 -mthumb \
  -std=c11 -Wall -Wextra -Werror -ffreestanding -I"$root/code" \
  -c "$root/tests/portable_system_abi_self_test.c" -o "$work/system-api.o"
# Verify that the public SDK really is C, independently of C++ compilation.
clang --target=arm-none-eabi -mcpu=cortex-m4 -mthumb \
  -std=c11 -Wall -Wextra -Werror -ffreestanding -fno-builtin \
  -I"$root/code" -I"$root/sdk/portable/include" \
  -c "$root/sdk/portable/start.c" -o "$work/start.o"
clang --target=arm-none-eabi -mcpu=cortex-m4 -mthumb \
  -std=c11 -Wall -Wextra -Werror -ffreestanding -fno-builtin \
  -I"$root/code" -I"$root/sdk/portable/include" \
  -c "$root/examples/portable-apps/HELLO/main.c" -o "$work/hello.o"

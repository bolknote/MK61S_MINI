#!/usr/bin/env bash
set -euo pipefail
root="$(cd "$(dirname "$0")/.." && pwd)"
build_dir="$(mktemp -d "${TMPDIR:-/tmp}/mk61-picocalc.XXXXXX")"
trap 'rm -rf "$build_dir"' EXIT
flags=()
if [[ "${MK61_TEST_SANITIZERS:-0}" == 1 ]]; then
    flags=(-fsanitize=address,undefined -fno-omit-frame-pointer)
fi
for unit in ff ffunicode; do
    clang -std=c11 -O2 "${flags[@]}" -I"$root/ports/picocalc" -I"$root/third_party/fatfs" \
        -c "$root/third_party/fatfs/$unit.c" -o "$build_dir/$unit.o"
done
clang++ -std=c++17 -O2 -Wall -Wextra -Werror -Wno-unused-variable -Wno-unused-parameter -Wno-unused-function -fconstexpr-steps=10000000 \
    -ffp-contract=off "${flags[@]}" -DMK61_CORE_STANDALONE=1 -DMK61_M61_READ_CACHE_BYTES=2048 -DMK61_ENABLE_RTC_ALARM_TERMINAL=1 -DMK61_ENABLE_USB_SCREEN=1 \
    -DMK61_USE_COMPACT_LIBM=1 -DMK61_MATH_BACKEND=0 \
    -I"$root/code" -I"$root/ports/picocalc" -I"$root/third_party/fatfs" \
    "$root/tests/picocalc_self_test.cpp" "$root/ports/picocalc/calculator.cpp" \
    "$root/ports/picocalc/screen.cpp" "$root/ports/picocalc/math_probe.cpp" "$root/ports/picocalc/markdown.cpp" "$root/ports/picocalc/terminal.cpp" "$root/ports/picocalc/fonts.cpp" "$root/ports/picocalc/native_display.cpp" "$root/ports/picocalc/canvas.cpp" \
    "$root/ports/picocalc/input.cpp" "$root/ports/picocalc/clock.cpp" "$root/ports/picocalc/diagnostics.cpp" "$root/ports/picocalc/firmware.cpp" "$root/code/crash_dump_format.cpp" \
    "$root/ports/picocalc/chip8_runtime.cpp" "$root/ports/picocalc/native_app.cpp" \
    "$root/ports/picocalc/usb_screen.cpp" "$root/code/chip8.cpp" \
    "$root/code/usb_screen_protocol.cpp" "$root/code/usb_screen_surface.cpp" "$root/code/ui_text_renderer.cpp" "$root/code/loadable_module_format.cpp" \
    "$root/ports/picocalc/ui.cpp" "$root/ports/picocalc/settings.cpp" \
    "$root/ports/picocalc/storage.cpp" "$root/ports/picocalc/block_transfer.cpp" "$root/ports/picocalc/services.cpp" "$root/ports/picocalc/service_runtime.cpp" \
    "$root/tests/picocalc_host_disk.cpp" "$root/tests/picocalc_services_self_test.cpp" "$root/tests/picocalc_io_self_test.cpp" \
    "$root/ports/picocalc/script_files.cpp" "$root/ports/picocalc/script_runtime.cpp" "$root/ports/picocalc/language_cache.cpp" \
    "$root/code/m61_text.cpp" "$root/code/m61_ansi.cpp" "$root/code/m61_print.cpp" \
    "$root/code/terminal_script_runtime.cpp" "$root/code/terminal_catalog.cpp" \
    "$root/code/terminal_key_sequence.cpp" "$root/code/calculator_control.cpp" \
    "$root/code/program_load.cpp" "$root/code/zx0_stream.cpp" \
    "$root/code/markdown_document.cpp" "$root/code/wbmp.cpp" "$root/code/explorer_autoexec.cpp" \
    "$root/tests/picocalc_m61_self_test.cpp" "$root/tests/picocalc_language_cache_self_test.cpp" "$root/tests/picocalc_runtime_self_test.cpp" "$root/tests/picocalc_parity_self_test.cpp" "$root/tests/picocalc_software_self_test.cpp" "$root/tests/picocalc_contract_self_test.cpp" "$root/tests/picocalc_firmware_self_test.cpp" "$root/code/zx0.cpp" "$root/code/zx0_encode.cpp" \
    "$root/code/language_bytecode.cpp" "$root/code/language_vm.cpp" "$root/code/language_vm_file_cache.cpp" "$root/code/basic_graphics.cpp" "$root/code/basic_native_io.cpp" "$root/code/app_flow.cpp" \
    "$root/code/calculator_face.cpp" "$root/code/text_screen.cpp" \
    "$root/code/builtin_font.cpp" "$root/code/ui_font.cpp" "$root/code/fmk_font.cpp" "$root/code/prepared_font.cpp" "$root/code/fmk_prepare.cpp" \
    "$root/code/mk61emu_core.cpp" "$root/code/ERM19264_graphics_font.cpp" \
    "$root/code/compact_math.cpp" "$build_dir/ff.o" "$build_dir/ffunicode.o" -o "$build_dir/self-test"
cd "$root"
if [[ -n "${MK61_TEST_BINARY:-}" ]]; then cp "$build_dir/self-test" "$MK61_TEST_BINARY"; fi
"$build_dir/self-test" "$@"
python3 "$root/tests/picocalc_uf2_self_test.py"
python3 "$root/tests/picocalc_seal_self_test.py"

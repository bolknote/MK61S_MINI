#!/usr/bin/env bash
set -euo pipefail
python3 "$(dirname "$0")/picocalc_status_fields_self_test.py"
python3 "$(dirname "$0")/picocalc_bios_power_self_test.py"
python3 "$(dirname "$0")/picocalc_pmu_async_self_test.py"
python3 "$(dirname "$0")/picocalc_stm3_reply_self_test.py"
python3 "$(dirname "$0")/picocalc_stm3_crc_self_test.py"
python3 "$(dirname "$0")/picocalc_m3_boot_self_test.py"
python3 "$(dirname "$0")/picocalc_keyboard_index_self_test.py"
python3 "$(dirname "$0")/picocalc_utility_scene_self_test.py"
python3 "$(dirname "$0")/picocalc_frame_schedule_self_test.py"
python3 "$(dirname "$0")/picocalc_battery_poll_self_test.py"
python3 "$(dirname "$0")/picocalc_stm32_sources_self_test.py"
python3 "$(dirname "$0")/picocalc_audio_dma_self_test.py"
bash "$(dirname "$0")/run_picocalc_read_cursor_tests.sh"
python3 "$(dirname "$0")/picocalc_psram_pio_self_test.py"
python3 "$(dirname "$0")/picocalc_psram_qpi_self_test.py"
python3 "$(dirname "$0")/picocalc_psram_probe_self_test.py"
python3 "$(dirname "$0")/picocalc_power_self_test.py"
python3 "$(dirname "$0")/picocalc_panel_recovery_self_test.py"
python3 "$(dirname "$0")/picocalc_lcd_dma_self_test.py"
python3 "$(dirname "$0")/picocalc_dma_support_self_test.py"
python3 "$(dirname "$0")/picocalc_worker_wait_self_test.py"
python3 "$(dirname "$0")/picocalc_i2c_audio_deadline_self_test.py"
python3 "$(dirname "$0")/picocalc_file_handler_self_test.py"
python3 "$(dirname "$0")/picocalc_audio_self_test.py"
python3 "$(dirname "$0")/cosmic_clock_self_test.py"
python3 "$(dirname "$0")/picocalc_audio_budget_self_test.py"
MK61_TEST_CLOCK_MODES=1 python3 "$(dirname "$0")/picocalc_audio_self_test.py"
python3 "$(dirname "$0")/picocalc_render_hil_self_test.py"
bash "$(dirname "$0")/run_shared_memory_buffer_tests.sh"
root="$(cd "$(dirname "$0")/.." && pwd)"
build="$(mktemp -d "${TMPDIR:-/tmp}/mk61-pico-hardware.XXXXXX")"
trap 'rm -rf "$build"' EXIT
flags=()
if [[ "${MK61_TEST_SANITIZERS:-0}" == 1 ]]; then flags=(-fsanitize=address,undefined -fno-omit-frame-pointer); fi
clang++ -std=c++17 -O2 -Wall -Wextra -Werror -DMK61_CORE_STANDALONE=1 "${flags[@]}" \
    -I"$root/ports/picocalc" -I"$root/code" \
    "$root/tests/picocalc_hardware_self_test.cpp" "$root/ports/picocalc/psram.cpp" \
    "$root/ports/picocalc/external_cache.cpp" "$root/ports/picocalc/dma_support.cpp" \
    "$root/ports/picocalc/buffers.cpp" "$root/code/shared_memory_buffer.cpp" -o "$build/test"
"$build/test"
clang++ -std=c++17 -O2 -Wall -Wextra -Werror "${flags[@]}" \
    -I"$root/ports/picocalc" -I"$root/code" \
    "$root/tests/picocalc_transfer_self_test.cpp" -o "$build/transfers"
"$build/transfers"
clang++ -std=c++17 -O2 -Wall -Wextra -Werror "${flags[@]}" \
    -I"$root/ports/picocalc" "$root/tests/picocalc_i2c_sd_self_test.cpp" -o "$build/i2c-sd"
"$build/i2c-sd"

clang++ -std=c++17 -O2 -Wall -Wextra -Werror "${flags[@]}" \
    -I"$root/ports/picocalc" "$root/tests/picocalc_m3_uart_self_test.cpp" -o "$build/m3-uart"
"$build/m3-uart"

clang++ -std=c++17 -O2 -Wall -Wextra -Werror "${flags[@]}" \
    -I"$root/ports/picocalc" -I"$root/code" -I"$root/sdk/coproc" \
    "$root/tests/picocalc_m3_fill_self_test.cpp" -o "$build/m3-fill"
"$build/m3-fill"

clang++ -std=c++17 -O2 -Wall -Wextra -Werror "${flags[@]}" \
    -I"$root/ports/picocalc" "$root/tests/picocalc_audio_irq_entry_self_test.cpp" -o "$build/irq-entry"
"$build/irq-entry"

clang++ -std=c++17 -O2 -Wall -Wextra -Werror "${flags[@]}" \
    -I"$root/ports/picocalc" "$root/tests/picocalc_audio_diagnostic_storage_self_test.cpp" -o "$build/audio-diagnostics"
"$build/audio-diagnostics"

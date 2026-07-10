#!/usr/bin/env bash
set -euo pipefail

root="$(cd "$(dirname "$0")/.." && pwd)"

"$root/tests/run_debug_tests.sh"
"$root/tests/run_display_font_tests.sh"
"$root/tests/run_fmk_converter_tests.sh"
"$root/tests/run_focal_tests.sh"
"$root/tests/run_keyboard_tests.sh"
"$root/tests/run_m61_text_tests.sh"
"$root/tests/run_mk_math_tests.sh"
"$root/tests/run_memory_buffer_tests.sh"
"$root/tests/run_msc_scsi_safety_tests.sh"
"$root/tests/run_program_store_tests.sh"
"$root/tests/run_runtime_peripherals_tests.sh"
"$root/tests/run_settings_journal_tests.sh"
"$root/tests/run_startup_splash_tests.sh"
"$root/tests/run_terminal_tests.sh"
"$root/tests/run_text_editor_tests.sh"
"$root/tests/run_tinybasic_tests.sh"
"$root/tests/run_virtual_fat_tests.sh"

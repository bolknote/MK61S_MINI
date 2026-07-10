#!/usr/bin/env bash
set -euo pipefail

root="$(cd "$(dirname "$0")/.." && pwd)"

"$root/tests/run_basic_tests.sh"
"$root/tests/run_focal_tests.sh"
"$root/tests/run_mk_math_tests.sh"
"$root/tests/run_memory_buffer_tests.sh"
"$root/tests/run_msc_scsi_safety_tests.sh"
"$root/tests/run_program_store_tests.sh"
"$root/tests/run_tinybasic_tests.sh"
"$root/tests/run_virtual_fat_tests.sh"

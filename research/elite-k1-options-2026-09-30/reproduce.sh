#!/usr/bin/env bash
set -euo pipefail
elite_trial_dir="$(cd "$(dirname "$0")" && pwd)"
elite_project_dir=/Users/bolk/Projects/MK61S_MINI
cd "$elite_project_dir"
clang++ -std=c++17 -O2 -Wall -Wextra -Wno-unused -Wno-unused-parameter -Wno-cpp \
  -DMK61_MATH_BACKEND=1 -DMK61_CORE_HOT_TABLES_IN_SRAM=0 \
  -DMK61_CORE_NATIVE_HOT_PATHS=1 -DMK61_CORE_PACKED_AMK=1 -DMK61_DISPLAY_UC1609 -DM61_TEXT_HOST_TEST \
  -include tests/mk_math_shim/debug.h -Itests/mk_math_shim -Icode \
  "$elite_trial_dir/core_runner.cpp" tests/elite_loader_host.cpp \
  code/m61_text.cpp code/mk_math_core.cpp code/mk61emu_core.cpp \
  code/language_workspace.cpp code/shared_memory.cpp code/workspace_swap.cpp \
  code/zx0.cpp code/zx0_encode.cpp code/zx0_stream.cpp code/program_load.cpp \
  -o "$elite_trial_dir/runner"
for elite_trial_variant in base specialized gates packed-drones overlay rle; do
  python3 "$elite_trial_dir/build_variants.py" "$elite_trial_variant"
done
python3 "$elite_trial_dir/capture.py"
for elite_trial_variant in specialized gates packed-drones overlay rle; do
  python3 "$elite_trial_dir/compare.py" "$elite_trial_variant"
done
python3 "$elite_trial_dir/packed_domain.py"
python3 "$elite_trial_dir/code_rle_audit.py"

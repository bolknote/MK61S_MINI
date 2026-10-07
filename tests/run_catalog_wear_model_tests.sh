#!/usr/bin/env bash
set -euo pipefail
root="$(cd "$(dirname "$0")/.." && pwd)"
build_dir="$(mktemp -d "${TMPDIR:-/tmp}/mk61-catalog-model.XXXXXX")"
# Deliberately host-only. The model contains no serial/USB or disk-image I/O.
sanitizers=()
if [[ "${MK61_TEST_SANITIZERS:-0}" == "1" ]]; then
  sanitizers=(-fsanitize=address,undefined -fno-sanitize-recover=all -fno-omit-frame-pointer)
fi
"${CXX:-clang++}" -std=c++17 -O2 -Wall -Wextra -Werror \
  "${sanitizers[@]}" -DPROGRAM_STORE_HOST_TEST \
  "$root/tests/catalog_wear_model_self_test.cpp" \
  "$root/code/storage_geometry.cpp" \
  -o "$build_dir/catalog-wear-model"
"$build_dir/catalog-wear-model"

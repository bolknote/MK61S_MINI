#!/usr/bin/env bash
set -euo pipefail

root="$(cd "$(dirname "$0")/.." && pwd)"
source="$root/tools/fmk_font.cpp"
output="$root/tools/fmk_font"

if [[ ! -x "$output" || "$source" -nt "$output" ]]; then
  if ! pkg-config --exists freetype2; then
    echo "FreeType development files are required (pkg-config freetype2)." >&2
    exit 1
  fi

  read -r -a freetype_flags <<<"$(pkg-config --cflags --libs freetype2)"
  c++ -std=c++17 -O2 -Wall -Wextra -Werror \
    "$source" \
    "${freetype_flags[@]}" \
    -o "$output"
fi

exec "$output" "$@"

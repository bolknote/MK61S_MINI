#!/bin/sh
# Compare with the pinned, separately downloaded GPL Raw source and the
# user's DOS data. No game data or external source is copied into Git.
set -eu
if [ "$#" -ne 2 ]; then
  printf '%s\n' 'Usage: sh tests/run_another_world_reference_tests.sh RAW_SOURCE DOS_DATA_DIR' >&2
  exit 2
fi
root=$(CDPATH= cd -- "$(dirname -- "$0")/.." && pwd)
reference=$(CDPATH= cd -- "$1" && pwd)
data=$(CDPATH= cd -- "$2" && pwd)
revision=$(git -C "$reference" rev-parse HEAD)
[ "$revision" = 170b7d466a6ea6cc36a9e53506d5b858ed503a84 ] || {
  printf '%s\n' 'Unexpected Raw revision' >&2; exit 1;
}
git -C "$reference" diff --quiet HEAD -- src
build_dir=$(mktemp -d "${TMPDIR:-/tmp}/mk61-another-reference.XXXXXXXX")
trap 'rm -r "$build_dir"' EXIT HUP INT TERM
app="$root/examples/portable-apps/ANOTHER"
raw="$reference/src"
for name in assets prepared video vm text; do
  ${CC:-cc} -std=c11 -O2 -c "$app/$name.c" -o "$build_dir/$name.o"
done
common="-std=c++17 -O2 -DAUTO_DETECT_PLATFORM -Wno-deprecated-declarations"
# shellcheck disable=SC2086
${CXX:-c++} $common -I"$raw" "$root/tests/another_world_assets_reference_test.cpp" \
  "$build_dir/assets.o" "$build_dir/prepared.o" "$raw/bank.cpp" "$raw/file.cpp" "$raw/util.cpp" -lz -o "$build_dir/assets"
"$build_dir/assets" "$data"
case $(uname -s) in Darwin) strip=-Wl,-dead_strip ;; *) strip=-Wl,--gc-sections ;; esac
# shellcheck disable=SC2086
${CXX:-c++} $common -ffunction-sections -fdata-sections -I"$raw" \
  "$root/tests/another_world_video_reference_test.cpp" "$build_dir/assets.o" "$build_dir/video.o" \
  "$raw/video.cpp" "$raw/util.cpp" "$strip" -o "$build_dir/video"
"$build_dir/video"
# shellcheck disable=SC2086
${CXX:-c++} $common -Wno-multichar -I"$raw" "$root/tests/another_world_vm_reference_test.cpp" \
  "$build_dir/assets.o" "$build_dir/video.o" "$build_dir/vm.o" "$build_dir/text.o" \
  "$raw/bank.cpp" "$raw/file.cpp" "$raw/util.cpp" "$raw/resource.cpp" "$raw/video.cpp" \
  "$raw/parts.cpp" "$raw/vm.cpp" "$raw/staticres.cpp" "$raw/sfxplayer.cpp" "$raw/mixer.cpp" \
  "$raw/serializer.cpp" -lz -o "$build_dir/vm"
"$build_dir/vm" "$data"
# Exercise the same oracle with the second SRAM video page active.
# shellcheck disable=SC2086
${CXX:-c++} $common -Wno-multichar -DAW_VIDEO_TWO_PAGES -DAW_VIDEO_BACKGROUND -DAW_VIDEO_PACKED3 -I"$raw" "$root/tests/another_world_vm_reference_test.cpp" \
  "$build_dir/assets.o" "$build_dir/video.o" "$build_dir/vm.o" "$build_dir/text.o" \
  "$raw/bank.cpp" "$raw/file.cpp" "$raw/util.cpp" "$raw/resource.cpp" "$raw/video.cpp" \
  "$raw/parts.cpp" "$raw/vm.cpp" "$raw/staticres.cpp" "$raw/sfxplayer.cpp" "$raw/mixer.cpp" \
  "$raw/serializer.cpp" -lz -o "$build_dir/vm-two-pages"
"$build_dir/vm-two-pages" "$data"
# Compare a deterministic moving level byte-for-byte, including the palette.
# shellcheck disable=SC2086
${CXX:-c++} $common -Wno-multichar -DAW_VIDEO_TWO_PAGES -DAW_VIDEO_BACKGROUND -DAW_VIDEO_BACKGROUND_SPLIT -DAW_VIDEO_PACKED3 -DAW_REFERENCE_DIRECT_LEVEL -I"$raw" \
  "$root/tests/another_world_vm_reference_test.cpp" \
  "$build_dir/assets.o" "$build_dir/video.o" "$build_dir/vm.o" "$build_dir/text.o" \
  "$raw/bank.cpp" "$raw/file.cpp" "$raw/util.cpp" "$raw/resource.cpp" "$raw/video.cpp" \
  "$raw/parts.cpp" "$raw/vm.cpp" "$raw/staticres.cpp" "$raw/sfxplayer.cpp" "$raw/mixer.cpp" \
  "$raw/serializer.cpp" -lz -o "$build_dir/vm-moving"
"$build_dir/vm-moving" "$data"

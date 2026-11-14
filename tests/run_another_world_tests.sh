#!/bin/sh
set -eu
root=$(CDPATH= cd -- "$(dirname -- "$0")/.." && pwd)
build_dir=$(mktemp -d "${TMPDIR:-/tmp}/mk61-another-world-tests.XXXXXXXX")
trap 'rm -r "$build_dir"' EXIT HUP INT TERM
${CC:-cc} -std=c11 -O2 -Wall -Wextra -Werror \
  "$root/examples/portable-apps/ANOTHER/assets.c" \
  "$root/tests/another_world_assets_self_test.c" -o "$build_dir/assets"
"$build_dir/assets"
${CC:-cc} -std=c11 -O2 -Wall -Wextra -Werror \
  "$root/examples/portable-apps/ANOTHER/assets.c" \
  "$root/examples/portable-apps/ANOTHER/video.c" \
  "$root/tests/another_world_video_self_test.c" -o "$build_dir/video"
"$build_dir/video"
${CC:-cc} -std=c11 -O2 -Wall -Wextra -Werror \
  "$root/examples/portable-apps/ANOTHER/assets.c" \
  "$root/examples/portable-apps/ANOTHER/video.c" \
  "$root/tests/another_world_background_self_test.c" -o "$build_dir/background"
"$build_dir/background"
${CC:-cc} -std=c11 -O2 -Wall -Wextra -Werror \
  "$root/examples/portable-apps/ANOTHER/assets.c" \
  "$root/examples/portable-apps/ANOTHER/video.c" \
  "$root/tests/another_world_page3_packed_self_test.c" -o "$build_dir/page3-packed"
"$build_dir/page3-packed"
${CC:-cc} -std=c11 -O2 -Wall -Wextra -Werror \
  "$root/examples/portable-apps/ANOTHER/display.c" \
  "$root/tests/another_world_display_self_test.c" -o "$build_dir/display"
"$build_dir/display"
${CC:-cc} -std=c11 -O2 -Wall -Wextra -Werror \
  "$root/examples/portable-apps/ANOTHER/assets.c" "$root/examples/portable-apps/ANOTHER/display_compact.c" \
  "$root/tests/another_world_display_compact_self_test.c" -o "$build_dir/display-compact"
"$build_dir/display-compact"
${CC:-cc} -std=c11 -O2 -Wall -Wextra -Werror \
  "$root/tests/another_world_pacing_self_test.c" -o "$build_dir/pacing"
"$build_dir/pacing"
${CC:-cc} -std=c11 -O2 -Wall -Wextra -Werror -I"$root/sdk/coproc" \
  "$root/examples/portable-apps/ANOTHER/assets.c" \
  "$root/examples/portable-apps/ANOTHER/audio.c" \
  "$root/examples/portable-apps/ANOTHER/m3_pcm.c" \
  "$root/tests/another_world_audio_self_test.c" -o "$build_dir/audio"
"$build_dir/audio"
${CC:-cc} -std=c11 -O2 -Wall -Wextra -Werror -I"$root/sdk/coproc" \
  "$root/examples/portable-apps/ANOTHER/m3_pcm.c" \
  "$root/tests/another_world_m3_pcm_self_test.c" -o "$build_dir/m3-pcm"
"$build_dir/m3-pcm"
python3 "$root/tests/spectrum_m3_runtime_fixture.py" --output "$build_dir/runtime"
${CC:-cc} -std=c11 -O2 -Wall -Wextra -Werror -Wno-misleading-indentation \
  -I"$build_dir/runtime" -c "$build_dir/runtime/stm3_runtime.c" -o "$build_dir/runtime.o"
${CC:-cc} -std=c11 -O2 -Wall -Wextra -Werror -I"$root/sdk/coproc" \
  -c "$root/examples/portable-apps/ANOTHER/m3_pcm.c" -o "$build_dir/m3-pcm.o"
${CXX:-c++} -std=c++17 -O2 -Wall -Wextra -Werror -I"$root/ports/picocalc" \
  -I"$build_dir/runtime" -I"$root/sdk/coproc" "$root/tests/another_world_m3_transport_self_test.cpp" \
  "$build_dir/runtime.o" "$build_dir/m3-pcm.o" -o "$build_dir/m3-transport"
"$build_dir/m3-transport"
${CC:-cc} -std=c11 -O2 -Wall -Wextra -Werror \
  "$root/examples/portable-apps/ANOTHER/assets.c" \
  "$root/examples/portable-apps/ANOTHER/video.c" \
  "$root/examples/portable-apps/ANOTHER/vm.c" \
  "$root/examples/portable-apps/ANOTHER/text.c" \
  "$root/tests/another_world_vm_self_test.c" -o "$build_dir/vm"
"$build_dir/vm"
if [ -n "${ANOTHER_WORLD_DATA:-}" ]; then
  ${CC:-cc} -std=c11 -O2 -Wall -Wextra -Werror -Dmain=another_app_main \
    -I"$root/sdk/portable/include" -I"$root/code" \
    -c "$root/examples/portable-apps/ANOTHER/main.c" -o "$build_dir/main.o"
  ${CC:-cc} -std=c11 -O2 -Wall -Wextra -Werror -I"$root/sdk/portable/include" -I"$root/code" \
    "$root/examples/portable-apps/ANOTHER/assets.c" "$root/examples/portable-apps/ANOTHER/video.c" \
    "$root/examples/portable-apps/ANOTHER/vm.c" "$root/examples/portable-apps/ANOTHER/text.c" \
    "$root/examples/portable-apps/ANOTHER/audio.c" "$root/examples/portable-apps/ANOTHER/display.c" \
    "$root/examples/portable-apps/ANOTHER/display_compact.c" \
    "$root/tests/another_world_app_host_test.c" \
    "$build_dir/main.o" -o "$build_dir/app"
  "$build_dir/app" "$ANOTHER_WORLD_DATA"
  "$build_dir/app" "$ANOTHER_WORLD_DATA" no-previous
  "$build_dir/app" "$ANOTHER_WORLD_DATA" no-framebuffer
  "$build_dir/app" "$ANOTHER_WORLD_DATA" no-background
  "$build_dir/app" "$ANOTHER_WORLD_DATA" pair-fallback
  "$build_dir/app" "$ANOTHER_WORLD_DATA" split
  "$build_dir/app" "$ANOTHER_WORLD_DATA" split-tail-failure
  ${CC:-cc} -std=c11 -O2 -Wall -Wextra -Werror -I"$root/sdk/portable/include" -I"$root/code" \
    "$root/examples/portable-apps/ANOTHER/assets.c" "$root/examples/portable-apps/ANOTHER/video.c" \
    "$root/examples/portable-apps/ANOTHER/vm.c" "$root/examples/portable-apps/ANOTHER/text.c" \
    "$root/examples/portable-apps/ANOTHER/audio.c" "$root/examples/portable-apps/ANOTHER/display.c" \
    "$root/examples/portable-apps/ANOTHER/display_compact.c" \
    "$root/tests/another_world_fragmentation_self_test.c" "$build_dir/main.o" -o "$build_dir/fragmentation"
  "$build_dir/fragmentation" "$ANOTHER_WORLD_DATA" "$build_dir/fragmentation.state"
  "$build_dir/fragmentation" "$ANOTHER_WORLD_DATA" "$build_dir/fragmentation.state"
  ${CC:-cc} -std=c11 -O2 -Wall -Wextra -Werror \
    "$root/examples/portable-apps/ANOTHER/assets.c" "$root/examples/portable-apps/ANOTHER/video.c" \
    "$root/examples/portable-apps/ANOTHER/vm.c" "$root/examples/portable-apps/ANOTHER/text.c" \
    "$root/tests/another_world_password_test.c" -o "$build_dir/password"
  "$build_dir/password" "$ANOTHER_WORLD_DATA"
  ${CC:-cc} -std=c11 -O2 -Wall -Wextra -Werror -I"$root/sdk/coproc" \
    "$root/examples/portable-apps/ANOTHER/assets.c" "$root/examples/portable-apps/ANOTHER/video.c" \
    "$root/examples/portable-apps/ANOTHER/vm.c" "$root/examples/portable-apps/ANOTHER/text.c" \
    "$root/examples/portable-apps/ANOTHER/audio.c" "$root/examples/portable-apps/ANOTHER/m3_pcm.c" \
    "$root/tests/another_world_game_probe.c" -o "$build_dir/game"
  "$build_dir/game" "$ANOTHER_WORLD_DATA"
  "$build_dir/game" "$ANOTHER_WORLD_DATA" 5000
  ${CC:-cc} -std=c11 -O2 -Wall -Wextra -Werror -DAW_DISPLAY_ANALYZE -I"$root/sdk/coproc" \
    "$root/examples/portable-apps/ANOTHER/assets.c" "$root/examples/portable-apps/ANOTHER/video.c" \
    "$root/examples/portable-apps/ANOTHER/vm.c" "$root/examples/portable-apps/ANOTHER/text.c" \
    "$root/examples/portable-apps/ANOTHER/audio.c" "$root/examples/portable-apps/ANOTHER/m3_pcm.c" \
    "$root/examples/portable-apps/ANOTHER/display.c" "$root/tests/another_world_game_probe.c" -o "$build_dir/display-game"
  "$build_dir/display-game" "$ANOTHER_WORLD_DATA" 5000
  ${CC:-cc} -std=c11 -O2 -Wall -Wextra -Werror -DAW_DISPLAY_ANALYZE -DAW_COMPACT_DISPLAY -DAW_VIDEO_BACKGROUND -DAW_VIDEO_PACKED3 -I"$root/sdk/coproc" \
    "$root/examples/portable-apps/ANOTHER/assets.c" "$root/examples/portable-apps/ANOTHER/video.c" \
    "$root/examples/portable-apps/ANOTHER/vm.c" "$root/examples/portable-apps/ANOTHER/text.c" \
    "$root/examples/portable-apps/ANOTHER/audio.c" "$root/examples/portable-apps/ANOTHER/m3_pcm.c" \
    "$root/examples/portable-apps/ANOTHER/display_compact.c" "$root/tests/another_world_game_probe.c" -o "$build_dir/compact-game"
  "$build_dir/compact-game" "$ANOTHER_WORLD_DATA" 5000
fi

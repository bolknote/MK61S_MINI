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
  "$root/examples/portable-apps/ANOTHER/assets.c" "$root/examples/portable-apps/ANOTHER/prepared.c" \
  "$root/tests/another_world_prepared_self_test.c" -o "$build_dir/prepared"
"$build_dir/prepared"
python3 "$root/tests/another_world_cache_tools_self_test.py"
${CC:-cc} -std=c11 -O2 -Wall -Wextra -Werror \
  "$root/examples/portable-apps/ANOTHER/text.c" \
  "$root/tests/another_world_text_self_test.c" -o "$build_dir/text"
"$build_dir/text"
${CC:-cc} -std=c11 -O2 -Wall -Wextra -Werror \
  "$root/examples/portable-apps/ANOTHER/assets.c" \
  "$root/tests/another_world_unpack_self_test.c" -o "$build_dir/unpack"
"$build_dir/unpack"
${CC:-cc} -std=c11 -O2 -Wall -Wextra -Werror -DAW_ASSET_CACHE_SLOTS=1 \
  "$root/examples/portable-apps/ANOTHER/assets.c" \
  "$root/tests/another_world_unpack_self_test.c" -o "$build_dir/unpack-single-slot"
"$build_dir/unpack-single-slot"
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
  if [ -f "$ANOTHER_WORLD_DATA/AWCACHE.BIN" ]; then
    ${CC:-cc} -std=c11 -O2 -Wall -Wextra -Werror -Dmain=another_cache_builder_main \
      -I"$root/sdk/portable/include" -I"$root/code" \
      -c "$root/tests/another_world_cache_device_builder.c" -o "$build_dir/cache-builder.o"
    ${CC:-cc} -std=c11 -O2 -Wall -Wextra -Werror -I"$root/sdk/portable/include" -I"$root/code" \
      "$root/examples/portable-apps/ANOTHER/assets.c" "$root/tests/another_world_cache_device_host_test.c" \
      "$build_dir/cache-builder.o" -o "$build_dir/cache-builder"
    "$build_dir/cache-builder" "$ANOTHER_WORLD_DATA"
    "$build_dir/cache-builder" "$ANOTHER_WORLD_DATA" deny
  fi
  ${CC:-cc} -std=c11 -O2 -Wall -Wextra -Werror -Dmain=another_app_main \
    -I"$root/sdk/portable/include" -I"$root/code" \
    -c "$root/examples/portable-apps/ANOTHER/main.c" -o "$build_dir/main.o"
  ${CC:-cc} -std=c11 -O2 -Wall -Wextra -Werror -I"$root/sdk/portable/include" -I"$root/code" \
    "$root/examples/portable-apps/ANOTHER/assets.c" "$root/examples/portable-apps/ANOTHER/prepared.c" "$root/examples/portable-apps/ANOTHER/video.c" \
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
    "$root/examples/portable-apps/ANOTHER/assets.c" "$root/examples/portable-apps/ANOTHER/prepared.c" "$root/examples/portable-apps/ANOTHER/video.c" \
    "$root/examples/portable-apps/ANOTHER/vm.c" "$root/examples/portable-apps/ANOTHER/text.c" \
    "$root/examples/portable-apps/ANOTHER/audio.c" "$root/examples/portable-apps/ANOTHER/display.c" \
    "$root/examples/portable-apps/ANOTHER/display_compact.c" \
    "$root/tests/another_world_fragmentation_self_test.c" "$build_dir/main.o" -o "$build_dir/fragmentation"
  "$build_dir/fragmentation" "$ANOTHER_WORLD_DATA" "$build_dir/fragmentation.state"
  "$build_dir/fragmentation" "$ANOTHER_WORLD_DATA" "$build_dir/fragmentation.state"
  # Exercise an earlier fragmented layout even with 856 fewer bytes.
  "$build_dir/fragmentation" "$ANOTHER_WORLD_DATA" "$build_dir/fragmentation-growth.state" 856
  "$build_dir/fragmentation" "$ANOTHER_WORLD_DATA" "$build_dir/fragmentation-growth.state" 856
  # Cold Pico observation: compacting the text table returned 624 bytes to
  # the large free block, enough to reserve the complete background cache.
  "$build_dir/fragmentation" "$ANOTHER_WORLD_DATA" "$build_dir/fragmentation-cold.state" 624 cold
  "$build_dir/fragmentation" "$ANOTHER_WORLD_DATA" "$build_dir/fragmentation-cold.state" 624 cold
  # Long-lived VM/display/audio state uses reserved stack, so the video cache
  # fits even if another 1600 bytes of the large hole are unavailable.
  "$build_dir/fragmentation" "$ANOTHER_WORLD_DATA" "$build_dir/fragmentation-warm.state" 2160 warm
  "$build_dir/fragmentation" "$ANOTHER_WORLD_DATA" "$build_dir/fragmentation-warm.state" 2160 warm
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

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
${CC:-cc} -std=c11 -O2 -Wall -Wextra -Werror -DAW_VIDEO_PACKED_CACHE=1 \
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
  "$root/examples/portable-apps/ANOTHER/assets.c" "$root/examples/portable-apps/ANOTHER/display_compact.c" \
  "$root/examples/portable-apps/ANOTHER/display_pages.c" "$root/tests/another_world_display_pages_self_test.c" -o "$build_dir/display-pages"
"$build_dir/display-pages"
${CXX:-c++} -std=c++17 -O2 -fno-exceptions -Wall -Wextra -Werror -I"$root/code" \
  -c "$root/examples/portable-apps/ANOTHER/display_storm.cpp" -o "$build_dir/storm.o"
${CXX:-c++} -std=c++17 -O2 -fno-exceptions -Wall -Wextra -Werror -I"$root/code" \
  -c "$root/code/zx0.cpp" -o "$build_dir/zx0.o"
for unit in assets display_compact display_pages; do
  ${CC:-cc} -std=c11 -O2 -Wall -Wextra -Werror \
    -c "$root/examples/portable-apps/ANOTHER/$unit.c" -o "$build_dir/storm-$unit.o"
done
${CXX:-c++} -std=c++17 -O2 -Wall -Wextra -Werror \
  "$root/tests/another_world_storm_self_test.cpp" "$build_dir/storm.o" "$build_dir/zx0.o" \
  "$build_dir"/storm-*.o -o "$build_dir/storm"
"$build_dir/storm"
${CC:-cc} -std=c11 -O2 -Wall -Wextra -Werror \
  -I"$root/sdk/portable/include" -I"$root/code" \
  "$root/tests/another_world_intro_resume_self_test.c" \
  "$root/examples/portable-apps/ANOTHER/assets.c" "$root/examples/portable-apps/ANOTHER/prepared.c" \
  "$root/examples/portable-apps/ANOTHER/video.c" "$root/examples/portable-apps/ANOTHER/vm.c" \
  "$root/examples/portable-apps/ANOTHER/text.c" "$root/examples/portable-apps/ANOTHER/audio.c" \
  "$root/examples/portable-apps/ANOTHER/display.c" "$root/examples/portable-apps/ANOTHER/display_compact.c" \
  "$root/examples/portable-apps/ANOTHER/display_pages.c" "$build_dir/storm.o" "$build_dir/zx0.o" \
  -o "$build_dir/intro-resume"
"$build_dir/intro-resume"
${CC:-cc} -std=c11 -O2 -Wall -Wextra -Werror -Dmain=lcd_pages_probe_main \
  -I"$root/sdk/portable/include" -I"$root/code" \
  -c "$root/tests/picocalc_lcd_pages_probe.c" -o "$build_dir/lcd-pages-probe.o"
${CC:-cc} -std=c11 -O2 -Wall -Wextra -Werror -I"$root/sdk/portable/include" -I"$root/code" \
  "$root/tests/picocalc_lcd_pages_probe_self_test.c" "$build_dir/lcd-pages-probe.o" -o "$build_dir/lcd-pages-probe"
"$build_dir/lcd-pages-probe"
${CC:-cc} -std=c11 -O2 -Wall -Wextra -Werror \
  "$root/tests/picocalc_lcd_readback_self_test.c" -o "$build_dir/lcd-readback"
"$build_dir/lcd-readback"
${CC:-cc} -std=c11 -O2 -Wall -Wextra -Werror -DPICOCALC_LCD_READBACK_HOST -Dmain=lcd_read_probe_main \
  -I"$root/sdk/portable/include" -I"$root/code" \
  -c "$root/tests/picocalc_lcd_read_probe.c" -o "$build_dir/lcd-read-probe.o"
${CC:-cc} -std=c11 -O2 -Wall -Wextra -Werror -I"$root/sdk/portable/include" -I"$root/code" \
  "$root/tests/picocalc_lcd_read_probe_self_test.c" "$build_dir/lcd-read-probe.o" -o "$build_dir/lcd-read-probe"
"$build_dir/lcd-read-probe"
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
    "$root/examples/portable-apps/ANOTHER/display_compact.c" "$root/examples/portable-apps/ANOTHER/display_pages.c" \
    "$root/tests/another_world_app_host_test.c" \
    "$build_dir/main.o" "$build_dir/storm.o" "$build_dir/zx0.o" -o "$build_dir/app"
  "$build_dir/app" "$ANOTHER_WORLD_DATA"
  "$build_dir/app" "$ANOTHER_WORLD_DATA" no-previous
  "$build_dir/app" "$ANOTHER_WORLD_DATA" no-framebuffer
  "$build_dir/app" "$ANOTHER_WORLD_DATA" no-background
  "$build_dir/app" "$ANOTHER_WORLD_DATA" pair-fallback
  "$build_dir/app" "$ANOTHER_WORLD_DATA" split
  "$build_dir/app" "$ANOTHER_WORLD_DATA" split-tail-failure
  "$build_dir/app" "$ANOTHER_WORLD_DATA" pages
  "$build_dir/app" "$ANOTHER_WORLD_DATA" pages-select-fail
  "$build_dir/app" "$ANOTHER_WORLD_DATA" pages-show-fail
  "$build_dir/app" "$ANOTHER_WORLD_DATA" pages-legacy
  "$build_dir/app" "$ANOTHER_WORLD_DATA" cancel-loading
  # Exercise the actual shared-buffer session and its arena, including the
  # old individual-buffer fallback and retry when the PCM reservation blocks
  # the mandatory first frame.
  for unit in assets prepared video vm text audio display display_compact display_pages; do
    ${CC:-cc} -std=c11 -O2 -Wall -Wextra -Werror -I"$root/sdk/portable/include" -I"$root/code" \
      -c "$root/examples/portable-apps/ANOTHER/$unit.c" -o "$build_dir/real-$unit.o"
  done
  ${CC:-cc} -std=c11 -O2 -Wall -Wextra -Werror -DAW_TEST_REAL_SESSION=1 \
    -I"$root/sdk/portable/include" -I"$root/code" \
    -c "$root/tests/another_world_app_host_test.c" -o "$build_dir/real-app.o"
  ${CXX:-c++} -std=c++17 -O2 -Wall -Wextra -Werror -I"$root/code" \
    -c "$root/tests/another_world_buffer_session_fixture.cpp" -o "$build_dir/real-session.o"
  ${CXX:-c++} -std=c++17 -O2 -Wall -Wextra -Werror -I"$root/code" \
    -c "$root/code/shared_memory_buffer.cpp" -o "$build_dir/real-buffer.o"
  ${CXX:-c++} "$build_dir"/real-*.o "$build_dir/main.o" "$build_dir/storm.o" "$build_dir/zx0.o" -o "$build_dir/real-app"
  "$build_dir/real-app" "$ANOTHER_WORLD_DATA" arena
  "$build_dir/real-app" "$ANOTHER_WORLD_DATA" arena-no-reserve
  "$build_dir/real-app" "$ANOTHER_WORLD_DATA" arena-screen-retry
  ${CC:-cc} -std=c11 -O2 -Wall -Wextra -Werror -I"$root/sdk/portable/include" -I"$root/code" \
    "$root/examples/portable-apps/ANOTHER/assets.c" "$root/examples/portable-apps/ANOTHER/prepared.c" "$root/examples/portable-apps/ANOTHER/video.c" \
    "$root/examples/portable-apps/ANOTHER/vm.c" "$root/examples/portable-apps/ANOTHER/text.c" \
    "$root/examples/portable-apps/ANOTHER/audio.c" "$root/examples/portable-apps/ANOTHER/display.c" \
    "$root/examples/portable-apps/ANOTHER/display_compact.c" "$root/examples/portable-apps/ANOTHER/display_pages.c" \
    "$root/tests/another_world_fragmentation_self_test.c" "$build_dir/main.o" \
    "$build_dir/storm.o" "$build_dir/zx0.o" -o "$build_dir/fragmentation"
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
  # Exercise the measured resident SRAM budget with the current ARM image.
  image_growth=28
  if [ -n "${ANOTHER_WORLD_APP_META:-}" ]; then
    image_growth=$(python3 -c 'import json,sys; print(json.load(open(sys.argv[1]))["memory_bytes"] - 41124)' "$ANOTHER_WORLD_APP_META")
  fi
  "$build_dir/fragmentation" "$ANOTHER_WORLD_DATA" "$build_dir/fragmentation-tight.state" "$image_growth" tight
  "$build_dir/fragmentation" "$ANOTHER_WORLD_DATA" "$build_dir/fragmentation-tight.state" "$image_growth" tight
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
  ${CC:-cc} -std=c11 -O2 -Wall -Wextra -Werror -DAW_DISPLAY_ANALYZE -DAW_COMPACT_DISPLAY -DAW_VIDEO_BACKGROUND -DAW_VIDEO_PACKED3 -DAW_VIDEO_PACKED_CACHE=1 -I"$root/sdk/coproc" \
    "$root/examples/portable-apps/ANOTHER/assets.c" "$root/examples/portable-apps/ANOTHER/video.c" \
    "$root/examples/portable-apps/ANOTHER/vm.c" "$root/examples/portable-apps/ANOTHER/text.c" \
    "$root/examples/portable-apps/ANOTHER/audio.c" "$root/examples/portable-apps/ANOTHER/m3_pcm.c" \
    "$root/examples/portable-apps/ANOTHER/display_compact.c" "$root/tests/another_world_game_probe.c" -o "$build_dir/compact-game"
  "$build_dir/compact-game" "$ANOTHER_WORLD_DATA" 5000
  ${CC:-cc} -std=c11 -O2 -Wall -Wextra -Werror -DAW_DISPLAY_ANALYZE -DAW_COMPACT_DISPLAY -DAW_TWO_PAGE_ANALYZE -DAW_VIDEO_BACKGROUND -DAW_VIDEO_PACKED3 -DAW_VIDEO_PACKED_CACHE=1 -I"$root/sdk/coproc" \
    "$root/examples/portable-apps/ANOTHER/assets.c" "$root/examples/portable-apps/ANOTHER/video.c" \
    "$root/examples/portable-apps/ANOTHER/vm.c" "$root/examples/portable-apps/ANOTHER/text.c" \
    "$root/examples/portable-apps/ANOTHER/audio.c" "$root/examples/portable-apps/ANOTHER/m3_pcm.c" \
    "$root/examples/portable-apps/ANOTHER/display_compact.c" "$root/examples/portable-apps/ANOTHER/display_pages.c" \
    "$root/tests/another_world_game_probe.c" -o "$build_dir/pages-game"
  "$build_dir/pages-game" "$ANOTHER_WORLD_DATA" 5000
  "$build_dir/pages-game" "$ANOTHER_WORLD_DATA" camera-cut
  app="$root/examples/portable-apps/ANOTHER"
  zx0="$root/tools/apps/packer/third_party/zx0"
  ${CC:-cc} -std=c11 -O2 -Wall -Wextra -Werror -I"$app" -I"$zx0" \
    "$root/tools/apps/another/prepare_storm.c" "$app/assets.c" "$app/video.c" "$app/vm.c" \
    "$app/text.c" "$app/audio.c" "$app/display_compact.c" "$app/display_pages.c" \
    "$zx0/optimize.c" "$zx0/compress.c" "$zx0/memory.c" -o "$build_dir/prepare-storm"
  if "$build_dir/prepare-storm" "$ANOTHER_WORLD_DATA" "$build_dir/AWSTORM.BIN" >/dev/null; then
    python3 "$root/tests/another_world_spi/writeback/edge/check_release.py" "$ANOTHER_WORLD_DATA" --cache "$build_dir/AWSTORM.BIN"
    ${CC:-cc} -std=c11 -O2 -Wall -Wextra -Werror -I"$root/sdk/coproc" \
      -DAW_DISPLAY_ANALYZE -DAW_COMPACT_DISPLAY -DAW_TWO_PAGE_ANALYZE -DAW_PROBE_FIRST_PART \
      -DAW_VIDEO_BACKGROUND -DAW_VIDEO_PACKED3 -DAW_VIDEO_PACKED_CACHE=1 -DAW_TEST_STORM \
      "$app/assets.c" "$app/video.c" "$app/vm.c" "$app/text.c" "$app/audio.c" "$app/m3_pcm.c" \
      "$app/display_compact.c" "$app/display_pages.c" "$root/tests/another_world_game_probe.c" \
      "$build_dir/storm.o" "$build_dir/zx0.o" -o "$build_dir/storm-game"
    AW_STORM_CACHE="$build_dir/AWSTORM.BIN" "$build_dir/storm-game" "$ANOTHER_WORLD_DATA" 3000
    AW_STORM_CACHE="$build_dir/AWSTORM.BIN" AW_STORM_OVERLAP=1 "$build_dir/storm-game" "$ANOTHER_WORLD_DATA" 3000
    AW_STORM_CACHE="$build_dir/AWSTORM.BIN" AW_STORM_TAIL_MISMATCH=visible "$build_dir/storm-game" "$ANOTHER_WORLD_DATA" 3000
    AW_STORM_CACHE="$build_dir/AWSTORM.BIN" AW_STORM_TAIL_MISMATCH=black "$build_dir/storm-game" "$ANOTHER_WORLD_DATA" 3000
    AW_STORM_CACHE="$build_dir/AWSTORM.BIN" AW_STORM_INCOMPLETE_BLACK=1 "$build_dir/storm-game" "$ANOTHER_WORLD_DATA" 3000
    AW_STORM_CACHE="$build_dir/AWSTORM.BIN" AW_STORM_LIMITED_TAIL=1 "$build_dir/storm-game" "$ANOTHER_WORLD_DATA" 3000
    AW_STORM_CACHE="$build_dir/AWSTORM.BIN" AW_STORM_RETURN_MISMATCH=1 "$build_dir/storm-game" "$ANOTHER_WORLD_DATA" 3000
    AW_STORM_CACHE="$build_dir/AWSTORM.BIN" AW_STORM_BASE_PRELUDE=1 "$build_dir/storm-game" "$ANOTHER_WORLD_DATA" 3000
    AW_STORM_CACHE="$build_dir/AWSTORM.BIN" AW_STORM_TIGHT_PSRAM=1 "$build_dir/storm-game" "$ANOTHER_WORLD_DATA" 3000
  elif [ "$?" -ne 2 ]; then
    exit 1
  fi
fi

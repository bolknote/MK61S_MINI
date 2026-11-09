#!/usr/bin/env bash
set -euo pipefail
root="$(cd "$(dirname "$0")/.." && pwd)"
build="$(mktemp -d "${TMPDIR:-/tmp}/mk61-spectrum-m3.XXXXXX")"
trap 'rm -rf "$build"' EXIT
python3 "$root/tests/spectrum_m3_runtime_fixture.py" --output "$build/runtime"
python3 "$root/tests/spectrum_m3_game_probe_packaging_self_test.py"
clang -std=c11 -O2 -Wall -Wextra -Werror -fsanitize=address,undefined \
    -fno-sanitize-recover=all "$root/tests/pcm_repeat_self_test.c" -o "$build/repeat-codec"
"$build/repeat-codec"
sound_flags=()
if [[ "${SPECTRUM_M3_FAST_INIT:-0}" != 0 ]]; then
    sound_flags=(-DEMU2149_M3_AUDIO=1 "-DSPECTRUM_M3_FAST_INIT=$SPECTRUM_M3_FAST_INIT")
fi
sound_flags+=("-DSPECTRUM_M3_SLICE_SAMPLES=${SPECTRUM_M3_SLICE_SAMPLES:-16}")
sound_flags+=("-DSPECTRUM_M3_STEP_BUDGET_US=${SPECTRUM_M3_STEP_BUDGET_US:-0}")
sound_flags+=("-DSPECTRUM_M3_INIT_BUDGET_US=${SPECTRUM_M3_INIT_BUDGET_US:-100}")
sound_flags+=("-DSPECTRUM_M3_SILENT_BATCH=${SPECTRUM_M3_SILENT_BATCH:-0}")
clang -std=c11 -O2 -Wall -Wextra -Werror -fsanitize=address,undefined \
    -fno-sanitize-recover=all -fno-omit-frame-pointer \
    "${sound_flags[@]}" \
    -I"$root/sdk/coproc" \
    "$root/tests/spectrum_m3_audio_self_test.c" \
    "$root/examples/portable-apps/SPECTRUM/m3_audio_module.c" \
    "$root/examples/portable-apps/SPECTRUM/peripherals.c" \
    "$root/third_party/emu2149/emu2149.c" -o "$build/test"
"$build/test"
if [[ "${SPECTRUM_M3_FAST_INIT:-0}" != 0 ]]; then
    clang -std=c11 -O2 -Wall -Wextra -Werror -fsanitize=address,undefined \
        -fno-sanitize-recover=all -fno-omit-frame-pointer -DEMU2149_M3_AUDIO=1 \
        "$root/tests/emu2149_quality_self_test.c" -o "$build/quality"
    "$build/quality"
fi
clang++ -std=c++17 -O2 -Wall -Wextra -Werror -fsanitize=address,undefined \
    -fno-sanitize-recover=all -fno-omit-frame-pointer \
    -I"$root/code" -I"$root/ports/picocalc" \
    "$root/tests/spectrum_m3_packets_self_test.cpp" -o "$build/packets"
"$build/packets"
clang -std=c11 -O2 -Wall -Wextra -Werror -Wno-misleading-indentation \
    -fsanitize=address,undefined -fno-sanitize-recover=all \
    -I"$build/runtime" \
    -c "$build/runtime/stm3_runtime.c" -o "$build/runtime.o"
clang++ -std=c++17 -O2 -Wall -Wextra -Werror -fsanitize=address,undefined \
    -fno-sanitize-recover=all -fno-omit-frame-pointer \
    -I"$root/ports/picocalc" -I"$build/runtime" \
    "$root/tests/spectrum_m3_wire_self_test.cpp" "$build/runtime.o" -o "$build/wire"
"$build/wire"
clang -std=c11 -O2 -Wall -Wextra -Werror -fsanitize=address,undefined -fno-sanitize-recover=all \
    -I"$root/sdk/coproc" -c "$root/sdk/coproc/stm3_client.c" -o "$build/client.o"
clang++ -std=c++17 -O2 -Wall -Wextra -Werror -fsanitize=address,undefined \
    -fno-sanitize-recover=all -fno-omit-frame-pointer \
    -I"$root/ports/picocalc" \
    -I"$build/runtime" \
    -I"$root/sdk/coproc" \
    "$root/tests/spectrum_m3_completion_self_test.cpp" "$build/runtime.o" "$build/client.o" -o "$build/completion"
"$build/completion"
clang++ -std=c++17 -O2 -Wall -Wextra -Werror -fsanitize=address,undefined \
    -fno-sanitize-recover=all -fno-omit-frame-pointer \
    -I"$root/code" -I"$root/ports/picocalc" -I"$root/sdk/coproc" \
    -I"$build/runtime" \
    "$root/tests/spectrum_m3_engine_self_test.cpp" "$build/runtime.o" -o "$build/engine"
"$build/engine"
clang++ -std=c++17 -O2 -Wall -Wextra -Werror -fsanitize=address,undefined \
    -fno-sanitize-recover=all -I"$root/ports/picocalc" \
    "$root/tests/picocalc_pwm_duty_ring_self_test.cpp" -o "$build/duty-ring"
"$build/duty-ring"

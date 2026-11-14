#!/usr/bin/env bash
set -euo pipefail
root="$(cd "$(dirname "$0")/.." && pwd)"
build="$(mktemp -d "${TMPDIR:-/tmp}/mk61-spectrum.XXXXXX")"
trap 'rm -rf "$build"' EXIT
flags=()
if [[ "${MK61_TEST_SANITIZERS:-0}" == 1 ]]; then flags=(-fsanitize=address,undefined -fno-omit-frame-pointer); fi
python3 "$root/tests/spectrum_rom_storage_self_test.py"
python3 "$root/tests/spectrum_m3_observer_self_test.py"
clang -std=c11 -O2 -Wall -Wextra -Werror "${flags[@]}" \
    -I"$root/sdk/portable/include" -I"$root/code" \
    "$root/tests/spectrum_display_self_test.c" -o "$build/display"
"$build/display" "$root/third_party/spectrum-rom/48.rom"
clang -std=c11 -O2 -Wall -Wextra -Werror -DMK61_TARGET_PICOCALC=1 "${flags[@]}" \
    "$root/tests/z80_alu_self_test.c" "$root/third_party/z80/z80.c" -o "$build/z80-alu"
"$build/z80-alu"
for test in spectrum_self_test spectrum_ldir_self_test spectrum_batch_self_test spectrum_audio_timeline_self_test; do
clang -std=c11 -O2 -Wall -Wextra -Werror -DMK61_TARGET_PICOCALC=1 "${flags[@]}" \
    "$root/tests/$test.c" "$root/examples/portable-apps/SPECTRUM/spectrum.c" \
    "$root/examples/portable-apps/SPECTRUM/memory.c" \
    "$root/examples/portable-apps/SPECTRUM/peripherals.c" \
    "$root/examples/portable-apps/SPECTRUM/fdc.c" "$root/examples/portable-apps/SPECTRUM/spi.c" \
    "$root/examples/portable-apps/SPECTRUM/mapper.c" \
    "$root/third_party/z80/z80.c" "$root/third_party/emu2149/emu2149.c" -o "$build/$test"
if [[ "$test" == spectrum_self_test ]]; then "$build/$test" "$root/third_party/spectrum-rom/48.rom"
else "$build/$test"; fi
done
for test in spectrum_hil_timing_self_test spectrum_hil_games_self_test spectrum_pacing_self_test; do
    clang -std=c11 -O2 -Wall -Wextra -Werror -DMK61_TARGET_PICOCALC=1 "${flags[@]}" \
        -I"$root/sdk/portable/include" -I"$root/code" \
        "$root/tests/$test.c" "$root/examples/portable-apps/SPECTRUM/spectrum.c" \
        "$root/examples/portable-apps/SPECTRUM/memory.c" \
        "$root/examples/portable-apps/SPECTRUM/peripherals.c" "$root/examples/portable-apps/SPECTRUM/fdc.c" \
        "$root/examples/portable-apps/SPECTRUM/spi.c" "$root/examples/portable-apps/SPECTRUM/mapper.c" \
        "$root/examples/portable-apps/SPECTRUM/media.c" "$root/examples/portable-apps/SPECTRUM/ui.c" \
        "$root/third_party/z80/z80.c" "$root/third_party/emu2149/emu2149.c" -o "$build/$test"
    "$build/$test" "$build/$test-wire.txt"
done
for test in emu2149_silent_self_test emu2149_quality_self_test; do
    sources=("$root/tests/$test.c")
    if [[ "$test" == emu2149_silent_self_test ]]; then sources+=("$root/third_party/emu2149/emu2149.c"); fi
    clang -std=c11 -O2 -Wall -Wextra -Werror "${flags[@]}" \
        "${sources[@]}" -o "$build/$test"
    "$build/$test"
done
for test in spectrum_disk_self_test spectrum_extensions_self_test spectrum_external_rom_self_test; do
    clang -std=c11 -O2 -Wall -Wextra -Werror -pthread "${flags[@]}" \
        "$root/tests/$test.c" "$root/examples/portable-apps/SPECTRUM/spectrum.c" \
        "$root/examples/portable-apps/SPECTRUM/memory.c" "$root/examples/portable-apps/SPECTRUM/peripherals.c" \
        "$root/examples/portable-apps/SPECTRUM/fdc.c" "$root/examples/portable-apps/SPECTRUM/spi.c" \
        "$root/examples/portable-apps/SPECTRUM/mapper.c" "$root/examples/portable-apps/SPECTRUM/media.c" \
        "$root/third_party/z80/z80.c" "$root/third_party/emu2149/emu2149.c" -o "$build/$test"
    if [[ "$test" == spectrum_disk_self_test && -n "${SPECTRUM_DEVICE_ASSETS:-}" ]]; then
        "$build/$test" "$root/third_party/spectrum-rom" "$SPECTRUM_DEVICE_ASSETS"
    else "$build/$test"; fi
done
if [[ -n "${SPECTRUM_DEVICE_ASSETS:-}" ]]; then
    python3 - "$root" "$SPECTRUM_DEVICE_ASSETS" "$build/app-assets" <<'PY'
import sys, shutil
from pathlib import Path
sys.path.insert(0, str(Path(sys.argv[1])/'tools'))
from tools.apps.spectrum.build_spectrum_app import copy_assets
target=Path(sys.argv[3]);copy_assets(target)
for name in ('trdos.rom','esxmmc.rom','ESXDOS.img','BLANK.trd'):
    shutil.copy2(Path(sys.argv[2])/name,target/name)
import struct
# Original fixtures for FILE_OPEN; external paths intentionally differ
# from the APP/ROM directory. Disk images remain read-only during tests.
snapshot=(target/'DEMO.sna').read_bytes();header=bytearray(30)
struct.pack_into('<HH',header,6,0x8000,0xFFFE);header[27]=header[28]=header[29]=1
(target/'OPEN.Z80').write_bytes(header+snapshot[27:])
empty_scl=b'SINCLAIR\x00';(target/'OPEN.SCL').write_bytes(empty_scl+struct.pack('<I',sum(empty_scl)))
(target/'BROKEN.z80').write_bytes(b'\xFF\x00\x80')
PY
    clang -std=c11 -O2 -Wall -Wextra -Werror "${flags[@]}" \
        -I"$root/sdk/portable/include" -I"$root/code" \
        "$root/tests/spectrum_app_self_test.c" "$root/examples/portable-apps/SPECTRUM/spectrum.c" \
        "$root/examples/portable-apps/SPECTRUM/memory.c" "$root/examples/portable-apps/SPECTRUM/peripherals.c" \
        "$root/examples/portable-apps/SPECTRUM/fdc.c" "$root/examples/portable-apps/SPECTRUM/spi.c" \
        "$root/examples/portable-apps/SPECTRUM/mapper.c" "$root/examples/portable-apps/SPECTRUM/media.c" \
        "$root/third_party/z80/z80.c" "$root/third_party/emu2149/emu2149.c" -o "$build/app"
    "$build/app" "$build/app-assets"
    SPECTRUM_LEGACY_LCD=1 "$build/app" "$build/app-assets"
    for selected in DEMO.sna DEMO128.sna OPEN.Z80 BLANK.trd OPEN.SCL; do
        SPECTRUM_OPEN_FILE="$selected" "$build/app" "$build/app-assets"
    done
    for selected in missing unsupported.tap BROKEN.z80; do
        SPECTRUM_OPEN_FILE="$selected" SPECTRUM_OPEN_ERROR=1 "$build/app" "$build/app-assets"
    done
    SPECTRUM_REMOTE_AUDIO=1 "$build/app" "$build/app-assets"
    SPECTRUM_REMOTE_AUDIO=1 SPECTRUM_OPEN_FILE=DEMO128.sna "$build/app" "$build/app-assets"
fi
clang++ -std=c++17 -O2 -Wall -Wextra -Werror "${flags[@]}" \
    -I"$root/ports/picocalc" -I"$root/code" \
    "$root/tests/picocalc_color_self_test.cpp" -o "$build/color"
"$build/color"

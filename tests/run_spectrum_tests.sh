#!/usr/bin/env bash
set -euo pipefail
root="$(cd "$(dirname "$0")/.." && pwd)"
build="$(mktemp -d "${TMPDIR:-/tmp}/mk61-spectrum.XXXXXX")"
trap 'rm -rf "$build"' EXIT
flags=()
if [[ "${MK61_TEST_SANITIZERS:-0}" == 1 ]]; then flags=(-fsanitize=address,undefined -fno-omit-frame-pointer); fi
app="$root/examples/portable-apps/SPECTRUM"
media=("$app/tape.c" "$app/szx.c" "$app/pentagon_video.c" "$app/inflate.c" "$app/preferences.c")
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
        "$root/examples/portable-apps/SPECTRUM/media.c" "$root/examples/portable-apps/SPECTRUM/ui.c" "${media[@]}" \
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
clang -std=c11 -O2 -Wall -Wextra -Werror "${flags[@]}" \
    -I"$root/sdk/portable/include" -I"$root/code" \
    "$root/tests/spectrum_media_features_self_test.c" "${media[@]}" \
    "$app/spectrum.c" "$app/memory.c" "$app/mapper.c" "$app/peripherals.c" "$app/spi.c" "$app/fdc.c" \
    "$root/third_party/z80/z80.c" "$root/third_party/emu2149/emu2149.c" -lz -o "$build/media-features"
"$build/media-features" "$root/third_party/spectrum-rom/48.rom" \
    "$root/third_party/spectrum-rom/128-0.rom" "$root/third_party/spectrum-rom/128-1.rom"
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
banked=(target/'DEMO128.sna').read_bytes()
header[6:8]=bytes(2)
extended=struct.pack('<HBBBBB',0x8000,3,16,0,0,0)+bytes(16)
pages=[bytes(16384) for _ in range(8)]
for index,bank in enumerate((5,2,0)):
    pages[bank]=banked[27+index*16384:27+(index+1)*16384]
(target/'OPEN128.Z80').write_bytes(header+struct.pack('<H',len(extended))+extended+b''.join(
    struct.pack('<HB',0xffff,bank+3)+page for bank,page in enumerate(pages)))
empty_scl=b'SINCLAIR\x00';(target/'OPEN.SCL').write_bytes(empty_scl+struct.pack('<I',sum(empty_scl)))
(target/'BROKEN.z80').write_bytes(b'\xFF\x00\x80')
shutil.copy2(target/'ESXDOS.img', target/'GAMES.img')
# The normal file handler must route Timex and extended Pentagon snapshots.
timex_header=bytearray(header);timex_header[6:8]=bytes(2)
timex_extended=bytearray(54);struct.pack_into('<H',timex_extended,0,0x8000)
timex_extended[2]=14;timex_extended[4]=6
(target/'TIMEX.Z80').write_bytes(timex_header+struct.pack('<H',54)+timex_extended+b''.join(
    struct.pack('<HB',0xffff,page)+snapshot[27+i*16384:27+(i+1)*16384] for i,page in enumerate((8,4,5))))
def screen_snapshot(name,model,mode,banks):
    hicolor=mode==2 and model==1
    cpu=bytearray(37);struct.pack_into('<HH',cpu,20,0xfffe,0x8000 if hicolor else 0x8001)
    cpu[28]=2 if hicolor else 1
    cpu[34]=0 if hicolor else 2
    ula=bytearray(8);ula[2]=mode if model==14 else 0
    chunks=[(b'Z80R',cpu),(b'SPCR',ula)]
    if model!=14:chunks.append((b'SCLD',bytes([0,mode])))
    for bank in banks:
        memory=bytearray(16384)
        if bank==2:memory[0]=0x76
        if bank==5:memory[:6144]=bytes([0x55])*6144
        if hicolor and bank==2:
            # IM2 with one update to the first bitmap cell after each interrupt.
            program=bytes.fromhex('F3 31 F0 BF 3E 93 ED 47 ED 5E FB 76 3A 00 40 3C 32 00 40 C3 0B 80')
            memory[:len(program)]=program
            memory[0x13ff:0x1401]=b'\xa0\x91'
            memory[0x11a0:0x11a3]=b'\xfb\xed\x4d'
        if hicolor and bank==5:
            memory[0]=0
            memory[8192]=0x47
        chunks.append((b'RAMP',bytes([0,0,bank])+memory))
    (target/name).write_bytes(b'ZXST'+bytes([1,5,model,0])+b''.join(
        tag+struct.pack('<I',len(body))+body for tag,body in chunks))
screen_snapshot('HIRES.SZX',8,6,(5,2,0))
screen_snapshot('HICOLOR.SZX',1,2,(5,2,0))
screen_snapshot('WIDE.SZX',14,64,range(64))
screen_snapshot('COLOR16.SZX',14,1,range(64))
PY
    clang -std=c11 -O2 -Wall -Wextra -Werror "${flags[@]}" \
        -I"$root/sdk/portable/include" -I"$root/code" \
        "$root/tests/spectrum_app_self_test.c" "$root/examples/portable-apps/SPECTRUM/spectrum.c" \
        "$root/examples/portable-apps/SPECTRUM/memory.c" "$root/examples/portable-apps/SPECTRUM/peripherals.c" \
        "$root/examples/portable-apps/SPECTRUM/fdc.c" "$root/examples/portable-apps/SPECTRUM/spi.c" \
        "$root/examples/portable-apps/SPECTRUM/mapper.c" "$root/examples/portable-apps/SPECTRUM/media.c" "${media[@]}" \
        "$root/third_party/z80/z80.c" "$root/third_party/emu2149/emu2149.c" -o "$build/app"
    "$build/app" "$build/app-assets"
    SPECTRUM_LEGACY_LCD=1 "$build/app" "$build/app-assets"
    for selected in DEMO.sna DEMO128.sna OPEN.Z80 ZX0001.SZX BLANK.trd OPEN.SCL GAMES.img; do
        SPECTRUM_OPEN_FILE="$selected" "$build/app" "$build/app-assets"
    done
    SPECTRUM_OPEN_FILE=DEMO128.sna SPECTRUM_SAVE_OPEN_FILE=1 "$build/app" "$build/app-assets"
    for selected in missing unsupported.tap BROKEN.z80; do
        SPECTRUM_OPEN_FILE="$selected" SPECTRUM_OPEN_ERROR=1 "$build/app" "$build/app-assets"
    done
    SPECTRUM_REMOTE_AUDIO=1 "$build/app" "$build/app-assets"
    SPECTRUM_REMOTE_AUDIO=1 SPECTRUM_OPEN_FILE=DEMO128.sna "$build/app" "$build/app-assets"
    for profile in 1 2 3 4; do
        clang -std=c11 -O2 -Wall -Wextra -Werror "${flags[@]}" -DSPECTRUM_APP_PROFILE="$profile" \
            -I"$root/sdk/portable/include" -I"$root/code" \
            "$root/tests/spectrum_app_self_test.c" "$app/spectrum.c" "$app/memory.c" \
            "$app/peripherals.c" "$app/fdc.c" "$app/spi.c" "$app/mapper.c" "$app/media.c" "${media[@]}" \
            "$root/third_party/z80/z80.c" "$root/third_party/emu2149/emu2149.c" -o "$build/app-profile"
        if [[ "$profile" == 1 || "$profile" == 3 ]]; then
            target=SINCLAIR.APP
            if [[ "$profile" == 3 ]]; then target=TIMEX.APP; fi
            SPECTRUM_TEST_FLOW=1 SPECTRUM_FLOW_TARGET="$target" SPECTRUM_FLOW_MODEL=3 \
                SPECTRUM_OPEN_FILE=OPEN128.Z80 "$build/app-profile" "$build/app-assets"
        else
            SPECTRUM_TEST_FLOW=1 SPECTRUM_OPEN_FILE=OPEN128.Z80 "$build/app-profile" "$build/app-assets"
        fi
        if [[ "$profile" == 1 || "$profile" == 2 ]]; then
            for phase in save restore fail bad save foreign save short handoff; do
                SPECTRUM_PREFERENCES_PHASE="$phase" "$build/app-profile" "$build/app-assets"
            done
            SPECTRUM_TEST_FLOW=1 SPECTRUM_FLOW_TARGET=TIMEX.APP SPECTRUM_FLOW_MODEL=0 \
                SPECTRUM_OPEN_FILE=TIMEX.Z80 "$build/app-profile" "$build/app-assets"
        fi
        if [[ "$profile" == 1 ]]; then
            for selected in WIDE.SZX COLOR16.SZX; do
                SPECTRUM_TEST_FLOW=1 SPECTRUM_FLOW_TARGET=ZXVIDEO.APP SPECTRUM_FLOW_MODEL=2 \
                    SPECTRUM_OPEN_FILE="$selected" "$build/app-profile" "$build/app-assets"
            done
        elif [[ "$profile" == 2 ]]; then
            SPECTRUM_TEST_FLOW=1 SPECTRUM_FLOW_TARGET=TIMEX.APP SPECTRUM_FLOW_MODEL=0 \
                SPECTRUM_OPEN_FILE=HICOLOR.SZX "$build/app-profile" "$build/app-assets"
        elif [[ "$profile" == 3 ]]; then
            for selected in WIDE.SZX COLOR16.SZX; do
                SPECTRUM_TEST_FLOW=1 SPECTRUM_OPEN_FILE="$selected" "$build/app-profile" "$build/app-assets"
            done
        else
            for selected in TIMEX.Z80 HIRES.SZX HICOLOR.SZX; do
                SPECTRUM_TEST_FLOW=1 SPECTRUM_OPEN_FILE="$selected" "$build/app-profile" "$build/app-assets"
            done
        fi
    done
fi
clang++ -std=c++17 -O2 -Wall -Wextra -Werror "${flags[@]}" \
    -I"$root/ports/picocalc" -I"$root/code" \
    "$root/tests/picocalc_color_self_test.cpp" -o "$build/color"
"$build/color"

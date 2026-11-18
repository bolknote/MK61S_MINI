#!/usr/bin/env bash
set -euo pipefail
root="$(cd "$(dirname "$0")/.." && pwd)"
work="$(mktemp -d)"
trap 'rm -rf "$work"' EXIT
app="$root/examples/portable-apps/MP3"
mad="$root/third_party/libmad"
flags=()
if [[ "${MK61_TEST_SANITIZERS:-0}" == 1 ]]; then
  flags=(-fsanitize=address,undefined -fno-omit-frame-pointer -fno-sanitize-recover=all)
fi
python3 "$root/tools/apps/mp3/pack_requant.py" "$mad/rq_table.dat" "$work/rq_compact.h"

ffmpeg -nostdin -hide_banner -loglevel error -f lavfi \
  -i 'aevalsrc=0.4*sin(2*PI*440*t)*lt(mod(t\,2)\,1)|0.4*sin(2*PI*660*t)*gte(mod(t\,2)\,1):s=44100:d=4' \
  -c:a libmp3lame -b:a 128k -id3v2_version 3 -metadata title='Ночной сигнал' -metadata artist='Линия 12' "$work/stereo.mp3"
ffmpeg -nostdin -hide_banner -loglevel error -f lavfi -i 'sine=frequency=440:sample_rate=24000:duration=2' \
  -c:a libmp3lame -q:a 5 -id3v2_version 4 -metadata title='Чёрная вода' -metadata artist='Малая волна' "$work/mono.mp3"
for rate in 32000 44100 48000; do
  ffmpeg -nostdin -hide_banner -loglevel error -f lavfi \
    -i "aevalsrc=0.25*sin(2*PI*15000*t)|0.25*sin(2*PI*1000*t):s=$rate:d=2" \
    -c:a libmp3lame -b:a 320k -cutoff 15600 "$work/fold-$rate.mp3"
done

for source in bit fixed frame huffman layer3 stream synth timer; do
  "${CC:-cc}" -std=c11 -O2 -fwrapv -DNDEBUG -DMK61_MAD_APP "${flags[@]}" -I"$work" -c "$mad/$source.c" -o "$work/$source.o"
done
"${CXX:-c++}" -std=c++17 -O2 -Wall -Wextra -Werror "${flags[@]}" \
  -I"$app" -I"$mad" -I"$root/code" "$root/tests/mp3_stereo_self_test.cpp" \
  "$app/metadata.cpp" "$app/audio.cpp" "$work/"*.o -o "$work/test"
"$work/test" "$work/stereo.mp3" "$work/mono.mp3" "$work"/fold-*.mp3
echo 'MP3: ID3v2.3/v2.4, CBR/VBR seek, real stereo channel separation, mono and volume passed.'

"${CXX:-c++}" -std=c++17 -O2 -Wall -Wextra -Werror "${flags[@]}" \
  -I"$app" -I"$mad" -I"$root/code" -I"$root/sdk/portable/include" -I"$root/ports/picocalc" \
  "$root/tests/mp3_tape_self_test.cpp" "$app/metadata.cpp" "$app/audio.cpp" "$app/screen.cpp" \
  "$app/tape.cpp" "$work/"*.o -o "$work/tape-test"
"$work/tape-test" "$app/CASSETTE.TV" "$app/REEL.TV"

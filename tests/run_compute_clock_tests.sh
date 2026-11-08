#!/usr/bin/env bash
set -euo pipefail
root="$(cd "$(dirname "$0")/.." && pwd)"
work="$(mktemp -d "${TMPDIR:-/tmp}/mk61-compute-clock.XXXXXX")"
trap 'rm -rf "$work"' EXIT
clang++ -std=c++17 -O1 -Wall -Wextra -Werror \
  -fsanitize=address,undefined -fno-sanitize-recover=all \
  -DMK61_COMPUTE_CLOCK_TEST -I"$root/code" \
  "$root/tests/compute_clock_self_test.cpp" "$root/code/compute_clock.cpp" -o "$work/policy"
"$work/policy"
"$work/policy" stock
clang++ -std=c++17 -O1 -Wall -Wextra -Werror \
  -fsanitize=address,undefined -fno-sanitize-recover=all -I"$root/code" \
  "$root/tests/setup_settings_model_self_test.cpp" -o "$work/menu"
"$work/menu"
clang -std=c11 -O1 -Wall -Wextra -Werror \
  -fsanitize=address,undefined -fno-sanitize-recover=all \
  -I"$root/code" -I"$root/sdk/portable/include" \
  "$root/tests/compute_clock_sdk_self_test.c" -o "$work/sdk"
"$work/sdk"
cat > "$work/Arduino.h" <<'HEADER'
#include <stdint.h>
uint32_t micros();
HEADER
clang++ -std=c++17 -O1 -Wall -Wextra -Werror \
  -fsanitize=address,undefined -fno-sanitize-recover=all \
  -I"$work" -I"$root/tests" \
  "$root/tests/compute_gap_probe_self_test.cpp" \
  "$root/tests/experimental/compute_gap_probe.cpp" -o "$work/gaps"
"$work/gaps"
python3 - "$root" "$work" <<'PY'
import sys
from pathlib import Path
root,out=map(Path,sys.argv[1:])
sys.path.insert(0,str(root/'tests'))
from ui_contract_surface import body
(out/'setup_settings_state.inc').write_text(''.join(body(root/'code/menu.cpp',marker)
    for marker in ('void set_program_memory_mode(', 'void read_settings_snapshot(', 'bool apply_setting(')))
(out/'compute_clock_label.inc').write_text(body(root/'code/setup_settings_ui.cpp','void label('))
(out/'compute_clock_storage.inc').write_text(''.join(body(root/'code/tools.hpp',marker,marker.startswith('struct'))
    for marker in ('struct SettingsFlags {', 'namespace speed_mode_storage {', 'struct SoundSettings {',
                   'inline u8 stored_compute_clock_profile(', 'inline void set_stored_compute_clock_profile(',
                   'inline SettingsFlags normalize_settings_flags(', 'inline SoundSettings normalize_sound_settings(')))

PY
for profile in lcd oled disabled; do
  flags=(-DMK61_ENABLE_SETUP=1)
  if [[ "$profile" == oled ]]; then flags+=(-DMK61_OLED1602_WS0010=1); fi
  if [[ "$profile" == disabled ]]; then flags=(-DMK61_ENABLE_SETUP=0); fi
  clang++ -std=c++17 -O1 -Wall -Wextra -Werror \
    -fsanitize=address,undefined -fno-sanitize-recover=all \
    -DMK61_HAS_GRAPHICAL_TEXT_SETTINGS=1 -DMK61_COMPUTE_CLOCK_SUPPORTED=1 \
    "${flags[@]}" -I"$root/code" -I"$work" \
    "$root/tests/setup_settings_state_self_test.cpp" -o "$work/state"
  "$work/state"
done

clang++ -std=c++17 -O1 -Wall -Wextra -Werror \
  -fsanitize=address,undefined -fno-sanitize-recover=all -I"$work" \
  "$root/tests/compute_clock_storage_self_test.cpp" -o "$work/storage"
"$work/storage"

clang++ -std=c++17 -O1 -Wall -Wextra -Werror \
  -fsanitize=address,undefined -fno-sanitize-recover=all -I"$root/code" -I"$work" \
  "$root/tests/compute_clock_label_self_test.cpp" -o "$work/label"
"$work/label"

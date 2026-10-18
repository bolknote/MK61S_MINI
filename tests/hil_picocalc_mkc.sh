#!/usr/bin/env bash
# Qualify the real MKC shell transport on one Pico H. Creates/removes only its
# own new SD directory, using the normal discovery, M8 codec and CRC protocol.
set -euo pipefail
root=$(cd "$(dirname "$0")/.." && pwd)
[ "$#" -ge 3 ] && [ "$#" -le 4 ] || { echo 'usage: hil_picocalc_mkc.sh PORT UID OUTPUT [FIRMWARE_DIRECTORY]' >&2;exit 2; }
test_port=$1 test_uid=$2 test_output=$3 test_firmware=${4:-"$root/binary/picocalc-pico-h"}
[[ "$test_uid" =~ ^[0-9A-F]{16}$ ]] || exit 2
mkdir -p "$test_output"
test_output=$(cd "$test_output" && pwd)
MKC_SOURCE_ONLY=1 MKC_CONFIG_FILE=/dev/null source "$root/tools/.mkc/mkc.sh"
SESSION_DIR=$(mktemp -d "$test_output/session.XXXXXX")
PORT=$test_port;PORT_EXPLICIT=1;DEVICE_SELECTOR=$test_uid;DEVICE_SELECTOR_EXPLICIT=1
remote="/MK61S-MKC-$(date +%Y%m%d-%H%M%S)";created=0
finish() {
  local status=$? original_error=${STATUS_TEXT:-}
  if [ "$created" = 1 ]; then remote_simple_real "rm -r \"$remote\"" || status=1;fi
  if [ -n "$MONITOR_PID" ]; then kill "$MONITOR_PID" 2>/dev/null || true;wait "$MONITOR_PID" 2>/dev/null || true;fi
  if [ "$status" != 0 ]; then echo "MKC HIL: ${original_error:-${STATUS_TEXT:-failed}}" >&2;fi
  exit "$status"
}
trap finish EXIT
list_cdc_ports > "$test_output/discovered-ports.txt"
grep -Fx "$test_port" "$test_output/discovered-ports.txt"
select_mk61_port || { echo "$SELECT_ERROR" >&2;exit 1; }
test "$DETECTED_DEVICE_ID:$DETECTED_PROFILE" = "$test_uid:picocalc-pico-h"
start_monitor
remote_mkdir "$remote";created=1
python3 - "$SESSION_DIR" <<'PY'
from pathlib import Path
import sys
directory=Path(sys.argv[1])
(directory/'source.txt').write_bytes('Привет, ёж!\r\nВторая строка\r\n'.encode('utf-8'))
(directory/'maximum.txt').write_text('Ж'*65534,encoding='utf-8')
(directory/'binary.wbmp').write_bytes(bytes(range(256)))
PY
for name in source.txt maximum.txt binary.wbmp;do
  echo "MKC upload $name"
  remote_put_file "$SESSION_DIR/$name" "$remote/$name"
  echo "MKC download $name"
  remote_get_file "$remote/$name" "$SESSION_DIR/read-$name"
  cmp "$SESSION_DIR/$name" "$SESSION_DIR/read-$name"
  echo "PASS MKC copy/readback $name"
done
remote_list_raw "$remote" "$test_output/listing.txt"
grep -F $'f\t131068\tmaximum.txt' "$test_output/listing.txt"
remote_simple_real "mv \"$remote/source.txt\" \"$remote/русский.txt\""
remote_get_file "$remote/русский.txt" "$SESSION_DIR/russian.txt"
cmp "$SESSION_DIR/source.txt" "$SESSION_DIR/russian.txt"
remote_simple_real "rm -r \"$remote\"";created=0
python3 - "$test_output" "$test_uid" "$test_firmware" <<'PY'
import json,sys
from pathlib import Path
from datetime import datetime,timezone
out=Path(sys.argv[1]);build=json.loads((Path(sys.argv[3])/'manifest.json').read_text())
report={'passed':True,'uid':sys.argv[2],'recorded_at_utc':datetime.now(timezone.utc).isoformat(),
 'uf2_sha256':build['uf2_sha256'],'temporary_directory_removed':True,
 'cases':['real Arduino CDC auto-discovery, exact Pico H UID and MKC handshake',
          'M8 text upload/download with CRC and UTF-8 storage: Russian, ё and 65534-character source',
          'binary byte-for-byte transfer, complete directory listing, Cyrillic rename and removal']}
(out/'result.json').write_text(json.dumps(report,ensure_ascii=False,indent=2)+'\n')
PY
echo 'ALL PicoCalc MKC HIL PASS'

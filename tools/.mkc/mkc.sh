#!/usr/bin/env bash

# MKC — двухпанельный файловый менеджер MK61s в стиле Norton Commander.
# Bash 3.2 compatible: системный Bash старых macOS тоже поддерживается.

set -u

ensure_utf8_locale() {
  local charmap candidate
  charmap=$(locale charmap 2>/dev/null || true)
  case "$charmap" in UTF-8|UTF8|utf8) return 0 ;; esac
  for candidate in C.UTF-8 en_US.UTF-8 UTF-8; do
    charmap=$(LC_CTYPE=$candidate locale charmap 2>/dev/null || true)
    case "$charmap" in
      UTF-8|UTF8|utf8)
        LC_CTYPE=$candidate
        export LC_CTYPE
        return 0
        ;;
    esac
  done
}
ensure_utf8_locale

SCRIPT_DIR=$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)
PROJECT_ROOT=$(cd "$SCRIPT_DIR/../.." && pwd)
ARDUINO_CLI=${MKC_ARDUINO_CLI:-${MK61_ARDUINO_CLI:-arduino-cli}}
CONFIG_FILE=${MKC_CONFIG_FILE:-"$PROJECT_ROOT/.mkc.conf"}

PORT=
LOCAL_PATH=$(pwd -P)
REMOTE_PATH=/
MOCK_ROOT=
CLASSIFY_ONLY=
SESSION_DIR=
MONITOR_PID=
MONITOR_INPUT_FD=
MONITOR_OUTPUT_FD=
TTY_FD=
TTY_SAVED=
SCREEN_ACTIVE=0
RESIZE_PENDING=0

ACTIVE_PANEL=L
L_SELECTED=0
R_SELECTED=0
L_PAGE=0
R_PAGE=0
STATUS_TEXT=
COMMAND_TEXT=
COMMAND_CURSOR=0
COMMAND_HISTORY_INDEX=-1
COMMAND_HISTORY_DRAFT=
LAST_REMOTE_OUTPUT=
LAST_REMOTE_TITLE='Терминал MK61s'
REMOTE_CAPTURE_PATH=/

L_NAMES=()
L_KINDS=()
L_SIZES=()
L_REASONS=()
L_MARKS=()
R_NAMES=()
R_KINDS=()
R_SIZES=()
R_REASONS=()
R_MARKS=()

PLAN_KINDS=()
PLAN_SOURCES=()
PLAN_DESTINATIONS=()
PLAN_SIZES=()
PLAN_TOTAL=0
PLAN_ERROR=
PLAN_SERIAL=0
SELECTED_INDICES=()
COMMAND_HISTORY=()
WBMP_BYTES=()
WBMP_WIDTH=0
WBMP_HEIGHT=0
WBMP_OFFSET=0
WBMP_ROW_BYTES=0
WBMP_ERROR=
WBMP_MB_VALUE=0
WBMP_PIXEL_DARK=0

TERM_COLS=80
TERM_LINES=24
UI_X=1
UI_Y=1
UI_WIDTH=80
UI_HEIGHT=24
HEADER_ROW=2
PANEL_SEPARATOR=19
PANEL_INFO_ROW=20
COMMAND_ROW=23
STATUS_ROW=23
FUNCTION_ROW=24
PANEL_BOTTOM=22
LIST_TOP=3
LIST_BOTTOM=18
LIST_ROWS=16
LEFT_WIDTH=40
RIGHT_X=41
RIGHT_WIDTH=40

C_RESET=$'\033[0m'
C_OUTSIDE=$'\033[0m'
# Фиксированная 16-цветная палитра DOS/VGA, не зависящая от темы терминала.
# Фон Norton Commander — VGA blue #0000AA; снаружи окна фон не закрашивается.
C_PANEL=$'\033[38;2;192;192;192;48;2;0;0;170m'
C_BORDER=$'\033[1;38;2;85;255;255;48;2;0;0;170m'
C_BORDER_INACTIVE=$'\033[38;2;0;170;170;48;2;0;0;170m'
C_TITLE=$'\033[1;38;2;255;255;255;48;2;0;0;170m'
C_FILE=$'\033[1;38;2;85;255;255;48;2;0;0;170m'
C_DIR=$'\033[1;38;2;85;255;255;48;2;0;0;170m'
C_MARKED=$'\033[1;38;2;255;255;85;48;2;0;0;170m'
C_DISABLED=$'\033[38;2;128;128;128;48;2;0;0;170m'
C_SELECTED=$'\033[38;2;0;0;0;48;2;0;170;170m'
C_SELECTED_DISABLED=$'\033[38;2;0;0;0;48;2;160;160;160m'
C_MENU=$'\033[38;2;0;0;0;48;2;0;170;170m'
C_STATUS=$'\033[1;38;2;255;255;85;48;2;0;0;170m'
C_ERROR=$'\033[1;38;2;255;85;85;48;2;0;0;170m'
C_COMMAND=$'\033[38;2;192;192;192;48;2;0;0;0m'
C_COMMAND_ERROR=$'\033[1;38;2;255;85;85;48;2;0;0;0m'
C_FUNCTION_NUMBER=$'\033[38;2;192;192;192;48;2;0;0;0m'
C_FUNCTION_LABEL=$'\033[38;2;0;0;0;48;2;0;170;170m'
C_DIALOG=$'\033[38;2;0;0;0;48;2;170;170;170m'
C_DIALOG_BORDER=$'\033[1;38;2;255;255;255;48;2;170;170;170m'
C_DIALOG_TITLE=$'\033[38;2;85;85;85;48;2;255;255;255m'
C_DIALOG_INPUT=$'\033[38;2;0;0;0;48;2;255;255;255m'
C_DIALOG_BUTTON=$'\033[38;2;0;0;0;48;2;255;255;255m'
C_DIALOG_BUTTON_ACTIVE=$'\033[38;2;0;0;0;48;2;255;255;85m'
C_SHADOW=$'\033[38;2;0;0;0;48;2;0;0;0m'

DIALOG_X=1
DIALOG_Y=1
DIALOG_WIDTH=60
DIALOG_HEIGHT=9
PROGRESS_ACTIVE=0

# Входная строка прошивки вмещает блок из 96 байт, но STM32 CDC вместе с
# arduino-cli monitor может потерять хвост одного рывка длиной около 128 байт.
# 48 байт дают команду не длиннее 113 байт даже с четырёхзначным смещением.
FS_PUT_CHUNK_BYTES=48

usage() {
  cat <<'EOF'
MKC — Norton Commander для файлов MK61s

Usage:
  tools/mkc.cmd [--port PORT] [--local DIRECTORY]
  tools/mkc.cmd --mock DIRECTORY [--local DIRECTORY]
  tools/mkc.cmd --classify FILE

Keys:
  Tab       switch panel        Enter     open directory
  Space     mark item           F1        help
  F3        view                F5        copy
  F6        rename/move         F7        mkdir
  F8        delete              F9        device info
  F10       quit                Ctrl-R    refresh
  Ctrl-O    last MK61s output

Type a command and press Enter: the left panel runs it locally, while the
right panel sends it to the MK61s terminal and captures its output.

Supported device files: .m61, .foc, .tbi, .txt, .state.txt, .fmk, .wbmp
Loadable modules in the device root: FOCAL.MOD, BASIC.MOD, WBMP.MOD
Legacy aliases accepted on upload: .t1, .m2, .wbm
EOF
}

die() {
  printf 'mkc: %s\n' "$*" >&2
  exit 1
}

repeat_char() {
  local char=$1 count=$2 result=
  while [ "$count" -gt 0 ]; do
    result=$result$char
    count=$((count - 1))
  done
  printf '%s' "$result"
}

byte_length() {
  LC_ALL=C printf '%s' "$1" | wc -c | tr -d '[:space:]'
}

lowercase() {
  LC_ALL=C printf '%s' "$1" | tr '[:upper:]' '[:lower:]'
}

uppercase() {
  LC_ALL=C printf '%s' "$1" | tr '[:lower:]' '[:upper:]'
}

# Печатает причину несовместимости; пустой вывод означает, что объект можно
# копировать на калькулятор. Второй аргумент: f, d либо l.
unsupported_reason() {
  local path=$1 kind=$2 name base lower upper bytes size limit minimum=0
  name=${path##*/}

  if [ "$kind" = l ]; then
    printf '%s' 'символическая ссылка'
    return
  fi
  case "$name" in
    ''|.|..) printf '%s' 'недопустимое имя'; return ;;
    *$'\n'*|*$'\r'*|*$'\t'*) printf '%s' 'управляющий символ в имени'; return ;;
    *'<'*|*'>'*|*':'*|*'"'*|*'/'*|*'\'*|*'|'*|*'?'*|*'*'*)
      printf '%s' 'недопустимый символ в имени'; return ;;
    *' '|*.) printf '%s' 'имя оканчивается пробелом или точкой'; return ;;
  esac

  base=$name
  limit=1536
  if [ "$kind" = f ]; then
    lower=$(lowercase "$name")
    case "$lower" in
      focal.mod|basic.mod)
        base=${name:0:$(( ${#name} - 4 ))}
        limit=16384
        minimum=64
        ;;
      wbmp.mod)
        base=${name:0:$(( ${#name} - 4 ))}
        limit=4096
        minimum=64
        ;;
      *.mod) printf '%s' 'допустимы только FOCAL.MOD, BASIC.MOD и WBMP.MOD'; return ;;
      *.state.txt) base=${name:0:$(( ${#name} - 10 ))} ;;
      *.m61|*.foc|*.tbi|*.txt|*.fmk)
        base=${name:0:$(( ${#name} - 4 ))}
        ;;
      *.wbmp)
        base=${name:0:$(( ${#name} - 5 ))}
        limit=1600
        ;;
      *.t1|*.m2)
        base=${name:0:$(( ${#name} - 3 ))}
        ;;
      *.wbm)
        base=${name:0:$(( ${#name} - 4 ))}
        limit=1600
        ;;
      *) printf '%s' 'формат не поддерживается'; return ;;
    esac
  elif [ "$kind" != d ]; then
    printf '%s' 'не обычный файл или каталог'
    return
  fi

  bytes=$(byte_length "$base")
  case "$bytes" in ''|*[!0-9]*) printf '%s' 'не удалось проверить имя'; return ;; esac
  if [ "$bytes" -lt 1 ] || [ "$bytes" -gt 31 ]; then
    printf '%s' 'basename должен занимать 1–31 байт UTF-8'
    return
  fi
  upper=$(uppercase "$base")
  case "$upper" in
    CON|PRN|AUX|NUL|COM[1-9]|LPT[1-9])
      printf '%s' 'зарезервированное имя DOS'; return ;;
  esac

  if [ "$kind" = f ]; then
    size=$(wc -c < "$path" 2>/dev/null | tr -d '[:space:]') || size=
    case "$size" in ''|*[!0-9]*) printf '%s' 'не удалось прочитать размер'; return ;; esac
    if [ "$size" -lt "$minimum" ]; then
      printf '%s' "слишком маленький: $size байт, минимум $minimum"
      return
    fi
    if [ "$size" -gt "$limit" ]; then
      printf '%s' "слишком большой: $size байт, максимум $limit"
      return
    fi
  fi
}

cleanup() {
  local status=$?
  trap - EXIT INT TERM HUP
  if [ -n "$MONITOR_PID" ] && kill -0 "$MONITOR_PID" 2>/dev/null; then
    kill "$MONITOR_PID" 2>/dev/null || true
    wait "$MONITOR_PID" 2>/dev/null || true
  fi
  [ -n "$MONITOR_INPUT_FD" ] && eval "exec ${MONITOR_INPUT_FD}>&-" 2>/dev/null || true
  [ -n "$MONITOR_OUTPUT_FD" ] && eval "exec ${MONITOR_OUTPUT_FD}>&-" 2>/dev/null || true
  if [ -n "$TTY_SAVED" ] && [ -n "$TTY_FD" ]; then
    eval "stty '$TTY_SAVED' <&${TTY_FD}" 2>/dev/null || true
  fi
  if [ "$SCREEN_ACTIVE" -eq 1 ] && [ -n "$TTY_FD" ]; then
    eval "printf '\\033[0m\\033[?25h\\033[?1049l' >&${TTY_FD}" 2>/dev/null || true
  fi
  [ -n "$TTY_FD" ] && eval "exec ${TTY_FD}>&-" 2>/dev/null || true
  if [ -n "$SESSION_DIR" ] && [ -d "$SESSION_DIR" ]; then
    rm -rf "$SESSION_DIR"
  fi
  exit "$status"
}
if [ "${MKC_SOURCE_ONLY:-0}" != 1 ]; then
  trap cleanup EXIT
  trap 'exit 130' INT
  trap 'exit 143' TERM HUP
  trap 'RESIZE_PENDING=1' WINCH
fi

load_config() {
  local key value saved_local= saved_port=
  [ -r "$CONFIG_FILE" ] || return 0
  while IFS='=' read -r key value || [ -n "${key:-}${value:-}" ]; do
    value=${value%$'\r'}
    case "$key" in
      LOCAL_PATH) saved_local=$value ;;
      PORT) saved_port=$value ;;
    esac
  done < "$CONFIG_FILE"
  if [ -z "$PORT" ] && [ -n "$saved_port" ]; then PORT=$saved_port; fi
  if [ "$LOCAL_PATH" = "$(pwd -P)" ] && [ -d "$saved_local" ]; then
    LOCAL_PATH=$(cd "$saved_local" && pwd -P)
  fi
}

save_config() {
  local temporary="$CONFIG_FILE.tmp"
  [ "$CONFIG_FILE" != /dev/null ] || return 0
  {
    printf '# Создано tools/mkc.cmd.\n'
    printf 'LOCAL_PATH=%s\n' "$LOCAL_PATH"
    printf 'PORT=%s\n' "$PORT"
  } > "$temporary" 2>/dev/null && mv "$temporary" "$CONFIG_FILE" 2>/dev/null
}

list_cdc_ports() {
  local json
  json=$("$ARDUINO_CLI" board list --format json 2>/dev/null) || return 0
  if command -v jq >/dev/null 2>&1; then
    printf '%s\n' "$json" | jq -r '
      .detected_ports[]?.port |
      select(((.properties.vid // "") | ascii_downcase | sub("^0x"; "")) == "0483") |
      select(((.properties.pid // "") | ascii_downcase | sub("^0x"; "")) == "5740") |
      .address' 2>/dev/null
    return
  fi
  printf '%s\n' "$json" | awk '
    function emit() {
      gsub(/^0[xX]/, "", vid); gsub(/^0[xX]/, "", pid)
      if(address != "" && tolower(vid) == "0483" && tolower(pid) == "5740") print address
    }
    /"address"[[:space:]]*:/ {
      emit(); address=$0; vid=""; pid=""
      sub(/^.*"address"[[:space:]]*:[[:space:]]*"/, "", address); sub(/".*$/, "", address)
    }
    /"vid"[[:space:]]*:/ {
      vid=$0; sub(/^.*"vid"[[:space:]]*:[[:space:]]*"/, "", vid); sub(/".*$/, "", vid)
    }
    /"pid"[[:space:]]*:/ {
      pid=$0; sub(/^.*"pid"[[:space:]]*:[[:space:]]*"/, "", pid); sub(/".*$/, "", pid)
    }
    END { emit() }
  '
}

detect_port() {
  local found
  while IFS= read -r found; do
    [ -n "$found" ] || continue
    PORT=$found
    return 0
  done < <(list_cdc_ports)
  return 1
}

start_monitor() {
  [ -n "$MOCK_ROOT" ] && return 0
  command -v "$ARDUINO_CLI" >/dev/null 2>&1 ||
    die "arduino-cli не найден (задайте MKC_ARDUINO_CLI)"
  [ -n "$PORT" ] || detect_port || return 1

  mkfifo "$SESSION_DIR/monitor.in" "$SESSION_DIR/monitor.out" || return 1
  exec 7<>"$SESSION_DIR/monitor.in" || return 1
  exec 8<>"$SESSION_DIR/monitor.out" || return 1
  MONITOR_INPUT_FD=7
  MONITOR_OUTPUT_FD=8
  "$ARDUINO_CLI" monitor --quiet --port "$PORT" --config baudrate=115200 \
    <&7 >&8 2>"$SESSION_DIR/monitor.log" &
  MONITOR_PID=$!
  sleep 0.25
  kill -0 "$MONITOR_PID" 2>/dev/null || return 1
  return 0
}

remote_send() {
  [ -n "$MONITOR_INPUT_FD" ] || return 1
  printf '%s\r' "$1" >&7
}

serial_read_line() {
  local timeout=${1:-5}
  SERIAL_LINE=
  IFS= read -r -t "$timeout" SERIAL_LINE <&8 || return 1
  SERIAL_LINE=${SERIAL_LINE%$'\r'}
  return 0
}

wait_for_marker() {
  local wanted=$1 attempts=0
  MARKER_LINE=
  while [ "$attempts" -lt 200 ]; do
    if ! serial_read_line 5; then
      STATUS_TEXT='Таймаут ответа калькулятора'
      return 1
    fi
    case "$SERIAL_LINE" in
      @MKC:ERROR*) STATUS_TEXT="Калькулятор: ${SERIAL_LINE#@MKC:ERROR }"; return 1 ;;
      Unknown\ command:\ fsget*|Unknown\ command:\ fsput*)
        STATUS_TEXT='Установленная прошивка не поддерживает F3/F5; загрузите свежую сборку'
        return 1
        ;;
      "$wanted"*) MARKER_LINE=$SERIAL_LINE; return 0 ;;
    esac
    attempts=$((attempts + 1))
  done
  STATUS_TEXT='Слишком длинный ответ калькулятора'
  return 1
}

remote_join() {
  local parent=$1 name=$2
  if [ "$parent" = / ]; then printf '/%s' "$name"; else printf '%s/%s' "${parent%/}" "$name"; fi
}

remote_parent() {
  local path=${1%/}
  [ "$path" = / ] && { printf '/'; return; }
  path=${path%/*}
  [ -n "$path" ] || path=/
  printf '%s' "$path"
}

remote_normalize() {
  local base=$1 input=$2 combined component i
  local parts=() output=()
  case "$input" in /*) combined=$input ;; *) combined=$(remote_join "$base" "$input") ;; esac
  IFS='/' read -r -a parts <<< "$combined"
  i=0
  while [ "$i" -lt "${#parts[@]}" ]; do
    component=${parts[$i]}
    case "$component" in
      ''|.) ;;
      ..) [ "${#output[@]}" -gt 0 ] && unset "output[$(( ${#output[@]} - 1 ))]" ;;
      *) output[${#output[@]}]=$component ;;
    esac
    i=$((i + 1))
  done
  if [ "${#output[@]}" -eq 0 ]; then
    printf '/'
    return
  fi
  combined=
  i=0
  while [ "$i" -lt "${#output[@]}" ]; do
    combined=$combined/${output[$i]}
    i=$((i + 1))
  done
  printf '%s' "$combined"
}

mock_path() {
  local normalized
  normalized=$(remote_normalize / "$1")
  printf '%s%s' "$MOCK_ROOT" "$normalized"
}

# Пишет каталог в машинном формате: kind<TAB>size<TAB>name.
remote_list_raw() {
  local path=$1 output=$2 line rest kind size name count=0 entry physical
  : > "$output" || return 1
  if [ -n "$MOCK_ROOT" ]; then
    physical=$(mock_path "$path")
    [ -d "$physical" ] || { STATUS_TEXT="Нет каталога $path"; return 1; }
    local entries=()
    entries=("$physical"/*)
    for entry in "${entries[@]}"; do
      [ -e "$entry" ] || [ -L "$entry" ] || continue
      name=${entry##*/}
      if [ -d "$entry" ] && [ ! -L "$entry" ]; then
        printf 'd\t0\t%s\n' "$name" >> "$output"
      elif [ -f "$entry" ] && [ ! -L "$entry" ]; then
        size=$(wc -c < "$entry" | tr -d '[:space:]')
        printf 'f\t%s\t%s\n' "$size" "$name" >> "$output"
      fi
    done
    return 0
  fi

  remote_send "ls \"$path\"" || return 1
  while [ "$count" -lt 10000 ]; do
    serial_read_line 8 || { STATUS_TEXT="Нет ответа на ls $path"; return 1; }
    line=$SERIAL_LINE
    case "$line" in
      $'d\t'*)
        name=${line#$'d\t'}
        name=${name%/}
        printf 'd\t0\t%s\n' "$name" >> "$output"
        ;;
      $'f\t'*)
        rest=${line#$'f\t'}
        size=${rest%% B$'\t'*}
        name=${rest#* B$'\t'}
        case "$size" in ''|*[!0-9]*) ;; *) printf 'f\t%s\t%s\n' "$size" "$name" >> "$output" ;; esac
        ;;
      *' entry.'|*' entries.') return 0 ;;
      ls:\ *|Unknown\ command:*) STATUS_TEXT=$line; return 1 ;;
    esac
    count=$((count + 1))
  done
  STATUS_TEXT='Каталог устройства слишком велик'
  return 1
}

remote_simple_real() {
  local command=$1 line failed=0 count=0
  remote_send "$command" || return 1
  remote_send 'ls "/"' || return 1
  while [ "$count" -lt 10000 ]; do
    serial_read_line 12 || { STATUS_TEXT='Нет ответа калькулятора'; return 1; }
    line=$SERIAL_LINE
    case "$line" in
      *' entry.'|*' entries.') [ "$failed" -eq 0 ]; return ;;
      mkdir:\ *|mv:\ *|rm:\ *|rmdir:\ *|Unknown\ command:*) STATUS_TEXT=$line; failed=1 ;;
    esac
    count=$((count + 1))
  done
  STATUS_TEXT='Операция не завершилась'
  return 1
}

remote_mkdir() {
  local path=$1 physical
  if [ -n "$MOCK_ROOT" ]; then
    physical=$(mock_path "$path")
    mkdir -p "$physical" 2>/dev/null || { STATUS_TEXT="Не удалось создать $path"; return 1; }
    return 0
  fi
  remote_simple_real "mkdir -p \"$path\""
}

remote_move() {
  local source=$1 destination=$2 src dst
  if [ -n "$MOCK_ROOT" ]; then
    src=$(mock_path "$source"); dst=$(mock_path "$destination")
    mv "$src" "$dst" 2>/dev/null || { STATUS_TEXT='Переименование не удалось'; return 1; }
    return 0
  fi
  remote_simple_real "mv \"$source\" \"$destination\""
}

remote_delete() {
  local path=$1 physical
  if [ -n "$MOCK_ROOT" ]; then
    physical=$(mock_path "$path")
    [ "$physical" != "$MOCK_ROOT/" ] || return 1
    rm -rf "$physical" 2>/dev/null || { STATUS_TEXT='Удаление не удалось'; return 1; }
    return 0
  fi
  remote_simple_real "rm -r \"$path\""
}

file_checksum() {
  cksum "$1" | awk '{print $1}'
}

file_to_hex() {
  od -An -v -tx1 "$1" | tr -d '[:space:]' | tr '[:lower:]' '[:upper:]'
}

hex_file_to_binary() {
  local source=$1 destination=$2 line chunk pair escapes index
  : > "$destination" || return 1
  while IFS= read -r line || [ -n "$line" ]; do
    chunk=$line
    escapes=
    index=0
    while [ "$index" -lt "${#chunk}" ]; do
      pair=${chunk:$index:2}
      [ "${#pair}" -eq 2 ] || return 1
      escapes=$escapes\\x$pair
      index=$((index + 2))
    done
    printf '%b' "$escapes" >> "$destination" || return 1
  done < "$source"
}

remote_put_file() {
  local source=$1 destination=$2 size crc hex offset=0 chunk expected
  if [ -n "$MOCK_ROOT" ]; then
    cp "$source" "$(mock_path "$destination")" 2>/dev/null || {
      STATUS_TEXT="Не удалось записать $destination"; return 1;
    }
    return 0
  fi
  size=$(wc -c < "$source" | tr -d '[:space:]')
  crc=$(file_checksum "$source") || return 1
  remote_send "fsput begin \"$destination\" $size $crc" || return 1
  wait_for_marker '@MKC:READY ' || return 1
  expected=${MARKER_LINE#@MKC:READY }
  [ "$expected" = "$size" ] || { STATUS_TEXT='Неверный ответ fsput begin'; return 1; }
  hex=$(file_to_hex "$source") || return 1
  while [ "$offset" -lt "$size" ]; do
    chunk=${hex:$((offset * 2)):$((FS_PUT_CHUNK_BYTES * 2))}
    remote_send "fsput data $offset $chunk" || return 1
    wait_for_marker '@MKC:ACK ' || return 1
    offset=$((offset + ${#chunk} / 2))
    expected=${MARKER_LINE#@MKC:ACK }
    [ "$expected" = "$offset" ] || { STATUS_TEXT='Неверное смещение ACK'; return 1; }
  done
  remote_send 'fsput end' || return 1
  wait_for_marker '@MKC:DONE ' || return 1
  case "$MARKER_LINE" in "@MKC:DONE $size $crc") return 0 ;; esac
  STATUS_TEXT='Контрольная сумма загрузки не совпала'
  return 1
}

remote_get_file() {
  local source=$1 destination=$2 header_size header_crc line rest offset hex
  local received=0 end_size end_crc actual_size actual_crc
  if [ -n "$MOCK_ROOT" ]; then
    cp "$(mock_path "$source")" "$destination" 2>/dev/null || {
      STATUS_TEXT="Не удалось прочитать $source"; return 1;
    }
    return 0
  fi
  : > "$SESSION_DIR/download.hex"
  remote_send "fsget \"$source\"" || return 1
  wait_for_marker '@MKC:GET ' || return 1
  rest=${MARKER_LINE#@MKC:GET }
  header_size=${rest%% *}
  header_crc=${rest#* }
  case "$header_size:$header_crc" in *[!0-9:]*|:*) STATUS_TEXT='Повреждён заголовок fsget'; return 1 ;; esac
  while true; do
    serial_read_line 8 || { STATUS_TEXT='Таймаут fsget'; return 1; }
    line=$SERIAL_LINE
    case "$line" in
      @MKC:DATA\ *)
        rest=${line#@MKC:DATA }
        offset=${rest%% *}
        hex=${rest#* }
        [ "$offset" = "$received" ] || { STATUS_TEXT='Нарушен порядок блоков fsget'; return 1; }
        case "$hex" in *[!0-9A-Fa-f]*|'') STATUS_TEXT='Повреждён HEX-блок fsget'; return 1 ;; esac
        [ $(( ${#hex} % 2 )) -eq 0 ] || { STATUS_TEXT='Нечётный HEX-блок fsget'; return 1; }
        printf '%s\n' "$hex" >> "$SESSION_DIR/download.hex"
        received=$((received + ${#hex} / 2))
        ;;
      @MKC:END\ *)
        rest=${line#@MKC:END }
        end_size=${rest%% *}
        end_crc=${rest#* }
        break
        ;;
      @MKC:ERROR*) STATUS_TEXT="Калькулятор: ${line#@MKC:ERROR }"; return 1 ;;
    esac
  done
  [ "$received" = "$header_size" ] && [ "$end_size" = "$header_size" ] &&
    [ "$end_crc" = "$header_crc" ] || { STATUS_TEXT='Размер fsget не совпал'; return 1; }
  hex_file_to_binary "$SESSION_DIR/download.hex" "$SESSION_DIR/download.bin" || {
    STATUS_TEXT='Не удалось декодировать fsget'; return 1;
  }
  actual_size=$(wc -c < "$SESSION_DIR/download.bin" | tr -d '[:space:]')
  actual_crc=$(file_checksum "$SESSION_DIR/download.bin") || return 1
  [ "$actual_size" = "$header_size" ] && [ "$actual_crc" = "$header_crc" ] || {
    STATUS_TEXT='Ошибка контрольной суммы fsget'; return 1;
  }
  cp "$SESSION_DIR/download.bin" "$destination" || return 1
}

add_local_entry() {
  local name=$1 kind=$2 size=$3 reason=$4 index=${#L_NAMES[@]}
  L_NAMES[$index]=$name
  L_KINDS[$index]=$kind
  L_SIZES[$index]=$size
  L_REASONS[$index]=$reason
  L_MARKS[$index]=0
}

add_remote_entry() {
  local name=$1 kind=$2 size=$3 reason=$4 index=${#R_NAMES[@]}
  R_NAMES[$index]=$name
  R_KINDS[$index]=$kind
  R_SIZES[$index]=$size
  R_REASONS[$index]=$reason
  R_MARKS[$index]=0
}

load_local_panel() {
  local old_name= entry name kind size reason pass i found=-1
  if [ "${#L_NAMES[@]}" -gt 0 ] && [ "$L_SELECTED" -lt "${#L_NAMES[@]}" ]; then
    old_name=${L_NAMES[$L_SELECTED]}
  fi
  L_NAMES=(); L_KINDS=(); L_SIZES=(); L_REASONS=(); L_MARKS=()
  [ "$LOCAL_PATH" = / ] || add_local_entry '..' d 0 ''
  local entries=("$LOCAL_PATH"/*)
  for pass in d f; do
    for entry in "${entries[@]}"; do
      [ -e "$entry" ] || [ -L "$entry" ] || continue
      name=${entry##*/}
      if [ -L "$entry" ]; then kind=l
      elif [ -d "$entry" ]; then kind=d
      elif [ -f "$entry" ]; then kind=f
      else kind=o
      fi
      if [ "$pass" = d ]; then
        [ "$kind" = d ] || continue
      else
        [ "$kind" != d ] || continue
      fi
      size=0
      [ "$kind" = f ] && size=$(wc -c < "$entry" 2>/dev/null | tr -d '[:space:]')
      reason=$(unsupported_reason "$entry" "$kind")
      add_local_entry "$name" "$kind" "${size:-0}" "$reason"
    done
  done
  if [ "${#L_NAMES[@]}" -eq 0 ]; then add_local_entry '..' d 0 ''; fi
  if [ -n "$old_name" ]; then
    i=0
    while [ "$i" -lt "${#L_NAMES[@]}" ]; do
      [ "${L_NAMES[$i]}" = "$old_name" ] && { found=$i; break; }
      i=$((i + 1))
    done
  fi
  if [ "$found" -ge 0 ]; then L_SELECTED=$found; fi
  [ "$L_SELECTED" -lt "${#L_NAMES[@]}" ] || L_SELECTED=$((${#L_NAMES[@]} - 1))
  [ "$L_SELECTED" -ge 0 ] || L_SELECTED=0
}

load_remote_panel() {
  local old_name= raw="$SESSION_DIR/remote-panel.list" kind size name reason i found=-1 pass
  if [ "${#R_NAMES[@]}" -gt 0 ] && [ "$R_SELECTED" -lt "${#R_NAMES[@]}" ]; then
    old_name=${R_NAMES[$R_SELECTED]}
  fi
  remote_list_raw "$REMOTE_PATH" "$raw" || return 1
  R_NAMES=(); R_KINDS=(); R_SIZES=(); R_REASONS=(); R_MARKS=()
  [ "$REMOTE_PATH" = / ] || add_remote_entry '..' d 0 ''
  for pass in d f; do
    while IFS=$'\t' read -r kind size name || [ -n "${kind:-}${size:-}${name:-}" ]; do
      [ "$kind" = "$pass" ] || continue
      reason=
      if [ -n "$MOCK_ROOT" ]; then
        reason=$(unsupported_reason "$(mock_path "$(remote_join "$REMOTE_PATH" "$name")")" "$kind")
      fi
      add_remote_entry "$name" "$kind" "$size" "$reason"
    done < "$raw"
  done
  if [ "${#R_NAMES[@]}" -eq 0 ]; then add_remote_entry '..' d 0 ''; fi
  if [ -n "$old_name" ]; then
    i=0
    while [ "$i" -lt "${#R_NAMES[@]}" ]; do
      [ "${R_NAMES[$i]}" = "$old_name" ] && { found=$i; break; }
      i=$((i + 1))
    done
  fi
  if [ "$found" -ge 0 ]; then R_SELECTED=$found; fi
  [ "$R_SELECTED" -lt "${#R_NAMES[@]}" ] || R_SELECTED=$((${#R_NAMES[@]} - 1))
  [ "$R_SELECTED" -ge 0 ] || R_SELECTED=0
  return 0
}

refresh_panels() {
  load_local_panel
  if ! load_remote_panel; then
    R_NAMES=(); R_KINDS=(); R_SIZES=(); R_REASONS=(); R_MARKS=()
    add_remote_entry '<нет связи>' f 0 'устройство недоступно'
    R_SELECTED=0
  fi
  L_PAGE=0
  R_PAGE=0
}

panel_count() {
  if [ "$1" = L ]; then printf '%s' "${#L_NAMES[@]}"; else printf '%s' "${#R_NAMES[@]}"; fi
}

panel_selected() {
  if [ "$1" = L ]; then printf '%s' "$L_SELECTED"; else printf '%s' "$R_SELECTED"; fi
}

panel_page() {
  if [ "$1" = L ]; then printf '%s' "$L_PAGE"; else printf '%s' "$R_PAGE"; fi
}

panel_name() {
  if [ "$1" = L ]; then printf '%s' "${L_NAMES[$2]}"; else printf '%s' "${R_NAMES[$2]}"; fi
}

panel_kind() {
  if [ "$1" = L ]; then printf '%s' "${L_KINDS[$2]}"; else printf '%s' "${R_KINDS[$2]}"; fi
}

panel_size() {
  if [ "$1" = L ]; then printf '%s' "${L_SIZES[$2]}"; else printf '%s' "${R_SIZES[$2]}"; fi
}

panel_reason() {
  if [ "$1" = L ]; then printf '%s' "${L_REASONS[$2]}"; else printf '%s' "${R_REASONS[$2]}"; fi
}

panel_mark() {
  if [ "$1" = L ]; then printf '%s' "${L_MARKS[$2]}"; else printf '%s' "${R_MARKS[$2]}"; fi
}

set_panel_selected() {
  if [ "$1" = L ]; then L_SELECTED=$2; else R_SELECTED=$2; fi
}

set_panel_page() {
  if [ "$1" = L ]; then L_PAGE=$2; else R_PAGE=$2; fi
}

set_panel_mark() {
  if [ "$1" = L ]; then L_MARKS[$2]=$3; else R_MARKS[$2]=$3; fi
}

clear_panel_marks() {
  local panel=$1 count i=0
  count=$(panel_count "$panel")
  while [ "$i" -lt "$count" ]; do set_panel_mark "$panel" "$i" 0; i=$((i + 1)); done
}

collect_selected_indices() {
  local panel=$1 count i=0 marked=0 selected
  SELECTED_INDICES=()
  count=$(panel_count "$panel")
  while [ "$i" -lt "$count" ]; do
    if [ "$(panel_mark "$panel" "$i")" -eq 1 ] && [ "$(panel_name "$panel" "$i")" != '..' ]; then
      SELECTED_INDICES[${#SELECTED_INDICES[@]}]=$i
      marked=1
    fi
    i=$((i + 1))
  done
  if [ "$marked" -eq 0 ]; then
    selected=$(panel_selected "$panel")
    [ "$(panel_name "$panel" "$selected")" != '..' ] && SELECTED_INDICES[0]=$selected
  fi
}

plan_reset() {
  PLAN_KINDS=(); PLAN_SOURCES=(); PLAN_DESTINATIONS=(); PLAN_SIZES=()
  PLAN_TOTAL=0
  PLAN_ERROR=
}

plan_add() {
  local kind=$1 source=$2 destination=$3 size=$4 index=${#PLAN_KINDS[@]}
  PLAN_KINDS[$index]=$kind
  PLAN_SOURCES[$index]=$source
  PLAN_DESTINATIONS[$index]=$destination
  PLAN_SIZES[$index]=$size
  [ "$kind" = f ] && PLAN_TOTAL=$((PLAN_TOTAL + size))
  return 0
}

plan_local_tree() {
  local source=$1 destination=$2 kind reason child name size source_lower destination_leaf destination_lower
  if [ -L "$source" ]; then kind=l
  elif [ -d "$source" ]; then kind=d
  elif [ -f "$source" ]; then kind=f
  else kind=o
  fi
  reason=$(unsupported_reason "$source" "$kind")
  if [ -n "$reason" ]; then PLAN_ERROR="${source##*/}: $reason"; return 1; fi
  if [ "$kind" = f ]; then
    source_lower=$(lowercase "${source##*/}")
    case "$source_lower" in
      focal.mod|basic.mod|wbmp.mod)
        destination_leaf=${destination#/}
        destination_lower=$(lowercase "$destination_leaf")
        if [ "$destination_leaf" != "${destination_leaf#*/}" ] ||
           [ "$destination_lower" != "$source_lower" ]; then
          PLAN_ERROR="${source##*/}: модуль сохраняется только в корне под своим фиксированным именем"
          return 1
        fi
        ;;
    esac
    size=$(wc -c < "$source" | tr -d '[:space:]')
    plan_add f "$source" "$destination" "$size"
    return 0
  fi
  plan_add d "$source" "$destination" 0
  local children=("$source"/*)
  for child in "${children[@]}"; do
    [ -e "$child" ] || [ -L "$child" ] || continue
    name=${child##*/}
    plan_local_tree "$child" "$(remote_join "$destination" "$name")" || return 1
  done
}

plan_remote_tree() {
  local source=$1 destination=$2 kind=$3 size=$4 raw child_kind child_size child_name child_source
  if [ "$kind" = f ]; then
    plan_add f "$source" "$destination" "$size"
    return 0
  fi
  plan_add d "$source" "$destination" 0
  PLAN_SERIAL=$((PLAN_SERIAL + 1))
  raw="$SESSION_DIR/plan.$PLAN_SERIAL.list"
  remote_list_raw "$source" "$raw" || { PLAN_ERROR=$STATUS_TEXT; return 1; }
  while IFS=$'\t' read -r child_kind child_size child_name ||
        [ -n "${child_kind:-}${child_size:-}${child_name:-}" ]; do
    child_source=$(remote_join "$source" "$child_name")
    plan_remote_tree "$child_source" "$destination/$child_name" \
      "$child_kind" "$child_size" || return 1
  done < "$raw"
}

term_size() {
  local size
  size=$(stty size <&9 2>/dev/null) || size='24 80'
  TERM_LINES=${size%% *}
  TERM_COLS=${size#* }
  case "$TERM_LINES:$TERM_COLS" in *[!0-9:]*|:*) TERM_LINES=24; TERM_COLS=80 ;; esac
  [ "$TERM_LINES" -ge 18 ] || TERM_LINES=18
  [ "$TERM_COLS" -ge 70 ] || TERM_COLS=70
  UI_WIDTH=$((TERM_COLS - 4))
  [ "$UI_WIDTH" -le 92 ] || UI_WIDTH=92
  [ "$UI_WIDTH" -ge 70 ] || UI_WIDTH=70
  UI_HEIGHT=$((TERM_LINES - 2))
  [ "$UI_HEIGHT" -le 25 ] || UI_HEIGHT=25
  [ "$UI_HEIGHT" -ge 18 ] || UI_HEIGHT=18
  UI_X=$(((TERM_COLS - UI_WIDTH) / 2 + 1))
  UI_Y=$(((TERM_LINES - UI_HEIGHT) / 2 + 1))
  LEFT_WIDTH=$((UI_WIDTH / 2))
  RIGHT_X=$((UI_X + LEFT_WIDTH))
  RIGHT_WIDTH=$((UI_WIDTH - LEFT_WIDTH))
  HEADER_ROW=$((UI_Y + 1))
  PANEL_BOTTOM=$((UI_Y + UI_HEIGHT - 3))
  PANEL_SEPARATOR=$((PANEL_BOTTOM - 2))
  PANEL_INFO_ROW=$((PANEL_BOTTOM - 1))
  LIST_TOP=$((UI_Y + 2))
  LIST_BOTTOM=$((PANEL_SEPARATOR - 1))
  LIST_ROWS=$((LIST_BOTTOM - LIST_TOP + 1))
  COMMAND_ROW=$((UI_Y + UI_HEIGHT - 2))
  STATUS_ROW=$COMMAND_ROW
  FUNCTION_ROW=$((UI_Y + UI_HEIGHT - 1))
}

cursor_to() {
  printf '\033[%d;%dH' "$1" "$2" >&9
}

clip_text() {
  local text=$1 width=$2
  text=${text//$'\n'/?}
  text=${text//$'\r'/?}
  text=${text//$'\t'/→}
  if [ "${#text}" -gt "$width" ]; then
    if [ "$width" -gt 1 ]; then printf '%s…' "${text:0:$((width - 1))}"; fi
  else
    printf '%s' "$text"
  fi
}

fit_text() {
  local text width clipped padding
  text=$1; width=$2
  clipped=$(clip_text "$text" "$width")
  padding=$((width - ${#clipped}))
  [ "$padding" -ge 0 ] || padding=0
  printf '%s%s' "$clipped" "$(repeat_char ' ' "$padding")"
}

center_text() {
  local text=$1 width=$2 clipped left right
  clipped=$(clip_text "$text" "$width")
  left=$(((width - ${#clipped}) / 2))
  [ "$left" -ge 0 ] || left=0
  right=$((width - ${#clipped} - left))
  [ "$right" -ge 0 ] || right=0
  printf '%s%s%s' "$(repeat_char ' ' "$left")" "$clipped" \
    "$(repeat_char ' ' "$right")"
}

display_local_path() {
  case "$LOCAL_PATH" in
    "$HOME") printf '~' ;;
    "$HOME"/*) printf '~/%s' "${LOCAL_PATH#"$HOME"/}" ;;
    *) printf '%s' "$LOCAL_PATH" ;;
  esac
}

panel_geometry() {
  if [ "$1" = L ]; then
    PANEL_X=$UI_X; PANEL_WIDTH=$LEFT_WIDTH
  else
    PANEL_X=$RIGHT_X; PANEL_WIDTH=$RIGHT_WIDTH
  fi
  PANEL_INNER=$((PANEL_WIDTH - 2))
  PANEL_COLUMNS=$((PANEL_INNER / 18))
  [ "$PANEL_COLUMNS" -ge 1 ] || PANEL_COLUMNS=1
  [ "$PANEL_COLUMNS" -le 4 ] || PANEL_COLUMNS=4
  PANEL_COLUMN_AREA=$((PANEL_INNER - PANEL_COLUMNS + 1))
  PANEL_CELL_WIDTH=$((PANEL_COLUMN_AREA / PANEL_COLUMNS))
  PANEL_CELL_REMAINDER=$((PANEL_COLUMN_AREA % PANEL_COLUMNS))
  PANEL_CAPACITY=$((LIST_ROWS * PANEL_COLUMNS))
}

panel_column_geometry() {
  local column=$1 index=0 width
  PANEL_COLUMN_X=$((PANEL_X + 1))
  while [ "$index" -lt "$column" ]; do
    width=$PANEL_CELL_WIDTH
    [ "$index" -lt "$PANEL_CELL_REMAINDER" ] && width=$((width + 1))
    PANEL_COLUMN_X=$((PANEL_COLUMN_X + width + 1))
    index=$((index + 1))
  done
  PANEL_COLUMN_WIDTH=$PANEL_CELL_WIDTH
  [ "$column" -lt "$PANEL_CELL_REMAINDER" ] && \
    PANEL_COLUMN_WIDTH=$((PANEL_COLUMN_WIDTH + 1))
}

ensure_panel_page() {
  local panel=$1 selected page
  panel_geometry "$panel"
  selected=$(panel_selected "$panel")
  page=$((selected / PANEL_CAPACITY * PANEL_CAPACITY))
  set_panel_page "$panel" "$page"
}

draw_panel_top() {
  local panel=$1 title label rest left right title_style
  panel_geometry "$panel"
  if [ "$panel" = L ]; then title=$(display_local_path); else title="MK61s:$REMOTE_PATH"; fi
  title=$(clip_text "$title" "$((PANEL_WIDTH - 8))")
  label=" $title "
  rest=$((PANEL_INNER - ${#label}))
  [ "$rest" -ge 0 ] || rest=0
  left=$((rest / 2)); right=$((rest - left))
  if [ "$panel" = "$ACTIVE_PANEL" ]; then title_style=$C_MENU
  else title_style=$C_FILE
  fi
  cursor_to "$UI_Y" "$PANEL_X"
  printf '%s╔%s%s%s%s%s╗' "$C_BORDER" "$(repeat_char '═' "$left")" \
    "$title_style" "$label" "$C_BORDER" "$(repeat_char '═' "$right")" >&9
}

draw_panel_frame() {
  local panel=$1 row column
  panel_geometry "$panel"
  draw_panel_top "$panel"

  cursor_to "$HEADER_ROW" "$PANEL_X"
  printf '%s║' "$C_BORDER" >&9
  column=0
  while [ "$column" -lt "$PANEL_COLUMNS" ]; do
    panel_column_geometry "$column"
    printf '%s%s' "$C_STATUS" "$(center_text 'Name' "$PANEL_COLUMN_WIDTH")" >&9
    [ "$column" -eq "$((PANEL_COLUMNS - 1))" ] || printf '%s│' "$C_BORDER" >&9
    column=$((column + 1))
  done
  printf '%s║' "$C_BORDER" >&9

  row=$LIST_TOP
  while [ "$row" -le "$LIST_BOTTOM" ]; do
    cursor_to "$row" "$PANEL_X"
    printf '%s║' "$C_BORDER" >&9
    column=0
    while [ "$column" -lt "$PANEL_COLUMNS" ]; do
      panel_column_geometry "$column"
      printf '%s%s' "$C_PANEL" "$(repeat_char ' ' "$PANEL_COLUMN_WIDTH")" >&9
      [ "$column" -eq "$((PANEL_COLUMNS - 1))" ] || printf '%s│' "$C_BORDER" >&9
      column=$((column + 1))
    done
    printf '%s║' "$C_BORDER" >&9
    row=$((row + 1))
  done

  cursor_to "$PANEL_SEPARATOR" "$PANEL_X"
  printf '%s╠' "$C_BORDER" >&9
  column=0
  while [ "$column" -lt "$PANEL_COLUMNS" ]; do
    panel_column_geometry "$column"
    printf '%s' "$(repeat_char '═' "$PANEL_COLUMN_WIDTH")" >&9
    [ "$column" -eq "$((PANEL_COLUMNS - 1))" ] || printf '╪' >&9
    column=$((column + 1))
  done
  printf '╣' >&9

  cursor_to "$PANEL_INFO_ROW" "$PANEL_X"
  printf '%s║%s%s%s║' "$C_BORDER" "$C_PANEL" \
    "$(repeat_char ' ' "$PANEL_INNER")" "$C_BORDER" >&9
  cursor_to "$PANEL_BOTTOM" "$PANEL_X"
  printf '%s╚%s╝' "$C_BORDER" "$(repeat_char '═' "$PANEL_INNER")" >&9
}

entry_style() {
  local panel=$1 index=$2 selected reason mark kind
  selected=$(panel_selected "$panel")
  reason=$(panel_reason "$panel" "$index")
  mark=$(panel_mark "$panel" "$index")
  kind=$(panel_kind "$panel" "$index")
  if [ "$panel" = "$ACTIVE_PANEL" ] && [ "$index" -eq "$selected" ]; then
    if [ -n "$reason" ]; then printf '%s' "$C_SELECTED_DISABLED"; else printf '%s' "$C_SELECTED"; fi
  elif [ -n "$reason" ]; then printf '%s' "$C_DISABLED"
  elif [ "$mark" -eq 1 ]; then printf '%s' "$C_MARKED"
  elif [ "$kind" = d ]; then printf '%s' "$C_DIR"
  else printf '%s' "$C_FILE"
  fi
}

draw_panel_slot() {
  local panel=$1 slot=$2 index row column text name style
  panel_geometry "$panel"
  index=$(($(panel_page "$panel") + slot))
  row=$((LIST_TOP + slot % LIST_ROWS))
  column=$((slot / LIST_ROWS))
  panel_column_geometry "$column"
  cursor_to "$row" "$PANEL_COLUMN_X"
  if [ "$index" -ge "$(panel_count "$panel")" ]; then
    printf '%s%s' "$C_PANEL" "$(repeat_char ' ' "$PANEL_COLUMN_WIDTH")" >&9
    return
  fi
  name=$(panel_name "$panel" "$index")
  text=$(fit_text " $name" "$PANEL_COLUMN_WIDTH")
  style=$(entry_style "$panel" "$index")
  printf '%s%s' "$style" "$text" >&9
}

draw_panel_entries() {
  local panel=$1 slot=0
  panel_geometry "$panel"
  ensure_panel_page "$panel"
  printf '\033[?2026h' >&9
  while [ "$slot" -lt "$PANEL_CAPACITY" ]; do
    draw_panel_slot "$panel" "$slot"
    slot=$((slot + 1))
  done
  draw_panel_info "$panel"
  printf '\033[?2026l' >&9
}

draw_panel_info() {
  local panel=$1 selected name kind size reason text style
  panel_geometry "$panel"
  selected=$(panel_selected "$panel")
  name=$(panel_name "$panel" "$selected")
  kind=$(panel_kind "$panel" "$selected")
  size=$(panel_size "$panel" "$selected")
  reason=$(panel_reason "$panel" "$selected")
  if [ -n "$reason" ]; then text="$name · $reason"; style=$C_DISABLED
  elif [ "$kind" = d ]; then text="$name    <SUB-DIR>"; style=$C_FILE
  else text="$name    $size B"; style=$C_FILE
  fi
  cursor_to "$PANEL_INFO_ROW" "$((PANEL_X + 1))"
  printf '%s%s' "$style" "$(center_text "$text" "$PANEL_INNER")" >&9
}

draw_command_line() {
  local path prompt max_prompt path_start input_width offset=0 visible cursor_column
  if [ "$ACTIVE_PANEL" = L ]; then
    path=$(display_local_path)
  else
    path="MK61s:$REMOTE_PATH"
  fi
  max_prompt=$((UI_WIDTH / 2 - 2))
  [ "$max_prompt" -ge 8 ] || max_prompt=8
  if [ "${#path}" -gt "$max_prompt" ]; then
    path_start=$((${#path} - max_prompt + 1))
    path="…${path:$path_start}"
  fi
  prompt="$path> "
  input_width=$((UI_WIDTH - ${#prompt}))
  [ "$input_width" -ge 1 ] || input_width=1
  if [ "$COMMAND_CURSOR" -ge "$input_width" ]; then
    offset=$((COMMAND_CURSOR - input_width + 1))
  fi
  visible=${COMMAND_TEXT:$offset:$input_width}
  cursor_to "$COMMAND_ROW" "$UI_X"
  printf '%s%s%s' "$C_COMMAND" "$prompt" \
    "$(fit_text "$visible" "$input_width")" >&9
  cursor_column=$((COMMAND_CURSOR - offset))
  [ "$cursor_column" -lt "$input_width" ] || cursor_column=$((input_width - 1))
  cursor_to "$COMMAND_ROW" "$((UI_X + ${#prompt} + cursor_column))"
  printf '\033[?25h' >&9
}

# Старые операции вызывают draw_status для промежуточного обновления. Строка
# теперь всегда остаётся командной и больше не превращается в область сообщений.
draw_status() {
  draw_command_line
}

draw_function_bar() {
  local labels=('Help' '' 'View' '' 'Copy' 'RenMov' 'Mkdir' 'Delete' 'Info' 'Quit')
  local i=0 width base extra label number number_width
  base=$((UI_WIDTH / 10)); extra=$((UI_WIDTH % 10))
  cursor_to "$FUNCTION_ROW" "$UI_X"
  while [ "$i" -lt 10 ]; do
    width=$base
    [ "$i" -lt "$extra" ] && width=$((width + 1))
    number=$((i + 1)); label=${labels[$i]}
    number_width=${#number}
    printf '%s%s%s%s' "$C_FUNCTION_NUMBER" "$number" "$C_FUNCTION_LABEL" \
      "$(fit_text "$label" "$((width - number_width))")" >&9
    i=$((i + 1))
  done
}

draw_screen() {
  local row
  term_size
  printf '%s\033[?2026h\033[2J\033[H' "$C_OUTSIDE" >&9
  row=$UI_Y
  while [ "$row" -lt "$((UI_Y + UI_HEIGHT))" ]; do
    cursor_to "$row" "$UI_X"
    printf '%s%s' "$C_PANEL" "$(repeat_char ' ' "$UI_WIDTH")" >&9
    row=$((row + 1))
  done
  draw_panel_frame L
  draw_panel_frame R
  draw_panel_entries L
  draw_panel_entries R
  draw_function_bar
  draw_command_line
  printf '\033[?2026l' >&9
}

draw_selection_delta() {
  local panel=$1 old=$2 old_page=$3 new_page slot
  panel_geometry "$panel"
  ensure_panel_page "$panel"
  new_page=$(panel_page "$panel")
  if [ "$new_page" -ne "$old_page" ]; then
    draw_panel_entries "$panel"
  else
    slot=$((old - old_page))
    [ "$slot" -ge 0 ] && [ "$slot" -lt "$PANEL_CAPACITY" ] && draw_panel_slot "$panel" "$slot"
    slot=$(($(panel_selected "$panel") - new_page))
    [ "$slot" -ge 0 ] && [ "$slot" -lt "$PANEL_CAPACITY" ] && draw_panel_slot "$panel" "$slot"
    draw_panel_info "$panel"
  fi
}

move_selection() {
  local delta=$1 panel=$ACTIVE_PANEL old selected count page next
  old=$(panel_selected "$panel")
  page=$(panel_page "$panel")
  selected=$old
  count=$(panel_count "$panel")
  panel_geometry "$panel"
  case "$delta" in
    up) selected=$((selected - 1)) ;;
    down) selected=$((selected + 1)) ;;
    left) selected=$((selected - LIST_ROWS)) ;;
    right) selected=$((selected + LIST_ROWS)) ;;
    home) selected=0 ;;
    end) selected=$((count - 1)) ;;
    pgup) selected=$((selected - PANEL_CAPACITY)) ;;
    pgdn) selected=$((selected + PANEL_CAPACITY)) ;;
  esac
  [ "$selected" -ge 0 ] || selected=0
  [ "$selected" -lt "$count" ] || selected=$((count - 1))
  [ "$selected" -eq "$old" ] && return
  set_panel_selected "$panel" "$selected"
  draw_selection_delta "$panel" "$old" "$page"
}

switch_panel() {
  local old=$ACTIVE_PANEL old_selected old_page new_selected new_page
  old_selected=$(panel_selected "$old"); old_page=$(panel_page "$old")
  if [ "$ACTIVE_PANEL" = L ]; then ACTIVE_PANEL=R; else ACTIVE_PANEL=L; fi
  new_selected=$(panel_selected "$ACTIVE_PANEL"); new_page=$(panel_page "$ACTIVE_PANEL")
  printf '\033[?2026h' >&9
  draw_panel_top "$old"; draw_panel_top "$ACTIVE_PANEL"
  draw_selection_delta "$old" "$old_selected" "$old_page"
  draw_selection_delta "$ACTIVE_PANEL" "$new_selected" "$new_page"
  draw_command_line
  printf '\033[?2026l' >&9
}

read_escape_tail() {
  local rest= char count=0
  stty -echo -icanon -iexten discard undef min 0 time 1 <&9 2>/dev/null || true
  # Читаем ровно одну CSI/SS3-последовательность. У SS3 первый байт `O` —
  # это префикс, а не конец: macOS Terminal кодирует F1..F4 как Esc O P..S.
  while [ "$count" -lt 8 ]; do
    char=$(dd bs=1 count=1 <&9 2>/dev/null) || true
    [ -n "$char" ] || break
    rest=$rest$char
    case "$rest" in
      O?) break ;;
      \[*[A-Za-z~]) break ;;
    esac
    count=$((count + 1))
  done
  stty -echo -icanon -iexten discard undef min 1 time 0 <&9 2>/dev/null || true
  printf '%s' "$rest"
}

drain_pending_input() {
  local char count=0
  stty -echo -icanon -iexten discard undef min 0 time 0 <&9 2>/dev/null || true
  while [ "$count" -lt 64 ]; do
    char=$(dd bs=1 count=1 <&9 2>/dev/null) || true
    [ -n "$char" ] || break
    count=$((count + 1))
  done
  stty -echo -icanon -iexten discard undef min 1 time 0 <&9 2>/dev/null || true
}

read_key() {
  local key rest
  IFS= read -rsn1 key <&9 || return 1
  if [ "$key" = $'\033' ]; then
    rest=$(read_escape_tail)
    case "$rest" in
      '[A'|'OA') printf up ;;
      '[B'|'OB') printf down ;;
      '[C'|'OC') printf right ;;
      '[D'|'OD') printf left ;;
      '[H'|'OH'|'[1~'|'[7~') printf home ;;
      '[F'|'OF'|'[4~'|'[8~') printf end ;;
      '[5~') printf pgup ;;
      '[6~') printf pgdn ;;
      '[2~') printf insert ;;
      '[3~') printf delete ;;
      'OP'|'[11~'|'[[A') printf f1 ;;
      'OQ'|'[12~'|'[[B') printf f2 ;;
      'OR'|'[13~'|'[[C') printf f3 ;;
      'OS'|'[14~'|'[[D') printf f4 ;;
      '[15~'|'[[E') printf f5 ;;
      '[17~') printf f6 ;;
      '[18~') printf f7 ;;
      '[19~') printf f8 ;;
      '[20~') printf f9 ;;
      '[21~') printf f10 ;;
      \[11\;*~|\[1\;*P) printf f1 ;;
      \[12\;*~|\[1\;*Q) printf f2 ;;
      \[13\;*~|\[1\;*R) printf f3 ;;
      \[14\;*~|\[1\;*S) printf f4 ;;
      \[15\;*~) printf f5 ;;
      \[17\;*~) printf f6 ;;
      \[18\;*~) printf f7 ;;
      \[19\;*~) printf f8 ;;
      \[20\;*~) printf f9 ;;
      \[21\;*~) printf f10 ;;
      *) printf esc ;;
    esac
  elif [ -z "$key" ]; then printf enter
  elif [ "$key" = $'\t' ]; then printf tab
  elif [ "$key" = ' ' ]; then printf space
  elif [ "$key" = $'\177' ] || [ "$key" = $'\010' ]; then printf backspace
  elif [ "$key" = $'\017' ]; then printf console
  elif [ "$key" = $'\022' ]; then printf refresh
  else printf '%s' "$key"
  fi
}

dialog_geometry() {
  DIALOG_WIDTH=$1; DIALOG_HEIGHT=$2
  [ "$DIALOG_WIDTH" -le "$((UI_WIDTH - 6))" ] || DIALOG_WIDTH=$((UI_WIDTH - 6))
  [ "$DIALOG_HEIGHT" -le "$((UI_HEIGHT - 4))" ] || DIALOG_HEIGHT=$((UI_HEIGHT - 4))
  DIALOG_X=$((UI_X + (UI_WIDTH - DIALOG_WIDTH) / 2))
  DIALOG_Y=$((UI_Y + (UI_HEIGHT - DIALOG_HEIGHT - 1) / 2))
}

draw_dialog_frame() {
  local title=$1 requested_width=$2 requested_height=$3 row label rest left right
  printf '\033[?25l' >&9
  dialog_geometry "$requested_width" "$requested_height"

  # Чёрная двухсимвольная тень — характерная деталь диалогов NC.
  row=$((DIALOG_Y + 1))
  while [ "$row" -lt "$((DIALOG_Y + DIALOG_HEIGHT))" ]; do
    cursor_to "$row" "$((DIALOG_X + DIALOG_WIDTH))"
    printf '%s  ' "$C_SHADOW" >&9
    row=$((row + 1))
  done
  cursor_to "$((DIALOG_Y + DIALOG_HEIGHT))" "$((DIALOG_X + 2))"
  printf '%s%s' "$C_SHADOW" "$(repeat_char ' ' "$DIALOG_WIDTH")" >&9

  label=" $title "
  label=$(clip_text "$label" "$((DIALOG_WIDTH - 8))")
  rest=$((DIALOG_WIDTH - 2 - ${#label}))
  [ "$rest" -ge 0 ] || rest=0
  left=$((rest / 2)); right=$((rest - left))
  cursor_to "$DIALOG_Y" "$DIALOG_X"
  printf '%s╔%s%s%s%s%s╗' "$C_DIALOG_BORDER" "$(repeat_char '═' "$left")" \
    "$C_DIALOG_TITLE" "$label" "$C_DIALOG_BORDER" "$(repeat_char '═' "$right")" >&9

  row=$((DIALOG_Y + 1))
  while [ "$row" -lt "$((DIALOG_Y + DIALOG_HEIGHT - 1))" ]; do
    cursor_to "$row" "$DIALOG_X"
    printf '%s║%s%s%s║' "$C_DIALOG_BORDER" "$C_DIALOG" \
      "$(repeat_char ' ' "$((DIALOG_WIDTH - 2))")" "$C_DIALOG_BORDER" >&9
    row=$((row + 1))
  done
  cursor_to "$((DIALOG_Y + DIALOG_HEIGHT - 1))" "$DIALOG_X"
  printf '%s╚%s╝' "$C_DIALOG_BORDER" \
    "$(repeat_char '═' "$((DIALOG_WIDTH - 2))")" >&9
}

draw_dialog_buttons() {
  local ok_label=$1 cancel_label=$2 focus=$3 row total start ok_style cancel_style
  local ok="[ $ok_label ]" cancel="[ $cancel_label ]"
  row=$((DIALOG_Y + DIALOG_HEIGHT - 3))
  if [ -z "$cancel_label" ]; then
    start=$((DIALOG_X + (DIALOG_WIDTH - ${#ok}) / 2))
    if [ "$focus" = ok ]; then ok_style=$C_DIALOG_BUTTON_ACTIVE
    else ok_style=$C_DIALOG_BUTTON
    fi
    cursor_to "$row" "$start"
    printf '%s%s' "$ok_style" "$ok" >&9
    return
  fi
  total=$((${#ok} + ${#cancel} + 4))
  start=$((DIALOG_X + (DIALOG_WIDTH - total) / 2))
  ok_style=$C_DIALOG_BUTTON; cancel_style=$C_DIALOG_BUTTON
  [ "$focus" = ok ] && ok_style=$C_DIALOG_BUTTON_ACTIVE
  [ "$focus" = cancel ] && cancel_style=$C_DIALOG_BUTTON_ACTIVE
  cursor_to "$row" "$start"
  printf '%s%s%s    %s' "$ok_style" "$ok" "$C_DIALOG" "$cancel_style$cancel" >&9
}

dialog_text_input() {
  local title=$1 prompt=$2 default=$3 ok_label=${4:-OK}
  local value=$default cursor=${#default} focus=field key input_x input_y input_width
  local offset visible cursor_column
  draw_dialog_frame "$title" 66 9
  input_x=$((DIALOG_X + 3)); input_y=$((DIALOG_Y + 4))
  input_width=$((DIALOG_WIDTH - 6))
  cursor_to "$((DIALOG_Y + 2))" "$input_x"
  printf '%s%s' "$C_DIALOG" "$(fit_text "$prompt" "$input_width")" >&9

  while true; do
    offset=0
    if [ "$cursor" -ge "$input_width" ]; then offset=$((cursor - input_width + 1)); fi
    visible=${value:$offset:$input_width}
    cursor_to "$input_y" "$input_x"
    printf '%s%s' "$C_DIALOG_INPUT" "$(fit_text "$visible" "$input_width")" >&9
    draw_dialog_buttons "$ok_label" 'Cancel' "$focus"
    if [ "$focus" = field ]; then
      cursor_column=$((cursor - offset))
      [ "$cursor_column" -lt "$input_width" ] || cursor_column=$((input_width - 1))
      cursor_to "$input_y" "$((input_x + cursor_column))"
      printf '\033[?25h' >&9
    else
      printf '\033[?25l' >&9
    fi

    key=$(read_key) || { UI_CONFIRMED=0; break; }
    case "$key" in
      esc|f10) UI_CONFIRMED=0; break ;;
      enter)
        if [ "$focus" = cancel ]; then UI_CONFIRMED=0; else UI_CONFIRMED=1; fi
        break
        ;;
      tab)
        case "$focus" in field) focus=ok ;; ok) focus=cancel ;; *) focus=field ;; esac
        ;;
      up|down)
        if [ "$focus" = field ]; then focus=ok; else focus=field; fi
        ;;
      left)
        if [ "$focus" = field ]; then [ "$cursor" -gt 0 ] && cursor=$((cursor - 1))
        else focus=ok
        fi
        ;;
      right)
        if [ "$focus" = field ]; then [ "$cursor" -lt "${#value}" ] && cursor=$((cursor + 1))
        else focus=cancel
        fi
        ;;
      home) [ "$focus" = field ] && cursor=0 ;;
      end) [ "$focus" = field ] && cursor=${#value} ;;
      backspace)
        if [ "$focus" = field ] && [ "$cursor" -gt 0 ]; then
          value=${value:0:$((cursor - 1))}${value:$cursor}
          cursor=$((cursor - 1))
        fi
        ;;
      delete)
        if [ "$focus" = field ] && [ "$cursor" -lt "${#value}" ]; then
          value=${value:0:$cursor}${value:$((cursor + 1))}
        fi
        ;;
      space)
        if [ "$focus" = field ]; then
          value=${value:0:$cursor}' '${value:$cursor}; cursor=$((cursor + 1))
        fi
        ;;
      $'\025') [ "$focus" = field ] && { value=; cursor=0; } ;;
      f1|f2|f3|f4|f5|f6|f7|f8|f9|insert|pgup|pgdn|refresh) ;;
      *)
        if [ "$focus" = field ]; then
          value=${value:0:$cursor}$key${value:$cursor}
          cursor=$((cursor + ${#key}))
        fi
        ;;
    esac
  done
  printf '\033[?25l' >&9
  UI_VALUE=$value
  draw_screen
  [ "$UI_CONFIRMED" -eq 1 ]
}

dialog_wrap() {
  local text=$1 width=$2 word current= combined
  local words=()
  DIALOG_LINES=()
  text=${text//$'\n'/ }
  IFS=' ' read -r -a words <<< "$text"
  for word in "${words[@]}"; do
    if [ -z "$current" ]; then combined=$word; else combined="$current $word"; fi
    if [ "${#combined}" -le "$width" ]; then current=$combined
    else
      DIALOG_LINES[${#DIALOG_LINES[@]}]=$current
      current=$word
    fi
  done
  [ -n "$current" ] && DIALOG_LINES[${#DIALOG_LINES[@]}]=$current
  [ "${#DIALOG_LINES[@]}" -gt 0 ] || DIALOG_LINES[0]=
}

ui_confirm() {
  local prompt=$1 key choice=cancel row index width=66
  dialog_wrap "$prompt" 54
  draw_dialog_frame 'Confirm' "$width" "$((7 + ${#DIALOG_LINES[@]}))"
  row=$((DIALOG_Y + 2)); index=0
  while [ "$index" -lt "${#DIALOG_LINES[@]}" ]; do
    cursor_to "$row" "$((DIALOG_X + 3))"
    printf '%s%s' "$C_DIALOG" \
      "$(center_text "${DIALOG_LINES[$index]}" "$((DIALOG_WIDTH - 6))")" >&9
    row=$((row + 1)); index=$((index + 1))
  done
  while true; do
    draw_dialog_buttons 'Yes' 'No' "$choice"
    key=$(read_key) || { UI_CONFIRMED=0; break; }
    case "$key" in
      y|Y|д|Д) UI_CONFIRMED=1; break ;;
      n|N|т|Т|esc|f10) UI_CONFIRMED=0; break ;;
      left|right|tab) if [ "$choice" = ok ]; then choice=cancel; else choice=ok; fi ;;
      enter) if [ "$choice" = ok ]; then UI_CONFIRMED=1; else UI_CONFIRMED=0; fi; break ;;
    esac
  done
  draw_screen
}

ui_input() {
  dialog_text_input "$1" "$1" "$2" "${3:-OK}"
}

ui_alert() {
  local title=$1 text=$2 key row index height
  dialog_wrap "$text" 54
  height=$((7 + ${#DIALOG_LINES[@]}))
  draw_dialog_frame "$title" 66 "$height"
  row=$((DIALOG_Y + 2)); index=0
  while [ "$index" -lt "${#DIALOG_LINES[@]}" ]; do
    cursor_to "$row" "$((DIALOG_X + 3))"
    printf '%s%s' "$C_DIALOG" \
      "$(center_text "${DIALOG_LINES[$index]}" "$((DIALOG_WIDTH - 6))")" >&9
    row=$((row + 1)); index=$((index + 1))
  done
  draw_dialog_buttons 'OK' '' ok
  while true; do
    key=$(read_key) || break
    case "$key" in enter|space|esc|f10) break ;; esac
  done
  draw_screen
}

show_lines() {
  local title=$1 file=$2 top=0 key row index line available viewer_bottom shown_end max_top
  local content_start content_end status_row inner label rest left right
  local lines=()
  # Один физический F3 в некоторых терминалах оставляет второй код в очереди.
  # Удаляем его до отрисовки, когда следующего осмысленного нажатия ещё нет.
  drain_pending_input
  while IFS= read -r line || [ -n "$line" ]; do lines[${#lines[@]}]=$line; done < "$file"
  [ "${#lines[@]}" -gt 0 ] || lines[0]='(пусто)'
  inner=$((UI_WIDTH - 2))
  viewer_bottom=$((UI_Y + UI_HEIGHT - 2))
  content_start=$((UI_Y + 1))
  status_row=$((viewer_bottom - 1))
  content_end=$((status_row - 1))
  available=$((content_end - content_start + 1))
  max_top=$((${#lines[@]} - available)); [ "$max_top" -ge 0 ] || max_top=0
  while true; do
    printf '%s\033[?25l\033[?2026h\033[2J\033[H' "$C_OUTSIDE" >&9
    label=" $title "; label=$(clip_text "$label" "$((UI_WIDTH - 8))")
    rest=$((inner - ${#label})); [ "$rest" -ge 0 ] || rest=0
    left=$((rest / 2)); right=$((rest - left))
    cursor_to "$UI_Y" "$UI_X"
    printf '%s╔%s%s%s%s%s╗' "$C_BORDER" "$(repeat_char '═' "$left")" \
      "$C_MENU" "$label" "$C_BORDER" "$(repeat_char '═' "$right")" >&9
    row=$content_start
    while [ "$row" -le "$content_end" ]; do
      index=$((top + row - content_start))
      cursor_to "$row" "$UI_X"
      if [ "$index" -lt "${#lines[@]}" ]; then line=${lines[$index]}; else line=; fi
      printf '%s║%s%s%s║' "$C_BORDER" "$C_FILE" \
        "$(fit_text " $line" "$inner")" "$C_BORDER" >&9
      row=$((row + 1))
    done
    shown_end=$((top + available))
    [ "$shown_end" -le "${#lines[@]}" ] || shown_end=${#lines[@]}
    cursor_to "$status_row" "$UI_X"
    printf '%s║%s%s%s║' "$C_BORDER" "$C_STATUS" \
      "$(center_text "Lines $((top + 1))–$shown_end / ${#lines[@]}  ·  Esc/F3 — close" "$inner")" \
      "$C_BORDER" >&9
    cursor_to "$viewer_bottom" "$UI_X"
    printf '%s╚%s╝' "$C_BORDER" "$(repeat_char '═' "$inner")" >&9
    draw_function_bar
    printf '\033[?2026l' >&9
    key=$(read_key) || break
    case "$key" in
      up) [ "$top" -gt 0 ] && top=$((top - 1)) ;;
      down) [ "$((top + available))" -lt "${#lines[@]}" ] && top=$((top + 1)) ;;
      pgup) top=$((top - available)); [ "$top" -ge 0 ] || top=0 ;;
      pgdn) top=$((top + available)); [ "$top" -le "$max_top" ] || top=$max_top ;;
      home) top=0 ;;
      end) top=$max_top ;;
      esc|f3|enter|f10) break ;;
    esac
  done
  draw_screen
}

show_message() {
  local title=$1 text=$2 file="$SESSION_DIR/message.txt"
  printf '%s\n' "$text" > "$file"
  show_lines "$title" "$file"
}

show_help() {
  show_message 'Помощь' 'MKC — файловый менеджер MK61s

Tab          сменить активную панель
Стрелки      выбрать файл; PgUp/PgDn — страница
Enter        войти в каталог
Backspace    перейти в родительский каталог
Space/Ins    отметить несколько объектов
F3           текст и WBMP (iTerm2 image, иначе Брайль)
F5           копировать между компьютером и калькулятором
F6           переименовать или переместить в активной панели
F7           создать каталог
F8           удалить с подтверждением
F9           сведения о памяти калькулятора
F10          выход
Ctrl-R       обновить обе панели
Ctrl-O       повторно показать последний вывод MK61s

Начните печатать в нижней строке и нажмите Enter. При активной левой панели
команда выполняется локально в её каталоге. При активной правой панели команда
выполняется терминалом MK61s, а её вывод открывается внутри MKC. Esc очищает
набранную команду; Ctrl-P/Ctrl-N листают историю.

Серые файлы имеют неподдерживаемый формат, имя или размер. Их можно
переименовать через F6, просмотреть через F3 и удалить через F8, но F5
на калькулятор для них заблокирован.

FOCAL.MOD, BASIC.MOD и WBMP.MOD загружаются только в корень под этими именами.'
}

command_set_text() {
  COMMAND_TEXT=$1
  COMMAND_CURSOR=${#COMMAND_TEXT}
}

command_reset_history_navigation() {
  COMMAND_HISTORY_INDEX=-1
  COMMAND_HISTORY_DRAFT=
}

command_insert_text() {
  local text=$1
  COMMAND_TEXT=${COMMAND_TEXT:0:$COMMAND_CURSOR}$text${COMMAND_TEXT:$COMMAND_CURSOR}
  COMMAND_CURSOR=$((COMMAND_CURSOR + ${#text}))
  command_reset_history_navigation
}

command_backspace() {
  [ "$COMMAND_CURSOR" -gt 0 ] || return
  COMMAND_TEXT=${COMMAND_TEXT:0:$((COMMAND_CURSOR - 1))}${COMMAND_TEXT:$COMMAND_CURSOR}
  COMMAND_CURSOR=$((COMMAND_CURSOR - 1))
  command_reset_history_navigation
}

command_delete() {
  [ "$COMMAND_CURSOR" -lt "${#COMMAND_TEXT}" ] || return
  COMMAND_TEXT=${COMMAND_TEXT:0:$COMMAND_CURSOR}${COMMAND_TEXT:$((COMMAND_CURSOR + 1))}
  command_reset_history_navigation
}

command_history_add() {
  local command=$1 count=${#COMMAND_HISTORY[@]}
  [ -n "$command" ] || return
  if [ "$count" -eq 0 ] || [ "${COMMAND_HISTORY[$((count - 1))]}" != "$command" ]; then
    COMMAND_HISTORY[$count]=$command
  fi
  command_reset_history_navigation
}

command_history_move() {
  local direction=$1 count=${#COMMAND_HISTORY[@]}
  [ "$count" -gt 0 ] || return
  if [ "$COMMAND_HISTORY_INDEX" -lt 0 ]; then
    COMMAND_HISTORY_DRAFT=$COMMAND_TEXT
    if [ "$direction" = previous ]; then COMMAND_HISTORY_INDEX=$((count - 1)); else return; fi
  elif [ "$direction" = previous ]; then
    [ "$COMMAND_HISTORY_INDEX" -gt 0 ] && COMMAND_HISTORY_INDEX=$((COMMAND_HISTORY_INDEX - 1))
  else
    COMMAND_HISTORY_INDEX=$((COMMAND_HISTORY_INDEX + 1))
    if [ "$COMMAND_HISTORY_INDEX" -ge "$count" ]; then
      COMMAND_HISTORY_INDEX=-1
      command_set_text "$COMMAND_HISTORY_DRAFT"
      return
    fi
  fi
  command_set_text "${COMMAND_HISTORY[$COMMAND_HISTORY_INDEX]}"
}

run_local_command() {
  local command=$1 shown_path result return_text
  shown_path=$(display_local_path)
  printf '\033[0m\033[?25h\033[?1049l' >&9
  stty "$TTY_SAVED" <&9 2>/dev/null || true
  printf '\n%s> %s\n' "$shown_path" "$command" >&9

  # Ctrl-C должен останавливать запущенную команду, а не весь MKC.
  trap '' INT
  (
    trap - INT
    cd "$LOCAL_PATH" || exit 1
    eval "$command"
  ) <&9 >&9 2>&9
  result=$?
  trap 'exit 130' INT
  stty "$TTY_SAVED" <&9 2>/dev/null || true

  if [ "$result" -eq 0 ]; then return_text='Enter — вернуться в MKC'
  else return_text="Код завершения: $result · Enter — вернуться в MKC"
  fi
  printf '\n[%s]' "$return_text" >&9
  IFS= read -r _ <&9 || true

  # В canonical extensions Ctrl-O — системный discard. Без -iexten драйвер
  # терминала съедает его до read_key(), и окно вывода MK61s не открывается.
  stty -echo -icanon -iexten discard undef min 1 time 0 <&9
  printf '\033[?1049h\033[?25l' >&9
  load_local_panel
  draw_screen
}

remote_line_is_prompt() {
  local line=$1
  case "$line" in
    /*'> ')
      REMOTE_CAPTURE_PATH=${line:0:$(( ${#line} - 2 ))}
      return 0
      ;;
    '...> ')
      return 0
      ;;
  esac
  return 1
}

# Выполняет одну строку терминала и пишет только её вывод: эхо команды и prompt
# удаляются. Дополнительный пустой ввод переводит следующий prompt на отдельную
# строку — прошивка сама печатает его без завершающего перевода строки.
remote_capture_command() {
  local command=$1 output=$2 line count=0 saw_echo=0
  : > "$output" || return 1
  REMOTE_CAPTURE_PATH=$REMOTE_PATH
  if [ -n "$MOCK_ROOT" ]; then
    case "$command" in
      pwd) printf '%s\n' "$REMOTE_PATH" > "$output" ;;
      help) printf 'Mock MK61s terminal\nCommands are routed to the right panel.\n' > "$output" ;;
      *) printf 'Mock MK61s: %s\n' "$command" > "$output" ;;
    esac
    return 0
  fi

  if [ "$(byte_length "$command")" -gt 96 ]; then
    STATUS_TEXT='Команда MK61s длиннее безопасных 96 байт'
    printf '%s\n' "$STATUS_TEXT" > "$output"
    return 1
  fi
  remote_send "$command" || { STATUS_TEXT='Не удалось отправить команду MK61s'; return 1; }
  sleep 0.05
  remote_send '' || return 1

  while [ "$count" -lt 2000 ]; do
    if ! serial_read_line 8; then
      STATUS_TEXT='Таймаут ответа терминала MK61s'
      printf '\n[%s]\n' "$STATUS_TEXT" >> "$output"
      return 1
    fi
    line=$SERIAL_LINE
    if [ "$saw_echo" -eq 1 ] && remote_line_is_prompt "$line"; then return 0; fi
    case "$line" in
      /*'> '*) line=${line#*> } ;;
      '...> '*) line=${line#*> } ;;
    esac
    if [ "$saw_echo" -eq 0 ]; then
      if [ "$line" = "$command" ]; then saw_echo=1; continue; fi
      # Полный старый prompt мог остаться после внешнего терминального клиента.
      if remote_line_is_prompt "$line"; then count=$((count + 1)); continue; fi
      saw_echo=1
    fi
    printf '%s\n' "$line" >> "$output"
    count=$((count + 1))
  done
  STATUS_TEXT='Слишком длинный вывод терминала MK61s'
  printf '\n[%s]\n' "$STATUS_TEXT" >> "$output"
  return 1
}

run_remote_command() {
  local command=$1 raw="$SESSION_DIR/mk61-command.raw" sync="$SESSION_DIR/mk61-sync.raw"
  local ok=1 captured_path=$REMOTE_PATH
  LAST_REMOTE_OUTPUT="$SESSION_DIR/mk61-terminal.txt"
  LAST_REMOTE_TITLE="MK61s · $command"
  : > "$LAST_REMOTE_OUTPUT"

  if [ -z "$MOCK_ROOT" ]; then
    if ! remote_capture_command "cd \"$REMOTE_PATH\"" "$sync"; then
      printf 'MK61s:%s> %s\n' "$REMOTE_PATH" "$command" >> "$LAST_REMOTE_OUTPUT"
      cat "$sync" >> "$LAST_REMOTE_OUTPUT"
      ok=0
    fi
  fi
  if [ "$ok" -eq 1 ]; then
    if remote_capture_command "$command" "$raw"; then ok=1; else ok=0; fi
    captured_path=$REMOTE_CAPTURE_PATH
    printf 'MK61s:%s> %s\n' "$REMOTE_PATH" "$command" >> "$LAST_REMOTE_OUTPUT"
    cat "$raw" >> "$LAST_REMOTE_OUTPUT"
  fi
  [ -s "$LAST_REMOTE_OUTPUT" ] || printf '(команда выполнена без вывода)\n' > "$LAST_REMOTE_OUTPUT"

  if [ "$ok" -eq 1 ]; then
    case "$captured_path" in
      /*) REMOTE_PATH=$(remote_normalize / "$captured_path") ;;
    esac
    load_remote_panel || true
    save_config
  fi
  show_lines "$LAST_REMOTE_TITLE" "$LAST_REMOTE_OUTPUT"
}

show_terminal_output() {
  if [ -n "$LAST_REMOTE_OUTPUT" ] && [ -r "$LAST_REMOTE_OUTPUT" ]; then
    show_lines "$LAST_REMOTE_TITLE" "$LAST_REMOTE_OUTPUT"
  else
    show_message 'Терминал MK61s' 'Команды в правой панели ещё не выполнялись.'
  fi
}

execute_command_line() {
  local command=$COMMAND_TEXT panel=$ACTIVE_PANEL
  [ -n "$command" ] || return
  command_history_add "$command"
  command_set_text ''
  draw_command_line
  if [ "$panel" = L ]; then run_local_command "$command"
  else run_remote_command "$command"
  fi
}

iterm_inline_images_supported() {
  # Обычный tmux не пропускает OSC 1337 без отдельной настройки passthrough.
  # В этом случае безопаснее показать Unicode-preview, чем испортить экран.
  [ -z "${TMUX:-}" ] || return 1
  [ "${TERM_PROGRAM:-}" = 'iTerm.app' ] ||
    [ "${LC_TERMINAL:-}" = 'iTerm2' ] ||
    [ -n "${ITERM_SESSION_ID:-}" ]
}

wbmp_read_mb_uint() {
  local count=${#WBMP_BYTES[@]} value=0 octet index=0
  while [ "$index" -lt 5 ]; do
    [ "$WBMP_OFFSET" -lt "$count" ] || { WBMP_ERROR='обрезанный заголовок'; return 1; }
    octet=${WBMP_BYTES[$WBMP_OFFSET]}
    WBMP_OFFSET=$((WBMP_OFFSET + 1))
    value=$((value * 128 + (octet & 127)))
    if [ "$((octet & 128))" -eq 0 ]; then WBMP_MB_VALUE=$value; return 0; fi
    index=$((index + 1))
  done
  WBMP_ERROR='слишком большое поле размера'
  return 1
}

wbmp_load() {
  local source=$1 line byte count expected used_bits padding_mask row last
  WBMP_BYTES=(); WBMP_WIDTH=0; WBMP_HEIGHT=0; WBMP_OFFSET=0
  WBMP_ROW_BYTES=0; WBMP_ERROR=
  while IFS= read -r line || [ -n "$line" ]; do
    for byte in $line; do WBMP_BYTES[${#WBMP_BYTES[@]}]=$byte; done
  done < <(od -An -v -tu1 "$source" 2>/dev/null) || {
    WBMP_ERROR='файл не читается'; return 1
  }
  count=${#WBMP_BYTES[@]}
  [ "$count" -ge 4 ] || { WBMP_ERROR='обрезанный заголовок'; return 1; }
  [ "${WBMP_BYTES[0]}" -eq 0 ] || { WBMP_ERROR='поддерживается только Type 0'; return 1; }
  [ "$((WBMP_BYTES[1] & 159))" -eq 0 ] || {
    WBMP_ERROR='некорректный fixed header'; return 1
  }
  WBMP_OFFSET=2
  wbmp_read_mb_uint || return 1; WBMP_WIDTH=$WBMP_MB_VALUE
  wbmp_read_mb_uint || return 1; WBMP_HEIGHT=$WBMP_MB_VALUE
  [ "$WBMP_WIDTH" -gt 0 ] && [ "$WBMP_HEIGHT" -gt 0 ] || {
    WBMP_ERROR='нулевой размер изображения'; return 1
  }
  WBMP_ROW_BYTES=$(((WBMP_WIDTH + 7) / 8))
  expected=$((WBMP_OFFSET + WBMP_ROW_BYTES * WBMP_HEIGHT))
  [ "$count" -eq "$expected" ] || {
    WBMP_ERROR="размер файла $count байт, ожидалось $expected"; return 1
  }
  used_bits=$((WBMP_WIDTH & 7))
  if [ "$used_bits" -ne 0 ]; then
    padding_mask=$(((1 << (8 - used_bits)) - 1)); row=0
    while [ "$row" -lt "$WBMP_HEIGHT" ]; do
      last=${WBMP_BYTES[$((WBMP_OFFSET + row * WBMP_ROW_BYTES + WBMP_ROW_BYTES - 1))]}
      [ "$((last & padding_mask))" -eq 0 ] || {
        WBMP_ERROR='ненулевые хвостовые биты строки'; return 1
      }
      row=$((row + 1))
    done
  fi
}

binary_byte() {
  printf "\\$(printf '%03o' "$(( $1 & 255 ))")"
}

binary_u16le() {
  binary_byte "$1"; binary_byte "$(( $1 >> 8 ))"
}

binary_u32le() {
  binary_byte "$1"; binary_byte "$(( $1 >> 8 ))"
  binary_byte "$(( $1 >> 16 ))"; binary_byte "$(( $1 >> 24 ))"
}

wbmp_write_bmp() {
  local output=$1 stride image_size file_size row index padding
  stride=$((((WBMP_WIDTH + 31) / 32) * 4))
  image_size=$((stride * WBMP_HEIGHT)); file_size=$((62 + image_size))
  {
    # BITMAPFILEHEADER + BITMAPINFOHEADER, 1 bpp, без сжатия.
    printf 'BM'; binary_u32le "$file_size"; binary_u32le 0; binary_u32le 62
    binary_u32le 40; binary_u32le "$WBMP_WIDTH"; binary_u32le "$WBMP_HEIGHT"
    binary_u16le 1; binary_u16le 1; binary_u32le 0; binary_u32le "$image_size"
    binary_u32le 2835; binary_u32le 2835; binary_u32le 2; binary_u32le 2
    # Палитра BGRA: WBMP уже кодирует 0=black, 1=white.
    binary_u32le 0; binary_byte 255; binary_byte 255; binary_byte 255; binary_byte 0
    # BMP хранит положительную высоту снизу вверх и выравнивает строки до 4 байт.
    row=$((WBMP_HEIGHT - 1))
    while [ "$row" -ge 0 ]; do
      index=0
      while [ "$index" -lt "$WBMP_ROW_BYTES" ]; do
        binary_byte "${WBMP_BYTES[$((WBMP_OFFSET + row * WBMP_ROW_BYTES + index))]}"
        index=$((index + 1))
      done
      padding=$((stride - WBMP_ROW_BYTES))
      while [ "$padding" -gt 0 ]; do binary_byte 0; padding=$((padding - 1)); done
      row=$((row - 1))
    done
  } > "$output"
}

wbmp_to_bmp() {
  local source=$1 output=$2
  wbmp_load "$source" || return 1
  wbmp_write_bmp "$output"
}

wbmp_dark_at() {
  local x=$1 y=$2 value mask
  if [ "$x" -lt 0 ] || [ "$x" -ge "$WBMP_WIDTH" ] ||
     [ "$y" -lt 0 ] || [ "$y" -ge "$WBMP_HEIGHT" ]; then
    WBMP_PIXEL_DARK=0
    return
  fi
  value=${WBMP_BYTES[$((WBMP_OFFSET + y * WBMP_ROW_BYTES + x / 8))]}
  mask=$((128 >> (x & 7)))
  if [ "$((value & mask))" -eq 0 ]; then WBMP_PIXEL_DARK=1
  else WBMP_PIXEL_DARK=0
  fi
}

wbmp_dark_block() {
  local start_x=$1 start_y=$2 size=$3 x y end_x end_y
  end_x=$((start_x + size)); end_y=$((start_y + size))
  WBMP_PIXEL_DARK=0; y=$start_y
  while [ "$y" -lt "$end_y" ] && [ "$y" -lt "$WBMP_HEIGHT" ]; do
    x=$start_x
    while [ "$x" -lt "$end_x" ] && [ "$x" -lt "$WBMP_WIDTH" ]; do
      wbmp_dark_at "$x" "$y"
      [ "$WBMP_PIXEL_DARK" -eq 0 ] || return 0
      x=$((x + 1))
    done
    y=$((y + 1))
  done
  return 0
}

utf8_codepoint() {
  local codepoint=$1
  # U+2800..U+28FF всегда занимает три байта UTF-8. Кодируем вручную:
  # printf из системного Bash 3.2 macOS ещё не поддерживает escape \uNNNN.
  binary_byte "$((224 | (codepoint >> 12)))"
  binary_byte "$((128 | ((codepoint >> 6) & 63)))"
  binary_byte "$((128 | (codepoint & 63)))"
}

wbmp_braille_preview() {
  local source=$1 output=$2 max_cols max_rows scale=1 needed x y columns rows
  local base_x base_y dot_x dot_y dot bit dots
  wbmp_load "$source" || return 1
  max_cols=$((UI_WIDTH - 6)); [ "$max_cols" -ge 8 ] || max_cols=8
  max_rows=$((UI_HEIGHT - 7)); [ "$max_rows" -ge 2 ] || max_rows=2
  needed=$(((WBMP_WIDTH + max_cols * 2 - 1) / (max_cols * 2)))
  [ "$needed" -le "$scale" ] || scale=$needed
  needed=$(((WBMP_HEIGHT + max_rows * 4 - 1) / (max_rows * 4)))
  [ "$needed" -le "$scale" ] || scale=$needed
  columns=$(((WBMP_WIDTH + scale * 2 - 1) / (scale * 2)))
  rows=$(((WBMP_HEIGHT + scale * 4 - 1) / (scale * 4)))
  printf '%s×%s · Braille preview%s\n\n' "$WBMP_WIDTH" "$WBMP_HEIGHT" \
    "$([ "$scale" -eq 1 ] || printf ' · 1:%s' "$scale")" > "$output"

  # Unicode Braille: слева точки 1,2,3,7; справа 4,5,6,8 — та же
  # раскладка, что в https://github.com/bolknote/XBM-Braille.
  y=0
  while [ "$y" -lt "$rows" ]; do
    x=0; base_y=$((y * scale * 4))
    while [ "$x" -lt "$columns" ]; do
      base_x=$((x * scale * 2)); dots=0; dot=0
      while [ "$dot" -lt 8 ]; do
        case "$dot" in
          0) dot_x=0; dot_y=0; bit=1 ;;
          1) dot_x=0; dot_y=1; bit=2 ;;
          2) dot_x=0; dot_y=2; bit=4 ;;
          3) dot_x=1; dot_y=0; bit=8 ;;
          4) dot_x=1; dot_y=1; bit=16 ;;
          5) dot_x=1; dot_y=2; bit=32 ;;
          6) dot_x=0; dot_y=3; bit=64 ;;
          *) dot_x=1; dot_y=3; bit=128 ;;
        esac
        # При уменьшении точка зажигается, если в соответствующем квадрате
        # есть хотя бы один тёмный пиксель: тонкие линии не исчезают.
        wbmp_dark_block "$((base_x + dot_x * scale))" \
          "$((base_y + dot_y * scale))" "$scale"
        [ "$WBMP_PIXEL_DARK" -eq 0 ] || dots=$((dots | bit))
        dot=$((dot + 1))
      done
      utf8_codepoint "$((10240 + dots))" >> "$output"
      x=$((x + 1))
    done
    printf '\n' >> "$output"
    y=$((y + 1))
  done
}

show_wbmp_iterm() {
  local title=$1 bitmap=$2 payload size inner viewer_bottom content_start content_end
  local status_row image_top image_rows image_cols row label rest left right key
  payload=$(base64 < "$bitmap" 2>/dev/null | tr -d '\r\n') || return 1
  [ -n "$payload" ] || return 1
  size=$(wc -c < "$bitmap" | tr -d '[:space:]')
  drain_pending_input
  inner=$((UI_WIDTH - 2)); viewer_bottom=$((UI_Y + UI_HEIGHT - 2))
  content_start=$((UI_Y + 1)); status_row=$((viewer_bottom - 1))
  content_end=$((status_row - 1)); image_top=$((content_start + 1))
  image_rows=$((content_end - image_top + 1)); image_cols=$((inner - 4))
  [ "$image_rows" -ge 1 ] && [ "$image_cols" -ge 1 ] || return 1

  printf '%s\033[?25l\033[?2026h\033[2J\033[H' "$C_OUTSIDE" >&9
  label=" $title "; label=$(clip_text "$label" "$((UI_WIDTH - 8))")
  rest=$((inner - ${#label})); [ "$rest" -ge 0 ] || rest=0
  left=$((rest / 2)); right=$((rest - left))
  cursor_to "$UI_Y" "$UI_X"
  printf '%s╔%s%s%s%s%s╗' "$C_BORDER" "$(repeat_char '═' "$left")" \
    "$C_MENU" "$label" "$C_BORDER" "$(repeat_char '═' "$right")" >&9
  row=$content_start
  while [ "$row" -le "$content_end" ]; do
    cursor_to "$row" "$UI_X"
    printf '%s║%s%s%s║' "$C_BORDER" "$C_PANEL" "$(repeat_char ' ' "$inner")" "$C_BORDER" >&9
    row=$((row + 1))
  done
  cursor_to "$content_start" "$((UI_X + 1))"
  printf '%s%s' "$C_STATUS" \
    "$(center_text "${WBMP_WIDTH}×${WBMP_HEIGHT} · iTerm2 inline image" "$inner")" >&9
  cursor_to "$image_top" "$((UI_X + 3))"
  printf '\033]1337;File=size=%s;width=%s;height=%s;preserveAspectRatio=1;inline=1:%s\a' \
    "$size" "$image_cols" "$image_rows" "$payload" >&9
  cursor_to "$status_row" "$UI_X"
  printf '%s║%s%s%s║' "$C_BORDER" "$C_STATUS" \
    "$(center_text 'Esc/F3 — close' "$inner")" "$C_BORDER" >&9
  cursor_to "$viewer_bottom" "$UI_X"
  printf '%s╚%s╝' "$C_BORDER" "$(repeat_char '═' "$inner")" >&9
  draw_function_bar
  printf '\033[?2026l' >&9
  while true; do
    key=$(read_key) || break
    case "$key" in esc|f3|enter|f10) break ;; esac
  done
  draw_screen
}

show_wbmp() {
  local title=$1 source=$2 bitmap="$SESSION_DIR/view.bmp" view="$SESSION_DIR/view.txt"
  WBMP_ERROR=
  if iterm_inline_images_supported && wbmp_to_bmp "$source" "$bitmap"; then
    if show_wbmp_iterm "$title" "$bitmap"; then return; fi
  elif [ -n "$WBMP_ERROR" ]; then
    ui_alert 'View' "Некорректный WBMP: $WBMP_ERROR"
    return
  fi
  if ! wbmp_braille_preview "$source" "$view"; then
    ui_alert 'View' "Некорректный WBMP: $WBMP_ERROR"
    return
  fi
  show_lines "$title" "$view"
}

show_file() {
  local panel=$ACTIVE_PANEL selected name kind source extension view="$SESSION_DIR/view.txt" binary=0
  selected=$(panel_selected "$panel"); name=$(panel_name "$panel" "$selected")
  kind=$(panel_kind "$panel" "$selected")
  [ "$name" != '..' ] && [ "$kind" != d ] || {
    STATUS_TEXT='F3 открывает файлы, а не каталоги'
    ui_alert 'View' "$STATUS_TEXT"
    return
  }
  if [ "$panel" = L ]; then source="$LOCAL_PATH/$name"
  else
    source="$SESSION_DIR/view.bin"
    STATUS_TEXT="Читаю ${name}…"; draw_status
    remote_get_file "$(remote_join "$REMOTE_PATH" "$name")" "$source" || {
      ui_alert 'View' "$STATUS_TEXT"
      return
    }
  fi
  extension=$(lowercase "$name")
  case "$extension" in
    *.wbmp|*.wbm) show_wbmp "$name" "$source"; return ;;
    *.fmk|*.mod) binary=1 ;;
  esac
  if [ "$binary" -eq 0 ] && { [ ! -s "$source" ] || LC_ALL=C grep -Iq . "$source" 2>/dev/null; }; then
    sed -n '1,400p' "$source" > "$view"
  else
    if command -v hexdump >/dev/null 2>&1; then hexdump -C "$source" > "$view"
    else od -Ax -tx1 -v "$source" > "$view"
    fi
  fi
  show_lines "$name" "$view"
}

toggle_mark() {
  local panel=$ACTIVE_PANEL selected old page mark name
  selected=$(panel_selected "$panel"); name=$(panel_name "$panel" "$selected")
  [ "$name" != '..' ] || return
  page=$(panel_page "$panel")
  mark=$(panel_mark "$panel" "$selected")
  if [ "$mark" -eq 1 ]; then mark=0; else mark=1; fi
  set_panel_mark "$panel" "$selected" "$mark"
  panel_geometry "$panel"
  draw_panel_slot "$panel" "$((selected - page))"
  draw_panel_info "$panel"
  move_selection down
}

open_selected() {
  local panel=$ACTIVE_PANEL selected name kind target
  selected=$(panel_selected "$panel"); name=$(panel_name "$panel" "$selected")
  kind=$(panel_kind "$panel" "$selected")
  if [ "$kind" != d ]; then show_file; return; fi
  if [ "$panel" = L ]; then
    if [ "$name" = '..' ]; then target=${LOCAL_PATH%/*}; [ -n "$target" ] || target=/
    else target="$LOCAL_PATH/$name"
    fi
    if [ -d "$target" ]; then LOCAL_PATH=$(cd "$target" && pwd -P); L_SELECTED=0; load_local_panel
    else STATUS_TEXT="Нет каталога $target"
    fi
  else
    if [ "$name" = '..' ]; then target=$(remote_parent "$REMOTE_PATH")
    else target=$(remote_join "$REMOTE_PATH" "$name")
    fi
    REMOTE_PATH=$(remote_normalize / "$target")
    R_SELECTED=0
    if ! load_remote_panel; then REMOTE_PATH=$(remote_parent "$REMOTE_PATH"); load_remote_panel || true; fi
  fi
  STATUS_TEXT='Каталог открыт'
  save_config
  draw_screen
}

go_parent() {
  local selected
  if [ "$ACTIVE_PANEL" = L ]; then
    [ "$LOCAL_PATH" = / ] || { LOCAL_PATH=${LOCAL_PATH%/*}; [ -n "$LOCAL_PATH" ] || LOCAL_PATH=/; load_local_panel; }
  else
    [ "$REMOTE_PATH" = / ] || { REMOTE_PATH=$(remote_parent "$REMOTE_PATH"); load_remote_panel || true; }
  fi
  selected=$(panel_selected "$ACTIVE_PANEL")
  STATUS_TEXT='Родительский каталог'
  save_config
  draw_screen
}

progress_draw() {
  local message=$1 current=$2 total=$3 percent width filled empty bar_x
  if [ "$total" -gt 0 ]; then percent=$((current * 100 / total)); else percent=100; fi
  [ "$percent" -le 100 ] || percent=100
  if [ "$PROGRESS_ACTIVE" -eq 0 ]; then
    draw_dialog_frame 'Copy' 66 9
    PROGRESS_ACTIVE=1
  fi
  width=$((DIALOG_WIDTH - 10)); [ "$width" -ge 10 ] || width=10
  filled=$((width * percent / 100)); empty=$((width - filled))
  cursor_to "$((DIALOG_Y + 2))" "$((DIALOG_X + 3))"
  printf '%s%s' "$C_DIALOG" "$(center_text "$message" "$((DIALOG_WIDTH - 6))")" >&9
  bar_x=$((DIALOG_X + 4))
  cursor_to "$((DIALOG_Y + 4))" "$bar_x"
  printf '%s[' "$C_DIALOG" >&9
  printf '%s%s' "$C_DIALOG_BUTTON_ACTIVE" "$(repeat_char ' ' "$filled")" >&9
  printf '%s%s' "$C_DIALOG_INPUT" "$(repeat_char ' ' "$empty")" >&9
  printf '%s]' "$C_DIALOG" >&9
  cursor_to "$((DIALOG_Y + 6))" "$((DIALOG_X + 3))"
  printf '%s%s' "$C_DIALOG" "$(center_text "$percent%" "$((DIALOG_WIDTH - 6))")" >&9
}

execute_plan() {
  local direction=$1 index=0 completed=0 kind source destination size part parent total_items
  total_items=${#PLAN_KINDS[@]}
  while [ "$index" -lt "$total_items" ]; do
    kind=${PLAN_KINDS[$index]}; source=${PLAN_SOURCES[$index]}
    destination=${PLAN_DESTINATIONS[$index]}; size=${PLAN_SIZES[$index]}
    progress_draw "Копирую $((index + 1))/$total_items: ${source##*/}" "$completed" "$PLAN_TOTAL"
    if [ "$direction" = L2R ]; then
      if [ "$kind" = d ]; then
        remote_mkdir "$destination" || return 1
      else
        remote_put_file "$source" "$destination" || return 1
        completed=$((completed + size))
      fi
    else
      if [ "$kind" = d ]; then
        mkdir -p "$destination" 2>/dev/null || { STATUS_TEXT="Не удалось создать $destination"; return 1; }
      else
        parent=${destination%/*}; [ -n "$parent" ] || parent=/
        mkdir -p "$parent" 2>/dev/null || { STATUS_TEXT="Не удалось создать $parent"; return 1; }
        part="$SESSION_DIR/receive.$index"
        remote_get_file "$source" "$part" || return 1
        cp "$part" "$destination" 2>/dev/null || { STATUS_TEXT="Не удалось записать $destination"; return 1; }
        completed=$((completed + size))
      fi
    fi
    index=$((index + 1))
  done
  progress_draw 'Копирование завершено' "$PLAN_TOTAL" "$PLAN_TOTAL"
  return 0
}

copy_selected() {
  local panel=$ACTIVE_PANEL index name kind size reason source destination count target error
  collect_selected_indices "$panel"
  count=${#SELECTED_INDICES[@]}
  [ "$count" -gt 0 ] || {
    STATUS_TEXT='Выберите файл или каталог'
    ui_alert 'Copy' "$STATUS_TEXT"
    return
  }
  if [ "$panel" = L ]; then
    for index in "${SELECTED_INDICES[@]}"; do
      reason=$(panel_reason L "$index")
      if [ -n "$reason" ]; then
        name=$(panel_name L "$index")
        STATUS_TEXT="Нельзя копировать $name: $reason"
        ui_alert 'Copy' "$STATUS_TEXT"
        return
      fi
    done
  fi

  if [ "$panel" = L ]; then
    if [ "$count" -eq 1 ]; then
      index=${SELECTED_INDICES[0]}; name=$(panel_name L "$index")
      destination=$(remote_join "$REMOTE_PATH" "$name")
    else
      destination=$REMOTE_PATH
    fi
    if ! dialog_text_input 'Copy' "Copy $count item(s) to MK61s:" "$destination" 'Copy'; then
      STATUS_TEXT='Копирование отменено'; draw_status; return
    fi
    target=$(remote_normalize "$REMOTE_PATH" "$UI_VALUE")
    plan_reset
    if [ "$count" -eq 1 ]; then
      index=${SELECTED_INDICES[0]}; name=$(panel_name L "$index")
      source="$LOCAL_PATH/$name"
      plan_local_tree "$source" "$target" || true
    else
      for index in "${SELECTED_INDICES[@]}"; do
        name=$(panel_name L "$index"); source="$LOCAL_PATH/$name"
        destination=$(remote_join "$target" "$name")
        plan_local_tree "$source" "$destination" || break
      done
    fi
    if [ -n "$PLAN_ERROR" ]; then
      STATUS_TEXT="Нельзя копировать: $PLAN_ERROR"; ui_alert 'Copy' "$STATUS_TEXT"; return
    fi
    PROGRESS_ACTIVE=0
    if execute_plan L2R; then
      STATUS_TEXT="Скопировано на MK61s: $count"; clear_panel_marks L
    else
      error=$STATUS_TEXT; PROGRESS_ACTIVE=0; draw_screen; ui_alert 'Copy' "$error"; return
    fi
  else
    if [ "$count" -eq 1 ]; then
      index=${SELECTED_INDICES[0]}; name=$(panel_name R "$index")
      destination="$LOCAL_PATH/$name"
    else
      destination=$LOCAL_PATH
    fi
    if ! dialog_text_input 'Copy' "Copy $count item(s) to computer:" "$destination" 'Copy'; then
      STATUS_TEXT='Копирование отменено'; draw_status; return
    fi
    case "$UI_VALUE" in /*) target=$UI_VALUE ;; *) target="$LOCAL_PATH/$UI_VALUE" ;; esac
    plan_reset
    if [ "$count" -eq 1 ]; then
      index=${SELECTED_INDICES[0]}; name=$(panel_name R "$index")
      source=$(remote_join "$REMOTE_PATH" "$name")
      kind=$(panel_kind R "$index"); size=$(panel_size R "$index")
      plan_remote_tree "$source" "$target" "$kind" "$size" || true
    else
      for index in "${SELECTED_INDICES[@]}"; do
        name=$(panel_name R "$index"); source=$(remote_join "$REMOTE_PATH" "$name")
        destination="$target/$name"; kind=$(panel_kind R "$index"); size=$(panel_size R "$index")
        plan_remote_tree "$source" "$destination" "$kind" "$size" || break
      done
    fi
    if [ -n "$PLAN_ERROR" ]; then STATUS_TEXT="Нельзя копировать: $PLAN_ERROR"; ui_alert 'Copy' "$STATUS_TEXT"; return; fi
    PROGRESS_ACTIVE=0
    if execute_plan R2L; then
      STATUS_TEXT="Скопировано на компьютер: $count"; clear_panel_marks R
    else
      error=$STATUS_TEXT; PROGRESS_ACTIVE=0; draw_screen; ui_alert 'Copy' "$error"; return
    fi
  fi
  PROGRESS_ACTIVE=0
  refresh_panels
  draw_screen
}

rename_selected() {
  local panel=$ACTIVE_PANEL selected name source destination
  selected=$(panel_selected "$panel"); name=$(panel_name "$panel" "$selected")
  [ "$name" != '..' ] || { STATUS_TEXT='Нельзя переименовать ..'; ui_alert 'Rename/Move' "$STATUS_TEXT"; return; }
  if [ "$panel" = L ]; then
    source="$LOCAL_PATH/$name"; destination=$source
    if ! dialog_text_input 'Rename/Move' 'Rename or move to:' "$destination" 'Move'; then
      STATUS_TEXT='Переименование отменено'; draw_status; return
    fi
    case "$UI_VALUE" in /*) destination=$UI_VALUE ;; *) destination="$LOCAL_PATH/$UI_VALUE" ;; esac
    if mv "$source" "$destination" 2>/dev/null; then STATUS_TEXT="Перемещено: $name"
    else STATUS_TEXT="Не удалось переместить $name"; ui_alert 'Rename/Move' "$STATUS_TEXT"; return
    fi
    load_local_panel
  else
    source=$(remote_join "$REMOTE_PATH" "$name")
    if ! dialog_text_input 'Rename/Move' 'Rename or move on MK61s to:' "$source" 'Move'; then
      STATUS_TEXT='Переименование отменено'; draw_status; return
    fi
    destination=$(remote_normalize "$REMOTE_PATH" "$UI_VALUE")
    if remote_move "$source" "$destination"; then STATUS_TEXT="Перемещено: $name"
    else ui_alert 'Rename/Move' "$STATUS_TEXT"; return
    fi
    load_remote_panel || true
  fi
  draw_screen
}

make_directory() {
  local panel=$ACTIVE_PANEL destination
  if ! dialog_text_input 'Make directory' 'Directory name:' 'New directory' 'Make'; then
    STATUS_TEXT='Создание отменено'; draw_status; return
  fi
  [ -n "$UI_VALUE" ] || { STATUS_TEXT='Имя каталога не задано'; ui_alert 'Make directory' "$STATUS_TEXT"; return; }
  if [ "$panel" = L ]; then
    case "$UI_VALUE" in /*) destination=$UI_VALUE ;; *) destination="$LOCAL_PATH/$UI_VALUE" ;; esac
    if mkdir "$destination" 2>/dev/null; then STATUS_TEXT="Создан $destination"; load_local_panel
    else STATUS_TEXT="Не удалось создать $destination"; ui_alert 'Make directory' "$STATUS_TEXT"; return
    fi
  else
    destination=$(remote_normalize "$REMOTE_PATH" "$UI_VALUE")
    if remote_mkdir "$destination"; then STATUS_TEXT="Создан $destination"; load_remote_panel || true
    else ui_alert 'Make directory' "$STATUS_TEXT"; return
    fi
  fi
  draw_screen
}

delete_selected() {
  local panel=$ACTIVE_PANEL count index name path failed=0
  collect_selected_indices "$panel"; count=${#SELECTED_INDICES[@]}
  [ "$count" -gt 0 ] || { STATUS_TEXT='Выберите объект для удаления'; ui_alert 'Delete' "$STATUS_TEXT"; return; }
  ui_confirm "Удалить безвозвратно: $count объект(ов)?"
  [ "$UI_CONFIRMED" -eq 1 ] || { STATUS_TEXT='Удаление отменено'; draw_status; return; }
  for index in "${SELECTED_INDICES[@]}"; do
    name=$(panel_name "$panel" "$index")
    if [ "$panel" = L ]; then
      path="$LOCAL_PATH/$name"
      [ "$path" != / ] && rm -rf "$path" 2>/dev/null || failed=1
    else
      path=$(remote_join "$REMOTE_PATH" "$name")
      remote_delete "$path" || failed=1
    fi
  done
  if [ "$failed" -eq 0 ]; then STATUS_TEXT="Удалено: $count"; else STATUS_TEXT='Часть объектов удалить не удалось'; fi
  refresh_panels
  draw_screen
}

device_info() {
  local file="$SESSION_DIR/device-info.txt" line count=0
  if [ -n "$MOCK_ROOT" ]; then
    { printf 'Режим: тестовый каталог\nПуть: %s\n\n' "$MOCK_ROOT"; df -h "$MOCK_ROOT" 2>/dev/null; } > "$file"
  else
    : > "$file"
    remote_send df || { STATUS_TEXT='Не удалось отправить df'; draw_status; return; }
    remote_send 'ls "/"' || return
    while [ "$count" -lt 10000 ]; do
      serial_read_line 10 || break
      line=$SERIAL_LINE
      case "$line" in
        Flash:\ *|Nodes:\ *|Visible:\ *|FAT12\ cluster:\ *|Settings:\ *) printf '%s\n' "$line" >> "$file" ;;
        *' entry.'|*' entries.') break ;;
      esac
      count=$((count + 1))
    done
    { printf 'Порт: %s\n\n' "$PORT"; cat "$file"; } > "$SESSION_DIR/device-info.full"
    file="$SESSION_DIR/device-info.full"
  fi
  show_lines 'Устройство' "$file"
}

main_loop() {
  local key
  while true; do
    if [ "$RESIZE_PENDING" -eq 1 ]; then RESIZE_PENDING=0; draw_screen; fi
    key=$(read_key) || break
    case "$key" in
      up)
        if [ -n "$COMMAND_TEXT" ]; then command_history_move previous
        else move_selection up
        fi
        ;;
      down)
        if [ -n "$COMMAND_TEXT" ]; then command_history_move next
        else move_selection down
        fi
        ;;
      left)
        if [ -n "$COMMAND_TEXT" ]; then [ "$COMMAND_CURSOR" -gt 0 ] && COMMAND_CURSOR=$((COMMAND_CURSOR - 1))
        else move_selection left
        fi
        ;;
      right)
        if [ -n "$COMMAND_TEXT" ]; then [ "$COMMAND_CURSOR" -lt "${#COMMAND_TEXT}" ] && COMMAND_CURSOR=$((COMMAND_CURSOR + 1))
        else move_selection right
        fi
        ;;
      home)
        if [ -n "$COMMAND_TEXT" ]; then COMMAND_CURSOR=0; else move_selection home; fi
        ;;
      end)
        if [ -n "$COMMAND_TEXT" ]; then COMMAND_CURSOR=${#COMMAND_TEXT}; else move_selection end; fi
        ;;
      pgup|pgdn) [ -n "$COMMAND_TEXT" ] || move_selection "$key" ;;
      tab) switch_panel ;;
      enter)
        if [ -n "$COMMAND_TEXT" ]; then execute_command_line; else open_selected; fi
        ;;
      backspace)
        if [ -n "$COMMAND_TEXT" ]; then command_backspace; else go_parent; fi
        ;;
      delete) [ -n "$COMMAND_TEXT" ] && command_delete ;;
      space)
        if [ -n "$COMMAND_TEXT" ]; then command_insert_text ' '; else toggle_mark; fi
        ;;
      insert) toggle_mark ;;
      refresh) STATUS_TEXT='Обновляю…'; draw_status; refresh_panels; STATUS_TEXT='Панели обновлены'; draw_screen ;;
      console) show_terminal_output ;;
      $'\020') command_history_move previous ;;
      $'\016') command_history_move next ;;
      $'\025') command_set_text ''; command_reset_history_navigation ;;
      f1) show_help ;;
      f2|f4) ;;
      f3) show_file ;;
      f5) copy_selected ;;
      f6) rename_selected ;;
      f7) make_directory ;;
      f8) delete_selected ;;
      f9) device_info ;;
      f10) break ;;
      esc) command_set_text ''; command_reset_history_navigation ;;
      *)
        case "$key" in [[:cntrl:]]) ;; *) command_insert_text "$key" ;; esac
        ;;
    esac
    draw_command_line
  done
}

parse_args() {
  while [ "$#" -gt 0 ]; do
    case "$1" in
      --port) [ "$#" -ge 2 ] || die 'после --port нужен порт'; PORT=$2; shift 2 ;;
      --local) [ "$#" -ge 2 ] || die 'после --local нужен каталог'; LOCAL_PATH=$2; shift 2 ;;
      --mock) [ "$#" -ge 2 ] || die 'после --mock нужен каталог'; MOCK_ROOT=$2; shift 2 ;;
      --classify) [ "$#" -ge 2 ] || die 'после --classify нужен файл'; CLASSIFY_ONLY=$2; shift 2 ;;
      -h|--help) usage; exit 0 ;;
      *) die "неизвестный параметр: $1" ;;
    esac
  done
}

main() {
  local reason kind prompted_port
  load_config
  parse_args "$@"
  if [ -n "$CLASSIFY_ONLY" ]; then
    if [ -L "$CLASSIFY_ONLY" ]; then kind=l
    elif [ -d "$CLASSIFY_ONLY" ]; then kind=d
    elif [ -f "$CLASSIFY_ONLY" ]; then kind=f
    else kind=o
    fi
    reason=$(unsupported_reason "$CLASSIFY_ONLY" "$kind")
    if [ -n "$reason" ]; then printf 'unsupported: %s\n' "$reason"; return 1; fi
    printf 'supported\n'; return 0
  fi

  [ -d "$LOCAL_PATH" ] || die "нет локального каталога: $LOCAL_PATH"
  LOCAL_PATH=$(cd "$LOCAL_PATH" && pwd -P)
  if [ -n "$MOCK_ROOT" ]; then
    [ -d "$MOCK_ROOT" ] || die "нет тестового каталога: $MOCK_ROOT"
    MOCK_ROOT=$(cd "$MOCK_ROOT" && pwd -P)
  fi
  SESSION_DIR=$(mktemp -d "${TMPDIR:-/tmp}/mkc.XXXXXX") || die 'не удалось создать временный каталог'
  shopt -s nullglob dotglob

  [ -t 0 ] || die 'нужен интерактивный терминал'
  # stdin остаётся свободным: монитор подключён к отдельным FIFO. Дубликат
  # управляющего PTY работает и в обычном shell, и в sandbox/expect, где
  # открытие /dev/tty может быть запрещено.
  exec 9<&0 || die 'нужен интерактивный терминал'
  TTY_FD=9
  if [ -z "$MOCK_ROOT" ] && [ -z "$PORT" ] && ! detect_port; then
    printf 'MKC: устройство 0483:5740 не найдено. Укажите последовательный порт: ' >&9
    IFS= read -r prompted_port <&9 || prompted_port=
    PORT=$prompted_port
  fi
  [ -n "$MOCK_ROOT" ] || [ -n "$PORT" ] || die 'порт не указан'
  start_monitor || die "не удалось открыть ${PORT:-устройство}"

  TTY_SAVED=$(stty -g <&9) || die 'не удалось настроить терминал'
  # Оставляем сигналы (Ctrl-C), но отключаем extended input: иначе Ctrl-O
  # перехватывается tty как discard вместо команды MKC.
  stty -echo -icanon -iexten discard undef min 1 time 0 <&9
  printf '\033[?1049h\033[?25l' >&9
  SCREEN_ACTIVE=1
  term_size
  printf '%s\033[2J\033[H' "$C_OUTSIDE" >&9
  cursor_to "$UI_Y" "$UI_X"
  printf '%s%s' "$C_PANEL" "$(fit_text ' MKC · читаю каталоги…' "$UI_WIDTH")" >&9
  refresh_panels
  save_config
  draw_screen
  main_loop
}

if [ "${MKC_SOURCE_ONLY:-0}" != 1 ]; then
  main "$@"
fi

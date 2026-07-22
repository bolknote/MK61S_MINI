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
PROJECT_ROOT=$(cd "$SCRIPT_DIR/.." && pwd)
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

usage() {
  cat <<'EOF'
MKC — Norton Commander для файлов MK61s

Usage:
  tools/mkc.sh [--port PORT] [--local DIRECTORY]
  tools/mkc.sh --mock DIRECTORY [--local DIRECTORY]
  tools/mkc.sh --classify FILE

Keys:
  Tab       switch panel        Enter     open directory
  Space     mark item           F1        help
  F3        view                F5        copy
  F6        rename/move         F7        mkdir
  F8        delete              F9        device info
  F10       quit                Ctrl-R    refresh

Supported device files: .m61, .foc, .tbi, .txt, .state.txt, .fmk, .wbmp
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
  local path=$1 kind=$2 name base lower upper bytes size limit
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
    printf '# Generated by tools/mkc.sh.\n'
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
    chunk=${hex:$((offset * 2)):192}
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
  local source=$1 destination=$2 kind reason child name size
  if [ -L "$source" ]; then kind=l
  elif [ -d "$source" ]; then kind=d
  elif [ -f "$source" ]; then kind=f
  else kind=o
  fi
  reason=$(unsupported_reason "$source" "$kind")
  if [ -n "$reason" ]; then PLAN_ERROR="${source##*/}: $reason"; return 1; fi
  if [ "$kind" = f ]; then
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

draw_status() {
  local style=$C_COMMAND text
  case "$STATUS_TEXT" in *ошиб*|*Ошибка*|*Нельзя*|*нельзя*|*Таймаут*|*не\ удалось*|*Нет\ ответа*) style=$C_COMMAND_ERROR ;; esac
  if [ -n "$STATUS_TEXT" ]; then text="MKC> $STATUS_TEXT"; else text='MKC>_'; fi
  cursor_to "$COMMAND_ROW" "$UI_X"
  printf '%s%s' "$style" "$(fit_text "$text" "$UI_WIDTH")" >&9
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
  draw_status
  draw_function_bar
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
  printf '\033[?2026l' >&9
}

read_escape_tail() {
  local rest= char count=0
  stty -echo -icanon min 0 time 1 <&9 2>/dev/null || true
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
  stty -echo -icanon min 1 time 0 <&9 2>/dev/null || true
  printf '%s' "$rest"
}

drain_pending_input() {
  local char count=0
  stty -echo -icanon min 0 time 0 <&9 2>/dev/null || true
  while [ "$count" -lt 64 ]; do
    char=$(dd bs=1 count=1 <&9 2>/dev/null) || true
    [ -n "$char" ] || break
    count=$((count + 1))
  done
  stty -echo -icanon min 1 time 0 <&9 2>/dev/null || true
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
    printf '%s\033[?2026h\033[2J\033[H' "$C_OUTSIDE" >&9
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
F3           встроенный просмотр (без редактора)
F5           копировать между компьютером и калькулятором
F6           переименовать или переместить в активной панели
F7           создать каталог
F8           удалить с подтверждением
F9           сведения о памяти калькулятора
F10          выход
Ctrl-R       обновить обе панели

Серые файлы имеют неподдерживаемый формат, имя или размер. Их можно
переименовать через F6, просмотреть через F3 и удалить через F8, но F5
на калькулятор для них заблокирован.'
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
  case "$extension" in *.wbmp|*.wbm|*.fmk) binary=1 ;; esac
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
      up|down|left|right|home|end|pgup|pgdn) move_selection "$key" ;;
      tab) switch_panel ;;
      enter) open_selected ;;
      backspace) go_parent ;;
      space|insert) toggle_mark ;;
      refresh) STATUS_TEXT='Обновляю…'; draw_status; refresh_panels; STATUS_TEXT='Панели обновлены'; draw_screen ;;
      f1) show_help ;;
      f2|f4) ;;
      f3) show_file ;;
      f5) copy_selected ;;
      f6) rename_selected ;;
      f7) make_directory ;;
      f8) delete_selected ;;
      f9) device_info ;;
      f10) break ;;
      esc) STATUS_TEXT='F10 — выход'; draw_status ;;
    esac
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
  stty -echo -icanon min 1 time 0 <&9
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

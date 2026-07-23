#!/usr/bin/env bash

# Интерактивный сборщик и загрузчик прошивки для MK61S_MINI.
# Совместим с Bash 3.2 — системной версией Bash в старых выпусках macOS.

set -u

# Bash считает и извлекает символы с учётом текущей локали. В чистом окружении
# macOS по умолчанию использует ASCII, из-за чего русский интерфейс может быть
# разрезан посреди последовательности UTF-8. Сохраняем существующую локаль UTF-8,
# а иначе выбираем первое переносимое обозначение, доступное на этом хосте.
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

ARDUINO_CLI=${MK61_ARDUINO_CLI:-arduino-cli}
BUILD_ROOT=${MK61_BUILD_ROOT:-"$PROJECT_ROOT/.build/mk61-firmware"}
OUTPUT_DIR=${MK61_OUTPUT_DIR:-"$PROJECT_ROOT/binary"}
CONFIG_FILE=${MK61_CONFIG_FILE:-"$PROJECT_ROOT/.mk61-firmware.conf"}
LEGACY_SELECTION_FILE="$BUILD_ROOT/selected-profile"
LAST_LOG="$BUILD_ROOT/last.log"

STM32_CORE_VERSION=2.12.0
STM32_PACKAGE_URL=https://github.com/stm32duino/BoardManagerFiles/raw/main/package_stmicroelectronics_index.json
FQBN_F411='STMicroelectronics:stm32:GenF4:pnum=BLACKPILL_F411CE,upload_method=dfuMethod,xserial=generic,usb=CDCgen,opt=osstd'
FQBN_F401='STMicroelectronics:stm32:GenF4:pnum=BLACKPILL_F401CC,upload_method=dfuMethod,xserial=generic,usb=CDCgen,opt=osstd'

PROFILE=
HARDWARE_PLATFORM=
SCREEN_KIND=
MCU=f411
CLI_PROFILE=0
CLI_MCU=0
ENABLE_FOCAL=1
ENABLE_TINYBASIC=1
ENABLE_WBMP_VIEWER=1
ENABLE_USB_SCREEN=0
ENABLE_EXTENDED_FONT_SETTINGS=0
ENABLE_USER_EXPLORER=1
ENABLE_CORE_MATH=0
DEVICE_STATUS='не проверялось'
DFU_UTIL_PATH=
DFU_STATUS='не найден'
DETECTED_PORT=
DETECTED_VERSION=
UI_KIND=native
UI_CMD=
INTERACTIVE=0
ACTIVE_PID=
DFU_CMD=()
NATIVE_SCREEN_ACTIVE=0
NATIVE_COLS=80
NATIVE_ROWS=24
NATIVE_WIDTH=78
NATIVE_TEXT_WIDTH=74
NATIVE_MARGIN=
NATIVE_LIST_FIRST_ROW=1
NATIVE_VIEW_KIND=
NATIVE_PROGRESS_TITLE=

C_RESET=$'\033[0;37;44m'
C_BORDER=$'\033[1;36;44m'
C_BORDER_DIM=$'\033[0;36;44m'
C_SELECTED=$'\033[30;46m'
C_GREEN=$'\033[1;33;44m'
C_YELLOW=$'\033[1;33;44m'
C_MUTED=$'\033[0;36;44m'
C_RED=$'\033[1;31;44m'
C_BLUE=$'\033[0;36;44m'
C_MAGENTA=$'\033[1;36;44m'
C_WHITE=$'\033[1;37;44m'
C_OUTSIDE=$'\033[0m'

if [ "${MK61_COLOR:-always}" = never ] || \
    { [ "${MK61_COLOR:-always}" = auto ] && [ -n "${NO_COLOR:-}" ]; }; then
  C_RESET=
  C_BORDER=
  C_BORDER_DIM=
  C_SELECTED=
  C_GREEN=
  C_YELLOW=
  C_MUTED=
  C_RED=
  C_BLUE=
  C_MAGENTA=
  C_WHITE=
fi

cleanup() {
  if [ -n "$ACTIVE_PID" ] && kill -0 "$ACTIVE_PID" 2>/dev/null; then
    kill "$ACTIVE_PID" 2>/dev/null || true
  fi
  native_screen_leave
}
trap cleanup EXIT
trap 'exit 130' INT
trap 'exit 143' TERM

usage() {
  cat <<'EOF'
MK61s firmware builder and DFU uploader

Usage:
  tools/mk61-firmware.cmd                         interactive menu
  tools/mk61-firmware.cmd --mcu MCU --profile ID --build
  tools/mk61-firmware.cmd --mcu MCU --profile ID --upload
  tools/mk61-firmware.cmd --mcu f401 --profile ID --install-apps
  tools/mk61-firmware.cmd --detect                detect MK61s/STM32 DFU
  tools/mk61-firmware.cmd --setup                 install pinned Arduino dependencies
  tools/mk61-firmware.cmd --list-profiles         print supported profiles
  tools/mk61-firmware.cmd --show-config           print saved selection and flags

Options:
  --mcu MCU       f411 (512 KiB Flash) or f401 (256 KiB Flash + System APP)
  --profile ID    mini-v3-a00, mini-v3-a02, mini-v2-a00, mini-v2-a02,
                  classic-v2, classic-v3, or 40th
  --plain         use the built-in shell UI even when dialog/whiptail exists
  -h, --help      show this help

Environment overrides:
  MK61_ARDUINO_CLI, MK61_DFU_UTIL, MK61_BUILD_ROOT, MK61_OUTPUT_DIR,
  MK61_CONFIG_FILE, MK61_C5_MOUNT, MK61_APP_MANIFESTS, MK61_UI,
  MK61_COLOR (always, auto, or never)

Interactive selections are stored in .mk61-firmware.conf (git-ignored).
EOF
}

mcu_valid() {
  case "${1:-}" in f411|f401) return 0 ;; esac
  return 1
}

mcu_label() {
  case "${1:-}" in
    f411) printf '%s' 'STM32F411CE · 512 KiB Flash' ;;
    f401) printf '%s' 'STM32F401CC · 256 KiB Flash · APP в C5' ;;
    *) printf '%s' 'не выбран' ;;
  esac
}

fqbn_for_mcu() {
  case "${1:-}" in
    f411) printf '%s' "$FQBN_F411" ;;
    f401) printf '%s' "$FQBN_F401" ;;
    *) return 1 ;;
  esac
}

profile_valid() {
  case "${1:-}" in
    mini-v3-a00|mini-v3-a02|mini-v2-a00|mini-v2-a02|classic-v2|classic-v3|40th)
      return 0
      ;;
  esac
  return 1
}

platform_valid() {
  case "${1:-}" in
    mini-v3|mini-v2|classic-v2|classic-v3|40th) return 0 ;;
  esac
  return 1
}

screen_valid() {
  case "${1:-}" in
    lcd1602-a00|lcd1602-a02|uc1609) return 0 ;;
  esac
  return 1
}

platform_label() {
  case "${1:-}" in
    mini-v3)    printf '%s' 'mini V3' ;;
    mini-v2)    printf '%s' 'mini V2' ;;
    classic-v2) printf '%s' 'Classic V2' ;;
    classic-v3) printf '%s' 'Classic V3' ;;
    40th)       printf '%s' 'MK61s 40th' ;;
    *)          printf '%s' 'не выбрана' ;;
  esac
}

screen_label() {
  case "${1:-}" in
    lcd1602-a00) printf '%s' 'LCD1602 · CGROM A00' ;;
    lcd1602-a02) printf '%s' 'LCD1602 · CGROM A02' ;;
    uc1609)      printf '%s' 'UC1609 · 192×64' ;;
    *)           printf '%s' 'не выбран' ;;
  esac
}

hardware_compatible() {
  case "${1:-}:${2:-}" in
    mini-v3:lcd1602-a00|mini-v3:lcd1602-a02|mini-v2:lcd1602-a00|mini-v2:lcd1602-a02|\
    classic-v2:uc1609|classic-v3:uc1609|40th:uc1609)
      return 0
      ;;
  esac
  return 1
}

profile_from_hardware() {
  case "${1:-}:${2:-}" in
    mini-v3:lcd1602-a00) printf '%s' mini-v3-a00 ;;
    mini-v3:lcd1602-a02) printf '%s' mini-v3-a02 ;;
    mini-v2:lcd1602-a00) printf '%s' mini-v2-a00 ;;
    mini-v2:lcd1602-a02) printf '%s' mini-v2-a02 ;;
    classic-v2:uc1609)   printf '%s' classic-v2 ;;
    classic-v3:uc1609)   printf '%s' classic-v3 ;;
    40th:uc1609)         printf '%s' 40th ;;
    *) return 1 ;;
  esac
}

hardware_from_profile() {
  case "${1:-}" in
    mini-v3-a00) HARDWARE_PLATFORM=mini-v3; SCREEN_KIND=lcd1602-a00 ;;
    mini-v3-a02) HARDWARE_PLATFORM=mini-v3; SCREEN_KIND=lcd1602-a02 ;;
    mini-v2-a00) HARDWARE_PLATFORM=mini-v2; SCREEN_KIND=lcd1602-a00 ;;
    mini-v2-a02) HARDWARE_PLATFORM=mini-v2; SCREEN_KIND=lcd1602-a02 ;;
    classic-v2)  HARDWARE_PLATFORM=classic-v2; SCREEN_KIND=uc1609 ;;
    classic-v3)  HARDWARE_PLATFORM=classic-v3; SCREEN_KIND=uc1609 ;;
    40th)        HARDWARE_PLATFORM=40th; SCREEN_KIND=uc1609 ;;
    *) return 1 ;;
  esac
}

sync_profile_from_hardware() {
  PROFILE=$(profile_from_hardware "$HARDWARE_PLATFORM" "$SCREEN_KIND") || PROFILE=
}

profile_label() {
  case "$1" in
    mini-v3-a00) printf '%s' 'mini V3 · LCD1602 A00' ;;
    mini-v3-a02) printf '%s' 'mini V3 · LCD1602 A02' ;;
    mini-v2-a00) printf '%s' 'mini V2 · LCD1602 A00' ;;
    mini-v2-a02) printf '%s' 'mini V2 · LCD1602 A02' ;;
    classic-v2)  printf '%s' 'Classic V2 · UC1609 192×64' ;;
    classic-v3)  printf '%s' 'Classic V3 · UC1609 192×64' ;;
    40th)        printf '%s' 'MK61s 40th · UC1609 192×64' ;;
    *)           printf '%s' 'не выбрано' ;;
  esac
}

profile_flags() {
  case "$1" in
    mini-v3-a00) printf '%s' '-DMK61_LCD1602_A00' ;;
    mini-v3-a02) printf '%s' '-DMK61_LCD1602_A02' ;;
    mini-v2-a00) printf '%s' '-DREVISION_V2 -DMK61_LCD1602_A00' ;;
    mini-v2-a02) printf '%s' '-DREVISION_V2 -DMK61_LCD1602_A02' ;;
    classic-v2)  printf '%s' '-DMK61_BOARD_CLASSIC_V2' ;;
    classic-v3)  printf '%s' '-DMK61_BOARD_CLASSIC_V3' ;;
    40th)        printf '%s' '-DMK61_BOARD_40TH' ;;
    *) return 1 ;;
  esac
}

profile_artifact_name() {
  local suffix=${2:-$MCU}
  mcu_valid "$suffix" || return 1
  case "$1" in
    mini-v3-a00) printf 'mk61s-M-mini-v3-lcd1602-a00-%s.bin' "$suffix" ;;
    mini-v3-a02) printf 'mk61s-M-mini-v3-lcd1602-a02-%s.bin' "$suffix" ;;
    mini-v2-a00) printf 'mk61s-M-mini-v2-lcd1602-a00-%s.bin' "$suffix" ;;
    mini-v2-a02) printf 'mk61s-M-mini-v2-lcd1602-a02-%s.bin' "$suffix" ;;
    classic-v2)  printf 'mk61s-M-classic-v2-uc1609-%s.bin' "$suffix" ;;
    classic-v3)  printf 'mk61s-M-classic-v3-uc1609-%s.bin' "$suffix" ;;
    40th)        printf 'mk61s-M-40th-%s.bin' "$suffix" ;;
    *) return 1 ;;
  esac
}

profile_bundle_dir() {
  local artifact
  artifact=$(profile_artifact_name "$1" f401) || return 1
  printf '%s/%s' "$OUTPUT_DIR" "${artifact%.bin}"
}

profile_artifact_path() {
  local artifact
  artifact=$(profile_artifact_name "$1" "$MCU") || return 1
  if [ "$MCU" = f401 ]; then
    printf '%s/%s' "$(profile_bundle_dir "$1")" "$artifact"
  else
    printf '%s/%s' "$OUTPUT_DIR" "$artifact"
  fi
}

list_profiles() {
  local id
  for id in mini-v3-a00 mini-v3-a02 mini-v2-a00 mini-v2-a02 classic-v2 classic-v3 40th; do
    printf '%s\t%s\t%s\n' "$id" "$(profile_label "$id")" "$(profile_flags "$id")"
  done
}

command_available() {
  case "$1" in
    */*) [ -x "$1" ] ;;
    *) command -v "$1" >/dev/null 2>&1 ;;
  esac
}

select_ui() {
  UI_KIND=native
  UI_CMD=
  if [ "${MK61_UI:-}" = plain ] || [ "${MK61_UI:-}" = native ]; then
    return
  fi
  if [ -n "${MK61_UI:-}" ]; then
    if command_available "$MK61_UI"; then
      UI_CMD=$MK61_UI
      UI_KIND=dialog
    fi
    return
  fi
  if command -v dialog >/dev/null 2>&1; then
    UI_CMD=$(command -v dialog)
    UI_KIND=dialog
  elif command -v whiptail >/dev/null 2>&1; then
    UI_CMD=$(command -v whiptail)
    UI_KIND=dialog
  fi
}

repeat_char() {
  local char=$1
  local count=$2
  local result=
  while [ "$count" -gt 0 ]; do
    result=$result$char
    count=$((count - 1))
  done
  printf '%s' "$result"
}

native_term_size() {
  local value
  value=$(tput cols 2>/dev/null) || value=80
  case "$value" in ''|*[!0-9]*) value=80 ;; esac
  NATIVE_COLS=$value
  value=$(tput lines 2>/dev/null) || value=24
  case "$value" in ''|*[!0-9]*) value=24 ;; esac
  NATIVE_ROWS=$value

  NATIVE_WIDTH=$((NATIVE_COLS - 2))
  [ "$NATIVE_WIDTH" -gt 92 ] && NATIVE_WIDTH=92
  [ "$NATIVE_WIDTH" -lt 38 ] && NATIVE_WIDTH=38
  NATIVE_TEXT_WIDTH=$((NATIVE_WIDTH - 4))
  local left=$(((NATIVE_COLS - NATIVE_WIDTH) / 2))
  [ "$left" -lt 0 ] && left=0
  NATIVE_MARGIN=$(repeat_char ' ' "$left")
}

native_screen_enter() {
  [ "$UI_KIND" = native ] || return
  [ "$NATIVE_SCREEN_ACTIVE" -eq 0 ] || return
  native_term_size
  printf '\033[?1049h\033[?25l%s\033[2J\033[H' "$C_OUTSIDE" >&2
  NATIVE_SCREEN_ACTIVE=1
}

native_screen_leave() {
  [ "$NATIVE_SCREEN_ACTIVE" -eq 1 ] || return 0
  printf '\033[0m\033[?25h\033[?1049l' >&2
  NATIVE_SCREEN_ACTIVE=0
}

native_clear() {
  native_term_size
  NATIVE_VIEW_KIND=full
  printf '%s\033[?2026h\033[H' "$C_OUTSIDE" >&2
}

native_clip() {
  local text=$1
  local width=$2
  if [ "${#text}" -gt "$width" ]; then
    if [ "$width" -gt 1 ]; then
      printf '%s…' "${text:0:$((width - 1))}"
    fi
  else
    printf '%s' "$text"
  fi
}

native_border_top() {
  local title
  title=$(native_clip "$1" "$((NATIVE_WIDTH - 6))")
  local label="─ $title "
  local rest=$((NATIVE_WIDTH - 2 - ${#label}))
  [ "$rest" -lt 0 ] && rest=0
  printf '%s%s%s┌─ %s%s%s%s %s┐%s%s\n' "$C_OUTSIDE" "$NATIVE_MARGIN" \
    "$C_BORDER" "$C_WHITE" "$title" "$C_RESET" "$C_BORDER" \
    "$(repeat_char '─' "$rest")" "$C_RESET" "$C_OUTSIDE" >&2
}

native_border_bottom() {
  local hint
  hint=$(native_clip "$1" "$((NATIVE_WIDTH - 6))")
  local label="─ $hint "
  local rest=$((NATIVE_WIDTH - 2 - ${#label}))
  [ "$rest" -lt 0 ] && rest=0
  printf '%s%s%s└─ %s%s%s%s %s┘%s%s\033[J\033[?2026l' \
    "$C_OUTSIDE" "$NATIVE_MARGIN" "$C_BORDER_DIM" "$C_MUTED" "$hint" \
    "$C_RESET" "$C_BORDER_DIM" "$(repeat_char '─' "$rest")" \
    "$C_RESET" "$C_OUTSIDE" >&2
}

native_box_line() {
  local text
  text=$(native_clip "$1" "$NATIVE_TEXT_WIDTH")
  local style=${2:-}
  local padding=$((NATIVE_TEXT_WIDTH - ${#text}))
  [ "$padding" -lt 0 ] && padding=0
  printf '%s%s%s│%s %s%s%s%s %s│%s%s\n' \
    "$C_OUTSIDE" "$NATIVE_MARGIN" "$C_BORDER_DIM" "$C_RESET" "$style" "$text" \
    "$(repeat_char ' ' "$padding")" "$C_RESET" "$C_BORDER_DIM" "$C_RESET" \
    "$C_OUTSIDE" >&2
}

native_text_style() {
  case "$1" in
    Экран:*несовместим*|DFU:*не\ найден*|Устройство:*не\ найдено*|*Ошибка*|*НЕ\ НАЙДЕН*) printf '%s' "$C_RED" ;;
    Платформа:*|Оборудование:*|Профиль:*) printf '%s' "$C_BORDER" ;;
    Экран:*) printf '%s' "$C_MAGENTA" ;;
    Ключи:*) printf '%s' "$C_GREEN" ;;
    Цель:*|Контроллер:*|Метод:*) printf '%s' "$C_BLUE" ;;
    DFU:*) printf '%s' "$C_YELLOW" ;;
    Устройство:*не\ проверялось*) printf '%s' "$C_MUTED" ;;
    Устройство:*|*Готово*) printf '%s' "$C_GREEN" ;;
    *) printf '%s' "$C_WHITE" ;;
  esac
}

native_box_text() {
  local text=$1
  local line style
  while IFS= read -r line || [ -n "$line" ]; do
    style=$(native_text_style "$line")
    native_box_line "$line" "$style"
  done < <(printf '%s\n' "$text" | fold -s -w "$NATIVE_TEXT_WIDTH")
}

native_wrapped_line_count() {
  printf '%s\n' "$1" | fold -s -w "$NATIVE_TEXT_WIDTH" | awk 'END { print NR ? NR : 1 }'
}

native_update_begin() {
  printf '\033[?2026h' >&2
}

native_update_end() {
  printf '\033[?2026l' >&2
}

native_box_line_at() {
  local row=$1
  shift
  printf '\033[%d;1H' "$row" >&2
  native_box_line "$@"
}

native_menu_style() {
  case "$1" in
    '◉ '*|'☑ '*|'⌕ '*) printf '%s' "$C_BORDER" ;;
    '↓ '*) printf '%s' "$C_YELLOW" ;;
    '× '*) printf '%s' "$C_RED" ;;
    *) printf '%s' "$C_WHITE" ;;
  esac
}

native_draw_menu_item() {
  local index=$1
  local selected=$2
  local label=$3
  local text="  $label"
  local style
  style=$(native_menu_style "$label")
  if [ "$index" -eq "$selected" ]; then
    text="▶ $label"
    style=$C_SELECTED
  fi
  native_box_line_at "$((NATIVE_LIST_FIRST_ROW + index))" "$text" "$style"
}

native_read_escape_tail() {
  local saved rest
  # В macOS всё ещё поставляется Bash 3.2, где `read -t` принимает лишь целые секунды.
  # VTIME даёт короткое ожидание меньше секунды, не замедляя настоящий Esc.
  saved=$(stty -g 2>/dev/null) || {
    IFS= read -rsn2 -t 1 rest || true
    printf '%s' "$rest"
    return
  }
  stty -echo -icanon min 0 time 1 2>/dev/null || true
  rest=$(dd bs=1 count=2 2>/dev/null) || true
  stty "$saved" 2>/dev/null || true
  printf '%s' "$rest"
}

native_read_key() {
  local key rest
  IFS= read -rsn1 key || return 1
  if [ "$key" = $'\033' ]; then
    rest=$(native_read_escape_tail)
    case "$rest" in
      '[A'|'OA') printf '%s' up ;;
      '[B'|'OB') printf '%s' down ;;
      '[C'|'OC') printf '%s' right ;;
      '[D'|'OD') printf '%s' left ;;
      '[H'|'OH') printf '%s' home ;;
      '[F'|'OF') printf '%s' end ;;
      *) printf '%s' esc ;;
    esac
  elif [ -z "$key" ]; then
    printf '%s' enter
  elif [ "$key" = ' ' ]; then
    printf '%s' space
  elif [ "$key" = $'\177' ] || [ "$key" = $'\010' ]; then
    printf '%s' backspace
  else
    printf '%s' "$key"
  fi
}

native_draw_menu() {
  local title=$1
  local prompt=$2
  local selected=$3
  shift 3
  local labels=("$@")
  native_clear
  native_border_top "$title"
  native_box_line ''
  native_box_text "$prompt"
  native_box_line ''
  NATIVE_LIST_FIRST_ROW=$((4 + $(native_wrapped_line_count "$prompt")))
  local i=0 text style
  while [ "$i" -lt "${#labels[@]}" ]; do
    text="  ${labels[$i]}"
    style=$(native_menu_style "${labels[$i]}")
    if [ "$i" -eq "$selected" ]; then
      text="▶ ${labels[$i]}"
      style=$C_SELECTED
    fi
    native_box_line "$text" "$style"
    i=$((i + 1))
  done
  native_box_line ''
  native_border_bottom '↑↓ выбрать · Enter подтвердить · Esc назад'
}

ui_menu() {
  local title=$1
  local prompt=$2
  local initial_tag=$3
  shift 3
  if [ "$UI_KIND" = dialog ]; then
    local answer
    answer=$("$UI_CMD" --title "$title" --default-item "$initial_tag" \
      --menu "$prompt" 22 78 12 "$@" 3>&1 1>&2 2>&3)
    local status=$?
    [ "$status" -eq 0 ] || return 1
    printf '%s\n' "$answer"
    return 0
  fi

  local tags=()
  local labels=()
  local count=0
  while [ "$#" -ge 2 ]; do
    tags[$count]=$1
    labels[$count]=$2
    count=$((count + 1))
    shift 2
  done
  local selected=0
  local index=0
  while [ "$index" -lt "$count" ]; do
    if [ "${tags[$index]}" = "$initial_tag" ]; then
      selected=$index
      break
    fi
    index=$((index + 1))
  done
  local key previous
  native_draw_menu "$title" "$prompt" "$selected" "${labels[@]}"
  while true; do
    key=$(native_read_key) || return 1
    previous=$selected
    case "$key" in
      up|k|K)
        selected=$((selected - 1))
        [ "$selected" -lt 0 ] && selected=$((count - 1))
        ;;
      down|j|J)
        selected=$((selected + 1))
        [ "$selected" -ge "$count" ] && selected=0
        ;;
      home) selected=0 ;;
      end) selected=$((count - 1)) ;;
      enter|space)
        printf '%s\n' "${tags[$selected]}"
        return 0
        ;;
      esc|q|Q) return 1 ;;
      [1-9])
        if [ "$key" -le "$count" ]; then
          printf '%s\n' "${tags[$((key - 1))]}"
          return 0
        fi
        ;;
    esac
    if [ "$selected" -ne "$previous" ]; then
      native_update_begin
      native_draw_menu_item "$previous" "$selected" "${labels[$previous]}"
      native_draw_menu_item "$selected" "$selected" "${labels[$selected]}"
      native_update_end
    fi
  done
}

native_draw_radio_item() {
  local index=$1
  local selected=$2
  local current=$3
  local state=$4
  local label=$5
  local marker='○'
  local style=$C_YELLOW
  if [ "$state" = disabled ]; then
    marker='⊘'
    style=$C_RED
  elif [ "$index" -eq "$current" ]; then
    marker='◉'
    style=$C_GREEN
  fi
  local text="$marker  $label"
  if [ "$index" -eq "$selected" ]; then
    text="▶ $text"
    style=$C_SELECTED
  else
    text="  $text"
  fi
  native_box_line_at "$((NATIVE_LIST_FIRST_ROW + index))" "$text" "$style"
}

native_draw_check_item() {
  local index=$1
  local selected=$2
  local checked=$3
  local label=$4
  local marker='☐'
  local style=$C_YELLOW
  if [ "$checked" -eq 1 ]; then
    marker='☑'
    style=$C_GREEN
  fi
  local text="$marker  $label"
  if [ "$index" -eq "$selected" ]; then
    text="▶ $text"
    style=$C_SELECTED
  else
    text="  $text"
  fi
  native_box_line_at "$((NATIVE_LIST_FIRST_ROW + index))" "$text" "$style"
}

native_finish_list() {
  local count=$1
  local hint=$2
  native_box_line_at "$((NATIVE_LIST_FIRST_ROW + count))" ''
  printf '\033[%d;1H' "$((NATIVE_LIST_FIRST_ROW + count + 1))" >&2
  native_border_bottom "$hint"
}

ui_radiolist() {
  local title=$1
  local prompt=$2
  shift 2
  if [ "$UI_KIND" = dialog ]; then
    local answer state index=0
    local dialog_args=()
    while [ "$#" -ge 3 ]; do
      state=$3
      [ "$state" = disabled ] && state=off
      dialog_args[$index]=$1
      dialog_args[$((index + 1))]=$2
      dialog_args[$((index + 2))]=$state
      index=$((index + 3))
      shift 3
    done
    answer=$("$UI_CMD" --title "$title" --radiolist "$prompt" 22 82 12 \
      "${dialog_args[@]}" \
      3>&1 1>&2 2>&3)
    local status=$?
    [ "$status" -eq 0 ] || return 1
    printf '%s\n' "$answer"
    return 0
  fi

  local tags=()
  local labels=()
  local states=()
  local count=0
  local current=-1
  while [ "$#" -ge 3 ]; do
    tags[$count]=$1
    labels[$count]=$2
    states[$count]=$3
    if [ "$3" = on ]; then current=$count; fi
    count=$((count + 1))
    shift 3
  done

  local selected=$current
  if [ "$selected" -lt 0 ] || [ "${states[$selected]}" = disabled ]; then
    selected=0
    while [ "$selected" -lt "$count" ] && [ "${states[$selected]}" = disabled ]; do
      selected=$((selected + 1))
    done
  fi
  [ "$selected" -ge "$count" ] && return 1
  local key i previous_selected previous_current attempts

  native_clear
  native_border_top "$title"
  native_box_line ''
  native_box_text "$prompt"
  native_box_line ''
  NATIVE_LIST_FIRST_ROW=$((4 + $(native_wrapped_line_count "$prompt")))
  i=0
  while [ "$i" -lt "$count" ]; do
    native_draw_radio_item "$i" "$selected" "$current" "${states[$i]}" "${labels[$i]}"
    i=$((i + 1))
  done
  native_finish_list "$count" '↑↓ выбрать · Space отметить · Enter сохранить · Esc назад'

  while true; do
    key=$(native_read_key) || return 1
    previous_selected=$selected
    previous_current=$current
    case "$key" in
      up|k|K)
        attempts=$count
        while [ "$attempts" -gt 0 ]; do
          selected=$((selected - 1))
          [ "$selected" -lt 0 ] && selected=$((count - 1))
          [ "${states[$selected]}" != disabled ] && break
          attempts=$((attempts - 1))
        done
        ;;
      down|j|J)
        attempts=$count
        while [ "$attempts" -gt 0 ]; do
          selected=$((selected + 1))
          [ "$selected" -ge "$count" ] && selected=0
          [ "${states[$selected]}" != disabled ] && break
          attempts=$((attempts - 1))
        done
        ;;
      home)
        selected=0
        while [ "${states[$selected]}" = disabled ]; do selected=$((selected + 1)); done
        ;;
      end)
        selected=$((count - 1))
        while [ "${states[$selected]}" = disabled ]; do selected=$((selected - 1)); done
        ;;
      space)
        [ "${states[$selected]}" != disabled ] && current=$selected
        ;;
      enter)
        [ "${states[$selected]}" = disabled ] && continue
        current=$selected
        printf '%s\n' "${tags[$current]}"
        return 0
        ;;
      esc|q|Q) return 1 ;;
    esac
    if [ "$selected" -ne "$previous_selected" ] || [ "$current" -ne "$previous_current" ]; then
      native_update_begin
      native_draw_radio_item "$previous_selected" "$selected" "$current" \
        "${states[$previous_selected]}" "${labels[$previous_selected]}"
      if [ "$previous_current" -ge 0 ] && [ "$previous_current" -ne "$previous_selected" ]; then
        native_draw_radio_item "$previous_current" "$selected" "$current" \
          "${states[$previous_current]}" "${labels[$previous_current]}"
      fi
      if [ "$selected" -ne "$previous_selected" ] && [ "$selected" -ne "$previous_current" ]; then
        native_draw_radio_item "$selected" "$selected" "$current" \
          "${states[$selected]}" "${labels[$selected]}"
      fi
      if [ "$current" -ge 0 ] && [ "$current" -ne "$previous_selected" ] && \
          [ "$current" -ne "$previous_current" ] && [ "$current" -ne "$selected" ]; then
        native_draw_radio_item "$current" "$selected" "$current" \
          "${states[$current]}" "${labels[$current]}"
      fi
      native_update_end
    fi
  done
}

ui_checklist() {
  local title=$1
  local prompt=$2
  shift 2
  if [ "$UI_KIND" = dialog ]; then
    local answer
    answer=$("$UI_CMD" --title "$title" --separate-output --checklist \
      "$prompt" 22 88 12 "$@" 3>&1 1>&2 2>&3)
    local status=$?
    [ "$status" -eq 0 ] || return 1
    printf '%s\n' "$answer"
    return 0
  fi

  local tags=()
  local labels=()
  local checked=()
  local count=0
  while [ "$#" -ge 3 ]; do
    tags[$count]=$1
    labels[$count]=$2
    if [ "$3" = on ]; then checked[$count]=1; else checked[$count]=0; fi
    count=$((count + 1))
    shift 3
  done

  local selected=0
  local key i previous

  native_clear
  native_border_top "$title"
  native_box_line ''
  native_box_text "$prompt"
  native_box_line ''
  NATIVE_LIST_FIRST_ROW=$((4 + $(native_wrapped_line_count "$prompt")))
  i=0
  while [ "$i" -lt "$count" ]; do
    native_draw_check_item "$i" "$selected" "${checked[$i]}" "${labels[$i]}"
    i=$((i + 1))
  done
  native_finish_list "$count" '↑↓ выбрать · Space переключить · Enter сохранить · Esc назад'

  while true; do
    key=$(native_read_key) || return 1
    previous=$selected
    case "$key" in
      up|k|K)
        selected=$((selected - 1))
        [ "$selected" -lt 0 ] && selected=$((count - 1))
        ;;
      down|j|J)
        selected=$((selected + 1))
        [ "$selected" -ge "$count" ] && selected=0
        ;;
      home) selected=0 ;;
      end) selected=$((count - 1)) ;;
      space|x|X)
        checked[$selected]=$((1 - checked[$selected]))
        native_update_begin
        native_draw_check_item "$selected" "$selected" "${checked[$selected]}" "${labels[$selected]}"
        native_update_end
        ;;
      enter)
        i=0
        while [ "$i" -lt "$count" ]; do
          [ "${checked[$i]}" -eq 1 ] && printf '%s\n' "${tags[$i]}"
          i=$((i + 1))
        done
        return 0
        ;;
      esc|q|Q) return 1 ;;
    esac
    if [ "$selected" -ne "$previous" ]; then
      native_update_begin
      native_draw_check_item "$previous" "$selected" "${checked[$previous]}" "${labels[$previous]}"
      native_draw_check_item "$selected" "$selected" "${checked[$selected]}" "${labels[$selected]}"
      native_update_end
    fi
  done
}

ui_yesno() {
  local title=$1
  local text=$2
  if [ "$UI_KIND" = dialog ]; then
    "$UI_CMD" --title "$title" --yesno "$text" 12 74
    return $?
  fi
  local selected=1
  local key previous first_row
  first_row=$((4 + $(native_wrapped_line_count "$text")))
  native_clear
  native_border_top "$title"
  native_box_line ''
  native_box_text "$text"
  native_box_line ''
  native_box_line '  Да, продолжить' "$C_WHITE"
  native_box_line '▶ Отмена' "$C_SELECTED"
  native_box_line ''
  native_border_bottom '←→ выбрать · Enter подтвердить · Esc отменить'
  while true; do
    key=$(native_read_key) || return 1
    previous=$selected
    case "$key" in
      up|down|left|right|j|J|k|K) selected=$((1 - selected)) ;;
      y|Y|д|Д) return 0 ;;
      n|N|н|Н|esc|q|Q) return 1 ;;
      enter|space) [ "$selected" -eq 0 ]; return $? ;;
    esac
    if [ "$selected" -ne "$previous" ]; then
      native_update_begin
      if [ "$selected" -eq 0 ]; then
        native_box_line_at "$first_row" '▶ Да, продолжить' "$C_SELECTED"
        native_box_line_at "$((first_row + 1))" '  Отмена' "$C_WHITE"
      else
        native_box_line_at "$first_row" '  Да, продолжить' "$C_WHITE"
        native_box_line_at "$((first_row + 1))" '▶ Отмена' "$C_SELECTED"
      fi
      native_update_end
    fi
  done
}

ui_msg() {
  local title=$1
  local text=$2
  if [ "$UI_KIND" = dialog ]; then
    "$UI_CMD" --title "$title" --msgbox "$text" 14 76
    return
  fi
  native_clear
  native_border_top "$title"
  native_box_line ''
  native_box_text "$text"
  native_box_line ''
  native_box_line '                         [  OK  ]' "$C_SELECTED"
  native_box_line ''
  native_border_bottom 'Enter или Esc закрыть'
  native_read_key >/dev/null || true
}

native_draw_input_value() {
  local row=$1
  local value=$2
  local limit=$((NATIVE_TEXT_WIDTH - 7))
  local shown=$value
  if [ "${#shown}" -gt "$limit" ]; then
    local start=$((${#shown} - limit + 1))
    shown="…${shown:$start:$((limit - 1))}"
  fi
  native_box_line_at "$row" "Путь: ${shown}█" "$C_SELECTED"
}

ui_input() {
  local title=$1
  local text=$2
  local value=${3:-}
  if [ "$UI_KIND" = dialog ]; then
    local answer
    answer=$("$UI_CMD" --title "$title" --inputbox "$text" 16 88 "$value" \
      3>&1 1>&2 2>&3)
    local status=$?
    [ "$status" -eq 0 ] || return 1
    printf '%s\n' "$answer"
    return 0
  fi

  local input_row=$((4 + $(native_wrapped_line_count "$text")))
  local key
  native_clear
  native_border_top "$title"
  native_box_line ''
  native_box_text "$text"
  native_box_line ''
  native_draw_input_value "$input_row" "$value"
  native_box_line_at "$((input_row + 1))" ''
  printf '\033[%d;1H' "$((input_row + 2))" >&2
  native_border_bottom 'Вставьте полный путь · Enter сохранить · Esc пропустить'
  while true; do
    key=$(native_read_key) || return 1
    case "$key" in
      enter)
        printf '%s\n' "$value"
        return 0
        ;;
      esc) return 1 ;;
      backspace)
        [ -n "$value" ] && value=${value%?}
        ;;
      space) value="$value " ;;
      up|down|left|right|home|end) continue ;;
      *) value=$value$key ;;
    esac
    native_update_begin
    native_draw_input_value "$input_row" "$value"
    native_update_end
  done
}

ui_log() {
  local title=$1
  local file=$2
  if [ ! -s "$file" ]; then
    ui_msg "$title" 'Журнал пуст.'
    return
  fi
  if [ "$UI_KIND" = dialog ]; then
    "$UI_CMD" --title "$title" --textbox "$file" 24 88
    return
  fi

  local lines=()
  local line count=0
  while IFS= read -r line || [ -n "$line" ]; do
    line=$(printf '%s' "$line" | tr '\033' '?')
    lines[$count]=$line
    count=$((count + 1))
  done < <(tr '\r' '\n' < "$file")
  local visible=$((NATIVE_ROWS - 7))
  [ "$visible" -lt 6 ] && visible=6
  [ "$visible" -gt 18 ] && visible=18
  local offset=$((count - visible))
  [ "$offset" -lt 0 ] && offset=0
  local key i end
  while true; do
    native_clear
    native_border_top "$title"
    native_box_line ''
    i=$offset
    end=$((offset + visible))
    while [ "$i" -lt "$end" ]; do
      if [ "$i" -lt "$count" ]; then native_box_line "${lines[$i]}"
      else native_box_line ''
      fi
      i=$((i + 1))
    done
    native_box_line ''
    native_border_bottom "↑↓ прокрутка · $((offset + 1))–$((offset + visible > count ? count : offset + visible)) из $count · Esc закрыть"
    key=$(native_read_key) || return
    case "$key" in
      up|k|K) [ "$offset" -gt 0 ] && offset=$((offset - 1)) ;;
      down|j|J) [ "$((offset + visible))" -lt "$count" ] && offset=$((offset + 1)) ;;
      home) offset=0 ;;
      end) offset=$((count - visible)); [ "$offset" -lt 0 ] && offset=0 ;;
      enter|esc|q|Q) return ;;
    esac
  done
}

native_progress_draw() {
  local title=$1
  local message=$2
  local percent=$3
  local hint='Операция выполняется…'
  [ "$percent" -lt 0 ] && percent=0
  [ "$percent" -gt 100 ] && percent=100
  [ "$percent" -eq 100 ] && hint='✓ Готово'
  local bar_width=$((NATIVE_TEXT_WIDTH - 7))
  [ "$bar_width" -lt 12 ] && bar_width=12
  local filled=$((bar_width * percent / 100))
  local empty=$((bar_width - filled))
  if [ "$NATIVE_VIEW_KIND" != progress ] || [ "$NATIVE_PROGRESS_TITLE" != "$title" ]; then
    native_clear
    native_border_top "$title"
    native_box_line ''
    native_box_line "$message" "$(native_text_style "$message")"
    native_box_line ''
    NATIVE_VIEW_KIND=progress
    NATIVE_PROGRESS_TITLE=$title
  else
    native_update_begin
    native_box_line_at 3 "$message" "$(native_text_style "$message")"
    printf '\033[5;1H' >&2
  fi
  printf '%s%s%s│%s [' "$C_OUTSIDE" "$NATIVE_MARGIN" "$C_BORDER_DIM" "$C_RESET" >&2
  printf '%s%s%s' "$C_GREEN" "$(repeat_char '█' "$filled")" "$C_RESET" >&2
  printf '%s%s%s' "$C_MUTED" "$(repeat_char '░' "$empty")" "$C_RESET" >&2
  printf '] %s%3d%%%s %s│%s%s\n' "$C_YELLOW" "$percent" "$C_RESET" \
    "$C_BORDER_DIM" "$C_RESET" "$C_OUTSIDE" >&2
  native_box_line_at 6 ''
  printf '\033[7;1H' >&2
  native_border_bottom "$hint"
}

progress_percent_from_log() {
  local file=$1
  tr '\r' '\n' < "$file" 2>/dev/null |
    awk '{ while (match($0, /[0-9]+%/)) { value=substr($0, RSTART, RLENGTH-1); $0=substr($0, RSTART+RLENGTH) } } END { if (value != "") print value }'
}

progress_stream() {
  local status_file=$1
  local log_file=$2
  local mode=$3
  local message=$4
  local percent=5
  while [ ! -s "$status_file" ]; do
    if [ "$mode" = measured ]; then
      local measured
      measured=$(progress_percent_from_log "$log_file")
      case "$measured" in
        ''|*[!0-9]*) ;;
        *) [ "$measured" -le 95 ] && percent=$measured ;;
      esac
    elif [ "$percent" -lt 90 ]; then
      percent=$((percent + 2))
      [ "$percent" -gt 90 ] && percent=90
    fi
    printf 'XXX\n%d\n%s\nXXX\n' "$percent" "$message"
    sleep 0.25
  done
  local status
  status=$(sed -n '1p' "$status_file")
  if [ "$status" -eq 0 ]; then
    printf 'XXX\n100\nГотово\nXXX\n'
  else
    printf 'XXX\n%d\nОшибка — подробности в журнале\nXXX\n' "$percent"
  fi
  sleep 0.35
}

run_with_progress() {
  local title=$1
  local message=$2
  local log_file=$3
  local mode=$4
  shift 4
  local status_file="$log_file.status"
  mkdir -p "$(dirname "$log_file")"
  : > "$log_file"
  rm -f "$status_file"

  (
    "$@" > "$log_file" 2>&1
    printf '%s\n' "$?" > "$status_file"
  ) &
  ACTIVE_PID=$!

  if [ "$UI_KIND" = dialog ] && [ "$INTERACTIVE" -eq 1 ]; then
    progress_stream "$status_file" "$log_file" "$mode" "$message" |
      "$UI_CMD" --title "$title" --gauge "$message" 10 76 0
  elif [ "$UI_KIND" = native ] && [ "$INTERACTIVE" -eq 1 ]; then
    local percent=5
    local measured
    while [ ! -s "$status_file" ]; do
      if [ "$mode" = measured ]; then
        measured=$(progress_percent_from_log "$log_file")
        case "$measured" in
          ''|*[!0-9]*) ;;
          *) [ "$measured" -le 95 ] && percent=$measured ;;
        esac
      elif [ "$percent" -lt 90 ]; then
        percent=$((percent + 2))
        [ "$percent" -gt 90 ] && percent=90
      fi
      native_progress_draw "$title" "$message" "$percent"
      sleep 0.2
    done
    local native_status
    native_status=$(sed -n '1p' "$status_file")
    if [ "$native_status" -eq 0 ]; then
      native_progress_draw "$title" 'Готово' 100
    else
      native_progress_draw "$title" 'Ошибка — подробности в журнале' "$percent"
    fi
    sleep 0.4
  elif [ -t 1 ]; then
    local frames='|/-\\'
    local frame=0
    while [ ! -s "$status_file" ]; do
      printf '\r%s [%s]' "$message" "${frames:$frame:1}"
      frame=$(((frame + 1) % 4))
      sleep 0.2
    done
    printf '\r%-78s\r' ' '
  else
    printf '%s…\n' "$message"
    while [ ! -s "$status_file" ]; do sleep 0.25; done
  fi

  wait "$ACTIVE_PID" 2>/dev/null || true
  ACTIVE_PID=
  local status
  status=$(sed -n '1p' "$status_file")
  rm -f "$status_file"
  [ "$status" -eq 0 ]
}

boolean_valid() {
  case "${1:-}" in 0|1) return 0 ;; esac
  return 1
}

load_config() {
  if [ ! -r "$CONFIG_FILE" ]; then
    local legacy_profile=
    if [ "$CLI_PROFILE" -eq 1 ]; then
      hardware_from_profile "$PROFILE" || true
    elif [ -r "$LEGACY_SELECTION_FILE" ]; then
      IFS= read -r legacy_profile < "$LEGACY_SELECTION_FILE" || legacy_profile=
      if profile_valid "$legacy_profile"; then
        PROFILE=$legacy_profile
        hardware_from_profile "$PROFILE" || true
      fi
    fi
    if platform_valid "$HARDWARE_PLATFORM" || screen_valid "$SCREEN_KIND"; then
      save_config || true
    fi
    return 0
  fi
  local key value saved_profile= saved_platform= saved_screen= saved_mcu=f411 migrate=0
  while IFS='=' read -r key value || [ -n "${key:-}${value:-}" ]; do
    value=${value%$'\r'}
    case "$key" in
      PROFILE)
        if profile_valid "$value"; then saved_profile=$value; fi
        ;;
      PLATFORM)
        if platform_valid "$value"; then saved_platform=$value; fi
        ;;
      SCREEN)
        if screen_valid "$value"; then saved_screen=$value; fi
        ;;
      MCU)
        if mcu_valid "$value"; then saved_mcu=$value; fi
        ;;
      DFU_UTIL_PATH)
        DFU_UTIL_PATH=$value
        ;;
      MK61_ENABLE_FOCAL)
        boolean_valid "$value" && ENABLE_FOCAL=$value
        ;;
      MK61_ENABLE_TINYBASIC)
        boolean_valid "$value" && ENABLE_TINYBASIC=$value
        ;;
      MK61_ENABLE_WBMP_VIEWER)
        boolean_valid "$value" && ENABLE_WBMP_VIEWER=$value
        ;;
      MK61_ENABLE_USB_SCREEN)
        boolean_valid "$value" && ENABLE_USB_SCREEN=$value
        ;;
      MK61_ENABLE_EXTENDED_FONT_SETTINGS)
        boolean_valid "$value" && ENABLE_EXTENDED_FONT_SETTINGS=$value
        ;;
      MK61_USER_EXPLORER_SHORTCUT)
        boolean_valid "$value" && ENABLE_USER_EXPLORER=$value
        ;;
      MK61_MATH_BACKEND)
        boolean_valid "$value" && ENABLE_CORE_MATH=$value
        ;;
    esac
  done < "$CONFIG_FILE"

  if [ "$CLI_MCU" -eq 0 ]; then MCU=$saved_mcu; fi
  if [ "$CLI_PROFILE" -eq 1 ]; then
    hardware_from_profile "$PROFILE" || true
  else
    HARDWARE_PLATFORM=$saved_platform
    SCREEN_KIND=$saved_screen
    if [ -z "$HARDWARE_PLATFORM" ] && [ -z "$SCREEN_KIND" ] && \
        profile_valid "$saved_profile"; then
      PROFILE=$saved_profile
      hardware_from_profile "$PROFILE" || true
      migrate=1
    fi
    sync_profile_from_hardware
    [ "$migrate" -eq 1 ] && save_config || true
  fi
}

save_config() {
  sync_profile_from_hardware
  local temporary="$CONFIG_FILE.tmp"
  mkdir -p "$(dirname "$CONFIG_FILE")" || return 1
  {
    printf '# Создано tools/mk61-firmware.cmd. Можно редактировать, пока инструмент закрыт.\n'
    printf 'MCU=%s\n' "$MCU"
    printf 'PLATFORM=%s\n' "$HARDWARE_PLATFORM"
    printf 'SCREEN=%s\n' "$SCREEN_KIND"
    printf 'DFU_UTIL_PATH=%s\n' "$DFU_UTIL_PATH"
    printf 'MK61_ENABLE_FOCAL=%s\n' "$ENABLE_FOCAL"
    printf 'MK61_ENABLE_TINYBASIC=%s\n' "$ENABLE_TINYBASIC"
    printf 'MK61_ENABLE_WBMP_VIEWER=%s\n' "$ENABLE_WBMP_VIEWER"
    printf 'MK61_ENABLE_USB_SCREEN=%s\n' "$ENABLE_USB_SCREEN"
    printf 'MK61_ENABLE_EXTENDED_FONT_SETTINGS=%s\n' "$ENABLE_EXTENDED_FONT_SETTINGS"
    printf 'MK61_USER_EXPLORER_SHORTCUT=%s\n' "$ENABLE_USER_EXPLORER"
    printf 'MK61_MATH_BACKEND=%s\n' "$ENABLE_CORE_MATH"
  } > "$temporary" || return 1
  mv "$temporary" "$CONFIG_FILE"
}

checkbox_marker() {
  if [ "$1" -eq 1 ]; then printf '☑'; else printf '☐'; fi
}

option_state() {
  if [ "$1" -eq 1 ]; then printf 'on'; else printf 'off'; fi
}

platform_state() {
  if [ "$HARDWARE_PLATFORM" = "$1" ]; then printf 'on'; else printf 'off'; fi
}

screen_option_state() {
  local screen=$1
  if platform_valid "$HARDWARE_PLATFORM" && \
      ! hardware_compatible "$HARDWARE_PLATFORM" "$screen"; then
    printf 'disabled'
  elif [ "$SCREEN_KIND" = "$screen" ]; then
    printf 'on'
  else
    printf 'off'
  fi
}

mcu_state() {
  if [ "$MCU" = "$1" ]; then printf 'on'; else printf 'off'; fi
}

compile_option_flags() {
  printf '%s' "-DMK61_ENABLE_FOCAL=$ENABLE_FOCAL" \
    " -DMK61_ENABLE_TINYBASIC=$ENABLE_TINYBASIC" \
    " -DMK61_ENABLE_WBMP_VIEWER=$ENABLE_WBMP_VIEWER" \
    " -DMK61_ENABLE_USB_SCREEN=$ENABLE_USB_SCREEN" \
    " -DMK61_ENABLE_EXTENDED_FONT_SETTINGS=$ENABLE_EXTENDED_FONT_SETTINGS" \
    " -DMK61_USER_EXPLORER_SHORTCUT=$ENABLE_USER_EXPLORER" \
    " -DMK61_MATH_BACKEND=$ENABLE_CORE_MATH"
}

all_compile_flags() {
  local board_flags
  board_flags=$(profile_flags "$1") || return 1
  printf '%s %s' "$board_flags" "$(compile_option_flags)"
}

compile_options_summary() {
  printf '%s FOCAL  %s TinyBASIC  %s WBMP  %s USB  %s шрифты  %s USER  %s CORE math' \
    "$(checkbox_marker "$ENABLE_FOCAL")" \
    "$(checkbox_marker "$ENABLE_TINYBASIC")" \
    "$(checkbox_marker "$ENABLE_WBMP_VIEWER")" \
    "$(checkbox_marker "$ENABLE_USB_SCREEN")" \
    "$(checkbox_marker "$ENABLE_EXTENDED_FONT_SETTINGS")" \
    "$(checkbox_marker "$ENABLE_USER_EXPLORER")" \
    "$(checkbox_marker "$ENABLE_CORE_MATH")"
}

compile_options_details() {
  printf '%s FOCAL (MK61_ENABLE_FOCAL)\n' "$(checkbox_marker "$ENABLE_FOCAL")"
  printf '%s TinyBASIC (MK61_ENABLE_TINYBASIC)\n' "$(checkbox_marker "$ENABLE_TINYBASIC")"
  printf '%s WBMP viewer (MK61_ENABLE_WBMP_VIEWER)\n' "$(checkbox_marker "$ENABLE_WBMP_VIEWER")"
  printf '%s USB-экран (MK61_ENABLE_USB_SCREEN)\n' "$(checkbox_marker "$ENABLE_USB_SCREEN")"
  printf '%s расширенные шрифты (MK61_ENABLE_EXTENDED_FONT_SETTINGS)\n' \
    "$(checkbox_marker "$ENABLE_EXTENDED_FONT_SETTINGS")"
  printf '%s USER → Explorer (MK61_USER_EXPLORER_SHORTCUT)\n' \
    "$(checkbox_marker "$ENABLE_USER_EXPLORER")"
  if [ "$ENABLE_CORE_MATH" -eq 1 ]; then
    printf '☑ CORE math (MK61_MATH_BACKEND=1)\n'
  else
    printf '☐ CORE math (MK61_MATH_BACKEND=0, libm)\n'
  fi
}

show_config() {
  sync_profile_from_hardware
  printf 'CONFIG_FILE=%s\n' "$CONFIG_FILE"
  printf 'MCU=%s\n' "$MCU"
  printf 'PLATFORM=%s\n' "$HARDWARE_PLATFORM"
  printf 'SCREEN=%s\n' "$SCREEN_KIND"
  printf 'PROFILE=%s\n' "$PROFILE"
  printf 'DFU_UTIL_PATH=%s\n' "$DFU_UTIL_PATH"
  printf 'MK61_ENABLE_FOCAL=%s\n' "$ENABLE_FOCAL"
  printf 'MK61_ENABLE_TINYBASIC=%s\n' "$ENABLE_TINYBASIC"
  printf 'MK61_ENABLE_WBMP_VIEWER=%s\n' "$ENABLE_WBMP_VIEWER"
  printf 'MK61_ENABLE_USB_SCREEN=%s\n' "$ENABLE_USB_SCREEN"
  printf 'MK61_ENABLE_EXTENDED_FONT_SETTINGS=%s\n' "$ENABLE_EXTENDED_FONT_SETTINGS"
  printf 'MK61_USER_EXPLORER_SHORTCUT=%s\n' "$ENABLE_USER_EXPLORER"
  printf 'MK61_MATH_BACKEND=%s\n' "$ENABLE_CORE_MATH"
  if profile_valid "$PROFILE"; then
    printf 'COMPILE_FLAGS=%s\n' "$(all_compile_flags "$PROFILE")"
  else
    printf 'COMPILE_FLAGS=%s\n' "$(compile_option_flags)"
  fi
}

choose_mcu() {
  local chosen
  chosen=$(ui_radiolist 'Контроллер' \
    'F411 хранит системные компоненты в прошивке. F401 собирает resident и согласованные System APP для C5:' \
    f411 'STM32F411CE · 512 KiB Flash' "$(mcu_state f411)" \
    f401 'STM32F401CC · 256 KiB Flash · APP в C5' "$(mcu_state f401)") || return 1
  MCU=$chosen
  save_config
}

choose_platform() {
  local chosen
  chosen=$(ui_radiolist 'Платформа' \
    'Выберите ревизию платы. Экран выбирается отдельно:' \
    mini-v3    'mini V3' "$(platform_state mini-v3)" \
    mini-v2    'mini V2' "$(platform_state mini-v2)" \
    classic-v2 'Classic V2' "$(platform_state classic-v2)" \
    classic-v3 'Classic V3' "$(platform_state classic-v3)" \
    40th       'MK61s 40th' "$(platform_state 40th)") || return 1
  HARDWARE_PLATFORM=$chosen
  sync_profile_from_hardware
  save_config
}

choose_screen() {
  local chosen
  chosen=$(ui_radiolist 'Экран' \
    'Выберите дисплей. Символ ⊘ означает, что экран не совместим с выбранной платформой:' \
    lcd1602-a00 'LCD1602 · CGROM A00' "$(screen_option_state lcd1602-a00)" \
    lcd1602-a02 'LCD1602 · CGROM A02' "$(screen_option_state lcd1602-a02)" \
    uc1609      'UC1609 · 192×64' "$(screen_option_state uc1609)") || return 1
  if platform_valid "$HARDWARE_PLATFORM" && \
      ! hardware_compatible "$HARDWARE_PLATFORM" "$chosen"; then
    ui_msg 'Несовместимая пара' \
      "$(platform_label "$HARDWARE_PLATFORM") не поддерживает $(screen_label "$chosen")."
    return 1
  fi
  SCREEN_KIND=$chosen
  sync_profile_from_hardware
  save_config
}

ensure_hardware_profile() {
  if ! platform_valid "$HARDWARE_PLATFORM"; then
    if [ "$INTERACTIVE" -eq 1 ]; then choose_platform || return 1
    else printf 'Error: select hardware with --profile ID.\n' >&2; return 1
    fi
  fi
  if ! screen_valid "$SCREEN_KIND"; then
    if [ "$INTERACTIVE" -eq 1 ]; then choose_screen || return 1
    else printf 'Error: select hardware with --profile ID.\n' >&2; return 1
    fi
  fi
  sync_profile_from_hardware
  if profile_valid "$PROFILE"; then return 0; fi
  if [ "$INTERACTIVE" -eq 1 ]; then
    ui_msg 'Несовместимое оборудование' \
      "Платформа: $(platform_label "$HARDWARE_PLATFORM")
Экран: $(screen_label "$SCREEN_KIND")

Выберите совместимый экран."
    choose_screen || return 1
    sync_profile_from_hardware
    profile_valid "$PROFILE"
    return $?
  fi
  printf 'Error: incompatible platform/screen selection.\n' >&2
  return 1
}

choose_compile_options() {
  local chosen tag
  chosen=$(ui_checklist 'Ключи компиляции' \
    'Пробелом включайте и выключайте независимые функции. Все значения явно передаются Arduino CLI как -Dключи:' \
    focal      'FOCAL · MK61_ENABLE_FOCAL' "$(option_state "$ENABLE_FOCAL")" \
    tinybasic  'TinyBASIC · MK61_ENABLE_TINYBASIC' "$(option_state "$ENABLE_TINYBASIC")" \
    wbmp       'WBMP viewer · MK61_ENABLE_WBMP_VIEWER' "$(option_state "$ENABLE_WBMP_VIEWER")" \
    usb_screen 'USB-экран · MK61_ENABLE_USB_SCREEN' "$(option_state "$ENABLE_USB_SCREEN")" \
    fonts      'Расширенные настройки шрифта' "$(option_state "$ENABLE_EXTENDED_FONT_SETTINGS")" \
    explorer   'Клавиша USER открывает Explorer' "$(option_state "$ENABLE_USER_EXPLORER")" \
    core_math  'Математика CORE вместо libm' "$(option_state "$ENABLE_CORE_MATH")") || return 1

  ENABLE_FOCAL=0
  ENABLE_TINYBASIC=0
  ENABLE_WBMP_VIEWER=0
  ENABLE_USB_SCREEN=0
  ENABLE_EXTENDED_FONT_SETTINGS=0
  ENABLE_USER_EXPLORER=0
  ENABLE_CORE_MATH=0
  while IFS= read -r tag; do
    case "$tag" in
      focal) ENABLE_FOCAL=1 ;;
      tinybasic) ENABLE_TINYBASIC=1 ;;
      wbmp) ENABLE_WBMP_VIEWER=1 ;;
      usb_screen) ENABLE_USB_SCREEN=1 ;;
      fonts) ENABLE_EXTENDED_FONT_SETTINGS=1 ;;
      explorer) ENABLE_USER_EXPLORER=1 ;;
      core_math) ENABLE_CORE_MATH=1 ;;
    esac
  done < <(printf '%s\n' "$chosen")
  save_config
}

arduino_core_ready() {
  command_available "$ARDUINO_CLI" || return 1
  "$ARDUINO_CLI" core list 2>/dev/null |
    awk -v version="$STM32_CORE_VERSION" '$1 == "STMicroelectronics:stm32" && $2 == version { found=1 } END { exit !found }'
}

arduino_libraries_ready() {
  command_available "$ARDUINO_CLI" || return 1
  local libraries
  libraries=$("$ARDUINO_CLI" lib list 2>/dev/null) || return 1
  printf '%s\n' "$libraries" | grep -Eq '^LiquidCrystal[[:space:]]+1\.0\.7([[:space:]]|$)' || return 1
  printf '%s\n' "$libraries" | grep -Eq '^STM32duino RTC[[:space:]]+1\.9\.0([[:space:]]|$)' || return 1
}

f401_system_apps_enabled() {
  [ "$ENABLE_FOCAL" -eq 1 ] || [ "$ENABLE_TINYBASIC" -eq 1 ] || \
    [ "$ENABLE_WBMP_VIEWER" -eq 1 ]
}

f401_any_apps_requested() {
  f401_system_apps_enabled || [ -n "${MK61_APP_MANIFESTS:-}" ]
}

f401_host_tools_ready() {
  [ "$MCU" != f401 ] || {
    [ -x "$PROJECT_ROOT/tools/build_f401_bundle.sh" ] &&
      { ! f401_any_apps_requested || command_available c++; }
  }
}

build_dependencies_ready() {
  arduino_core_ready && arduino_libraries_ready && f401_host_tools_ready
}

dependency_report() {
  if command_available "$ARDUINO_CLI"; then
    printf 'arduino-cli: %s\n' "$("$ARDUINO_CLI" version 2>/dev/null | head -n 1)"
  else
    printf 'arduino-cli: НЕ НАЙДЕН\n'
  fi
  if arduino_core_ready; then
    printf 'STM32 Arduino Core: %s\n' "$STM32_CORE_VERSION"
  else
    printf 'STM32 Arduino Core: нужен %s\n' "$STM32_CORE_VERSION"
  fi
  if arduino_libraries_ready; then
    printf 'LiquidCrystal: 1.0.7\nSTM32duino RTC: 1.9.0\n'
  else
    printf 'Библиотеки: нужны LiquidCrystal 1.0.7 и STM32duino RTC 1.9.0\n'
  fi
  if [ "$MCU" = f401 ]; then
    if [ -x "$PROJECT_ROOT/tools/build_f401_bundle.sh" ]; then
      printf 'F401 bundle builder: найден\n'
    else
      printf 'F401 bundle builder: НЕ НАЙДЕН\n'
    fi
    if ! f401_any_apps_requested; then
      printf 'Host C++17 compiler: не нужен (APP не запрошены)\n'
    elif command_available c++; then
      printf 'Host C++17 compiler: %s\n' "$(command -v c++ 2>/dev/null || printf '%s' c++)"
    else
      printf 'Host C++17 compiler: НЕ НАЙДЕН (нужен для упаковщика APP)\n'
    fi
  fi
  if locate_dfu_util; then
    printf 'DFU uploader: %s\n' "${DFU_CMD[0]}"
  else
    printf 'DFU uploader: не найден (появится вместе с STM32 Core)\n'
  fi
}

install_dependencies_worker() {
  "$ARDUINO_CLI" core update-index --additional-urls "$STM32_PACKAGE_URL" || return 1
  "$ARDUINO_CLI" core install "STMicroelectronics:stm32@$STM32_CORE_VERSION" \
    --additional-urls "$STM32_PACKAGE_URL" || return 1
  "$ARDUINO_CLI" lib update-index || return 1
  "$ARDUINO_CLI" lib install 'LiquidCrystal@1.0.7' || return 1
  "$ARDUINO_CLI" lib install 'STM32duino RTC@1.9.0'
}

install_dependencies() {
  if ! command_available "$ARDUINO_CLI"; then
    ui_msg 'Зависимости' 'arduino-cli не найден. Сначала установите Arduino CLI, затем снова запустите это меню.'
    return 1
  fi
  if run_with_progress 'Зависимости' 'Устанавливаю Arduino Core и библиотеки' \
      "$LAST_LOG" indeterminate install_dependencies_worker; then
    ui_msg 'Зависимости' 'STM32 Core 2.12.0 и библиотеки установлены.'
    return 0
  fi
  ui_log 'Ошибка установки' "$LAST_LOG"
  return 1
}

dfu_location_label() {
  local executable=$1 rest version system_name
  case "$executable" in
    */STM32Tools/*)
      rest=${executable#*/STM32Tools/}
      version=${rest%%/*}
      system_name=Linux
      case "$executable" in */macosx/*) system_name=macOS ;; esac
      printf 'Arduino STM32Tools %s · %s' "$version" "$system_name"
      ;;
    /opt/homebrew/*|/usr/local/Cellar/*|/usr/local/opt/*) printf '%s' 'Homebrew' ;;
    /home/linuxbrew/*|*/.linuxbrew/*) printf '%s' 'Linuxbrew' ;;
    *) printf '%s' "$executable" ;;
  esac
}

use_dfu_util() {
  local executable=$1
  case "$executable" in
    */*) ;;
    *) executable=$(command -v "$executable" 2>/dev/null) || return 1 ;;
  esac
  [ -x "$executable" ] || return 1
  case "${executable##*/}" in
    dfu-util|dfu-util.sh|dfu-util.exe) ;;
    *) return 1 ;;
  esac
  DFU_CMD=("$executable")
  DFU_STATUS="найден · $(dfu_location_label "$executable")"
  return 0
}

locate_dfu_util() {
  if [ "${#DFU_CMD[@]}" -gt 0 ] && [ -x "${DFU_CMD[0]}" ]; then return 0; fi
  DFU_CMD=()
  DFU_STATUS='не найден'

  if [ -n "${MK61_DFU_UTIL:-}" ] && use_dfu_util "$MK61_DFU_UTIL"; then return 0; fi
  if [ -n "$DFU_UTIL_PATH" ] && use_dfu_util "$DFU_UTIL_PATH"; then return 0; fi
  if command -v dfu-util >/dev/null 2>&1; then
    use_dfu_util "$(command -v dfu-util)"
    return 0
  fi

  local candidate discovered= user_home=${HOME:-}
  for candidate in \
      /opt/homebrew/bin/dfu-util \
      /opt/homebrew/opt/dfu-util/bin/dfu-util \
      /usr/local/bin/dfu-util \
      /usr/local/opt/dfu-util/bin/dfu-util \
      /opt/local/bin/dfu-util \
      /usr/bin/dfu-util \
      /bin/dfu-util \
      /home/linuxbrew/.linuxbrew/bin/dfu-util \
      /home/linuxbrew/.linuxbrew/opt/dfu-util/bin/dfu-util; do
    [ -x "$candidate" ] && discovered=$candidate
  done

  if [ -n "$user_home" ]; then
    for candidate in \
        "$user_home"/.linuxbrew/bin/dfu-util \
        "$user_home"/.linuxbrew/opt/dfu-util/bin/dfu-util \
        "$user_home"/Library/Arduino*/packages/STMicroelectronics/tools/STM32Tools/*/dfu-util.sh \
        "$user_home"/.arduino*/packages/STMicroelectronics/tools/STM32Tools/*/dfu-util.sh \
        "$user_home"/Library/Arduino*/packages/STMicroelectronics/tools/STM32Tools/*/macosx/dfu-util \
        "$user_home"/.arduino*/packages/STMicroelectronics/tools/STM32Tools/*/linux*/dfu-util \
        "$user_home"/.arduino*/packages/STMicroelectronics/tools/STM32Tools/*/linux*/*/dfu-util \
        "$user_home"/.local/share/arduino*/packages/STMicroelectronics/tools/STM32Tools/*/linux*/dfu-util \
        "$user_home"/.local/share/arduino*/packages/STMicroelectronics/tools/STM32Tools/*/linux*/*/dfu-util \
        "$user_home"/.var/app/*/data/arduino*/packages/STMicroelectronics/tools/STM32Tools/*/dfu-util.sh \
        "$user_home"/.var/app/*/data/arduino*/packages/STMicroelectronics/tools/STM32Tools/*/linux*/dfu-util \
        "$user_home"/.var/app/*/data/arduino*/packages/STMicroelectronics/tools/STM32Tools/*/linux*/*/dfu-util \
        "$user_home"/snap/arduino*/current/.arduino*/packages/STMicroelectronics/tools/STM32Tools/*/dfu-util.sh \
        "$user_home"/snap/arduino*/current/.arduino*/packages/STMicroelectronics/tools/STM32Tools/*/linux*/*/dfu-util; do
      [ -x "$candidate" ] && discovered=$candidate
    done
  fi

  if [ -n "$discovered" ]; then
    use_dfu_util "$discovered"
    return 0
  fi
  return 1
}

configure_dfu_util() {
  if locate_dfu_util; then
    if [ -z "${MK61_DFU_UTIL:-}" ] && [ "$DFU_UTIL_PATH" != "${DFU_CMD[0]}" ]; then
      DFU_UTIL_PATH=${DFU_CMD[0]}
      save_config || true
    fi
    return 0
  fi
  local entered expanded
  local help_text='Утилита dfu-util не найдена. Укажите полный путь к исполняемому файлу.

macOS: /opt/homebrew/bin/dfu-util, /usr/local/bin/dfu-util и ~/Library/Arduino15/packages/STMicroelectronics/tools/STM32Tools/<version>/macosx/dfu-util.

Linux: /usr/bin/dfu-util, /usr/local/bin/dfu-util, /home/linuxbrew/.linuxbrew/bin/dfu-util и ~/.arduino15/packages/STMicroelectronics/tools/STM32Tools/<version>/linux/<arch>/dfu-util.'
  while true; do
    entered=$(ui_input 'DFU uploader' "$help_text" '') || return 1
    [ -n "$entered" ] || return 1
    expanded=$entered
    case "$expanded" in
      '~/'*) expanded="${HOME:-}/${expanded#\~/}" ;;
    esac
    if use_dfu_util "$expanded"; then
      DFU_UTIL_PATH=$expanded
      save_config || true
      ui_msg 'DFU uploader' "dfu-util найден и сохранён:

$DFU_UTIL_PATH"
      return 0
    fi
    ui_msg 'DFU uploader' "Это не исполняемый dfu-util (ожидается dfu-util или dfu-util.sh):

$expanded"
  done
}

dfu_listing() {
  locate_dfu_util || return 1
  "${DFU_CMD[@]}" -l 2>&1
}

dfu_present() {
  local listing
  listing=$(dfu_listing) || true
  printf '%s\n' "$listing" | grep -Eiq '\[0483:df11\]|0483:df11'
}

list_cdc_ports() {
  command_available "$ARDUINO_CLI" || return 0
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
      if (address != "" && tolower(vid) == "0483" && tolower(pid) == "5740") print address
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

monitor_exchange() {
  local port=$1
  local command=$2
  {
    sleep 0.15
    printf '%s\r\n' "$command"
    sleep 1
  } | "$ARDUINO_CLI" monitor --quiet --port "$port" --config baudrate=115200 2>&1
}

recognize_profile_from_version() {
  case "$1" in
    *MK61s-Classic-V2*) printf '%s' classic-v2 ;;
    *MK61s-Classic-V3*) printf '%s' classic-v3 ;;
    *MK61s-40th*)       printf '%s' 40th ;;
    *) return 1 ;;
  esac
}

detect_device() {
  DETECTED_PORT=
  DETECTED_VERSION=
  if dfu_present; then
    DEVICE_STATUS='STM32 DFU 0483:df11 · готов к загрузке'
    return 0
  fi

  local port response detected_profile
  while IFS= read -r port; do
    [ -n "$port" ] || continue
    response=$(monitor_exchange "$port" ver) || true
    case "$response" in
      *MK61s*)
        DETECTED_PORT=$port
        DETECTED_VERSION=$(printf '%s\n' "$response" | grep 'MK61s' | tail -n 1)
        detected_profile=$(recognize_profile_from_version "$response") || detected_profile=
        if [ -n "$detected_profile" ]; then
          PROFILE=$detected_profile
          hardware_from_profile "$PROFILE" || true
          save_config
          DEVICE_STATUS="MK61s на $port · $(profile_label "$PROFILE")"
        else
          DEVICE_STATUS="MK61s на $port · mini-профиль не кодируется в ver"
        fi
        return 0
        ;;
    esac
  done < <(list_cdc_ports)

  DEVICE_STATUS='устройство не найдено'
  return 1
}

prepare_and_compile_f411_worker() {
  local profile=$1
  local sketch_dir="$BUILD_ROOT/sketch/$profile/mk61s-M"
  local build_dir flags signature artifact source_artifact
  flags=$(all_compile_flags "$profile") || return 1
  signature=$(printf '%s\n' "$flags" | cksum | awk '{print $1}')
  build_dir="$BUILD_ROOT/build/$profile-$signature"
  artifact="$OUTPUT_DIR/$(profile_artifact_name "$profile" f411)"

  rm -rf "$BUILD_ROOT/sketch/$profile"
  mkdir -p "$sketch_dir" "$build_dir" "$OUTPUT_DIR" || return 1
  cp -R "$PROJECT_ROOT/code/." "$sketch_dir/" || return 1

  "$ARDUINO_CLI" compile \
    --fqbn "$FQBN_F411" \
    --build-path "$build_dir" \
    --build-property "compiler.cpp.extra_flags=$flags" \
    "$sketch_dir" || return 1

  source_artifact="$build_dir/mk61s-M.ino.bin"
  [ -s "$source_artifact" ] || {
    printf 'Build succeeded but %s was not created.\n' "$source_artifact" >&2
    return 1
  }
  cp "$source_artifact" "$artifact.tmp" || return 1
  mv "$artifact.tmp" "$artifact" || return 1
  printf '%s\n' "$flags" > "$artifact.flags.tmp" || return 1
  mv "$artifact.flags.tmp" "$artifact.flags"
}

prepare_and_compile_f401_worker() {
  local profile=$1
  env \
    MK61_ARDUINO_CLI="$ARDUINO_CLI" \
    MK61_ENABLE_FOCAL="$ENABLE_FOCAL" \
    MK61_ENABLE_TINYBASIC="$ENABLE_TINYBASIC" \
    MK61_ENABLE_WBMP_VIEWER="$ENABLE_WBMP_VIEWER" \
    MK61_ENABLE_USB_SCREEN="$ENABLE_USB_SCREEN" \
    MK61_ENABLE_EXTENDED_FONT_SETTINGS="$ENABLE_EXTENDED_FONT_SETTINGS" \
    MK61_USER_EXPLORER_SHORTCUT="$ENABLE_USER_EXPLORER" \
    MK61_MATH_BACKEND="$ENABLE_CORE_MATH" \
    "$PROJECT_ROOT/tools/build_f401_bundle.sh" \
      --profile "$profile" \
      --output-dir "$OUTPUT_DIR" \
      --build-root "$BUILD_ROOT/f401/$profile"
}

prepare_and_compile_worker() {
  if [ "$MCU" = f401 ]; then
    prepare_and_compile_f401_worker "$1"
  else
    prepare_and_compile_f411_worker "$1"
  fi
}

expected_system_app_names() {
  [ "$ENABLE_FOCAL" -eq 1 ] && printf '%s\n' FOCAL.APP
  [ "$ENABLE_TINYBASIC" -eq 1 ] && printf '%s\n' BASIC.APP
  [ "$ENABLE_WBMP_VIEWER" -eq 1 ] && printf '%s\n' WBMP.APP
}

all_system_app_names() {
  printf '%s\n' FOCAL.APP BASIC.APP WBMP.APP
}

system_app_enabled() {
  case "$1" in
    FOCAL.APP) [ "$ENABLE_FOCAL" -eq 1 ] ;;
    BASIC.APP) [ "$ENABLE_TINYBASIC" -eq 1 ] ;;
    WBMP.APP) [ "$ENABLE_WBMP_VIEWER" -eq 1 ] ;;
    *) return 1 ;;
  esac
}

build_selected() {
  ensure_hardware_profile || return 1
  if ! build_dependencies_ready; then
    if [ "$INTERACTIVE" -eq 1 ]; then
      ui_msg 'Не хватает зависимостей' "$(dependency_report)"
    else
      dependency_report >&2
    fi
    return 1
  fi

  if run_with_progress 'Сборка прошивки' "Собираю $(profile_label "$PROFILE")" \
      "$LAST_LOG" indeterminate prepare_and_compile_worker "$PROFILE"; then
    local artifact size bundle system_apps app_count app_names
    artifact=$(profile_artifact_path "$PROFILE")
    if [ ! -s "$artifact" ]; then
      printf 'Build succeeded but %s was not created.\n' "$artifact" >> "$LAST_LOG"
      if [ "$INTERACTIVE" -eq 1 ]; then ui_log 'Ошибка сборки' "$LAST_LOG"
      else tail -n 60 "$LAST_LOG" >&2
      fi
      return 1
    fi
    size=$(wc -c < "$artifact" | tr -d '[:space:]')
    if [ "$MCU" = f401 ]; then
      bundle=$(profile_bundle_dir "$PROFILE")
      system_apps="$bundle/System"
      app_names=$(expected_system_app_names)
      app_count=$(printf '%s\n' "$app_names" | sed '/^$/d' | wc -l | tr -d '[:space:]')
      if [ "$INTERACTIVE" -eq 1 ]; then
        if [ "$app_count" -gt 0 ]; then
          ui_msg 'Комплект F401 собран' "Профиль: $(profile_label "$PROFILE")

$(compile_options_details)

Комплект: $bundle
Resident: $artifact
Размер resident: $size байт
System APP:
$app_names

После прошивки выполните пункт «Шаг 2 · Установить System APP»."
        else
          ui_msg 'Комплект F401 собран' "Профиль: $(profile_label "$PROFILE")

$(compile_options_details)

Комплект: $bundle
Resident: $artifact
Размер resident: $size байт

Все System APP выключены. На чистом C5 второй шаг не требуется;
если там остались прежние системные APP, второй шаг удалит только их."
        fi
      else
        printf 'Built F401 bundle: %s\n' "$bundle"
        printf 'Resident: %s (%s bytes)\n' "$artifact" "$size"
        if [ "$app_count" -gt 0 ]; then
          printf 'System APP:\n%s\n' "$app_names"
          printf 'Step 2: on MK61s select Menu -> USB Disk, then run --install-apps.\n'
        else
          printf 'All System APP are disabled; step 2 is only needed to remove previously installed canonical System APP.\n'
        fi
      fi
      return 0
    fi
    if [ "$INTERACTIVE" -eq 1 ]; then
      ui_msg 'Сборка завершена' "Профиль: $(profile_label "$PROFILE")

$(compile_options_details)

Файл: $artifact
Размер: $size байт"
    else
      printf 'Built: %s (%s bytes)\n' "$artifact" "$size"
    fi
    return 0
  fi

  if [ "$INTERACTIVE" -eq 1 ]; then ui_log 'Ошибка сборки' "$LAST_LOG"
  else tail -n 60 "$LAST_LOG" >&2
  fi
  return 1
}

validate_f401_bundle() {
  local bundle artifact flags_file actual_flags expected_flags source app
  bundle=$(profile_bundle_dir "$PROFILE") || return 1
  artifact=$(profile_artifact_path "$PROFILE") || return 1
  flags_file="$bundle/build.flags"
  source="$bundle/System"
  if [ ! -s "$artifact" ] || [ ! -r "$flags_file" ]; then
    printf 'F401 bundle is missing. Build the selected profile first: %s\n' \
      "$bundle" >&2
    return 1
  fi
  IFS= read -r actual_flags < "$flags_file" || actual_flags=
  expected_flags=$(all_compile_flags "$PROFILE") || return 1
  if [ "$actual_flags" != "$expected_flags" ]; then
    printf 'F401 bundle flags do not match the current selection. Rebuild it first.\n' >&2
    return 1
  fi
  for app in $(expected_system_app_names); do
    if [ ! -s "$source/$app" ]; then
      printf 'F401 bundle is incomplete: %s is missing.\n' "$source/$app" >&2
      return 1
    fi
  done
}

find_c5_mount() {
  local candidate user_name=${USER:-}
  if [ -n "${MK61_C5_MOUNT:-}" ]; then
    [ -d "$MK61_C5_MOUNT" ] || return 1
    printf '%s' "$MK61_C5_MOUNT"
    return 0
  fi
  for candidate in \
      '/Volumes/MK61S C5' \
      "${user_name:+/media/$user_name/MK61S C5}" \
      "${user_name:+/run/media/$user_name/MK61S C5}" \
      '/media/MK61S C5' \
      '/mnt/MK61S C5'; do
    [ -n "$candidate" ] && [ -d "$candidate" ] || continue
    printf '%s' "$candidate"
    return 0
  done
  return 1
}

wait_for_c5_mount_worker() {
  local attempts=120
  while [ "$attempts" -gt 0 ]; do
    if find_c5_mount >/dev/null; then return 0; fi
    attempts=$((attempts - 1))
    sleep 0.5
  done
  printf 'USB disk "MK61S C5" was not found within 60 seconds.\n' >&2
  return 1
}

copy_system_apps_worker() {
  local source=$1 mount=$2 target="$2/System" app
  mkdir -p "$target" || return 1
  for app in $(expected_system_app_names); do
    printf 'Copying %s...\n' "$app"
    cp -f "$source/$app" "$target/$app" || return 1
  done
  for app in $(all_system_app_names); do
    if ! system_app_enabled "$app"; then
      printf 'Removing disabled %s...\n' "$app"
      rm -f "$target/$app" || return 1
    fi
  done
  sync || return 1
  for app in $(expected_system_app_names); do
    cmp -s "$source/$app" "$target/$app" || {
      printf 'Verification failed: %s\n' "$target/$app" >&2
      return 1
    }
  done
  for app in $(all_system_app_names); do
    if ! system_app_enabled "$app" && [ -e "$target/$app" ]; then
      printf 'Removal verification failed: %s\n' "$target/$app" >&2
      return 1
    fi
  done
}

install_system_apps() {
  ensure_hardware_profile || return 1
  if [ "$MCU" != f401 ]; then
    if [ "$INTERACTIVE" -eq 1 ]; then
      ui_msg 'System APP' 'Второй шаг нужен только для STM32F401CC. На F411 системные компоненты находятся во внутренней Flash.'
    else
      printf 'Error: --install-apps is only valid for --mcu f401.\n' >&2
    fi
    return 1
  fi
  if ! validate_f401_bundle; then
    if [ "$INTERACTIVE" -eq 1 ]; then
      ui_msg 'Комплект не готов' "Комплект F401 отсутствует, неполон или собран с другими ключами.

Сначала выполните «Только собрать» либо «Собрать и прошить»."
    fi
    return 1
  fi

  local instructions='После прошивки дождитесь запуска MK61s.

На калькуляторе откройте Меню → USB-диск.
Не нажимайте ESC до сообщения об успешной проверке файлов.

После подтверждения инструмент будет ждать диск «MK61S C5» 60 секунд.'
  if [ "$INTERACTIVE" -eq 1 ]; then
    ui_msg 'Шаг 2 · System APP' "$instructions"
  else
    printf '%s\n' "$instructions"
  fi

  if ! run_with_progress 'USB-диск C5' 'Жду MK61S C5' "$LAST_LOG" \
      indeterminate wait_for_c5_mount_worker; then
    if [ "$INTERACTIVE" -eq 1 ]; then ui_log 'USB-диск не найден' "$LAST_LOG"
    else tail -n 20 "$LAST_LOG" >&2
    fi
    return 1
  fi

  local mount source app_names
  mount=$(find_c5_mount) || {
    printf 'USB disk disappeared before copying.\n' >&2
    return 1
  }
  source="$(profile_bundle_dir "$PROFILE")/System"
  if ! run_with_progress 'System APP' 'Копирую и проверяю файлы' "$LAST_LOG" \
      indeterminate copy_system_apps_worker "$source" "$mount"; then
    if [ "$INTERACTIVE" -eq 1 ]; then ui_log 'Ошибка установки APP' "$LAST_LOG"
    else tail -n 40 "$LAST_LOG" >&2
    fi
    return 1
  fi

  app_names=$(expected_system_app_names)
  if f401_system_apps_enabled; then
    DEVICE_STATUS='System APP синхронизированы и проверены'
  else
    DEVICE_STATUS='System APP удалены по выключенным ключам'
  fi
  if [ "$INTERACTIVE" -eq 1 ]; then
    if f401_system_apps_enabled; then
      ui_msg 'Шаг 2 завершён' "В каталоге $mount/System синхронизированы и побайтно проверены:
$app_names

Теперь можно выйти из режима USB-диска клавишей ESC на MK61s."
    else
      ui_msg 'Шаг 2 завершён' "Из каталога $mount/System удалены выключенные канонические System APP.
Другие файлы C5 не изменялись.

Теперь можно выйти из режима USB-диска клавишей ESC на MK61s."
    fi
  else
    if f401_system_apps_enabled; then
      printf 'Synchronized and verified in %s/System:\n%s\n' "$mount" "$app_names"
    else
      printf 'Removed disabled canonical System APP from %s/System.\n' "$mount"
    fi
    printf 'You may now leave USB Disk mode with ESC on MK61s.\n'
  fi
}

wait_for_dfu_worker() {
  local attempts=60
  while [ "$attempts" -gt 0 ]; do
    if dfu_present; then return 0; fi
    attempts=$((attempts - 1))
    sleep 0.5
  done
  printf 'STM32 DFU 0483:df11 was not found within 30 seconds.\n' >&2
  return 1
}

ensure_dfu_ready() {
  locate_dfu_util || {
    printf 'DFU uploader not found; install STM32 Arduino Core %s.\n' "$STM32_CORE_VERSION" >&2
    return 1
  }
  if dfu_present; then return 0; fi

  detect_device >/dev/null 2>&1 || true
  if [ -n "$DETECTED_PORT" ]; then
    if [ "$INTERACTIVE" -eq 0 ]; then
      printf 'Requesting DFU mode on %s…\n' "$DETECTED_PORT"
    fi
    monitor_exchange "$DETECTED_PORT" dfu >/dev/null 2>&1 || true
    local quick_attempts=20
    while [ "$quick_attempts" -gt 0 ]; do
      if dfu_present; then return 0; fi
      quick_attempts=$((quick_attempts - 1))
      sleep 0.25
    done
  fi

  if [ "$INTERACTIVE" -eq 1 ]; then
    ui_msg 'Нужен режим DFU' 'Зажмите ESC на калькуляторе и нажмите RESET (или подключите USB с зажатым ESC). Затем отпустите ESC. Меню будет ждать загрузчик 30 секунд.'
  else
    printf 'Enter DFU: hold ESC and press RESET (waiting 30 seconds).\n'
  fi
  if run_with_progress 'Поиск DFU' 'Жду STM32 DFU 0483:df11' "$LAST_LOG" \
      indeterminate wait_for_dfu_worker; then
    DEVICE_STATUS='STM32 DFU 0483:df11 · готов к загрузке'
    return 0
  fi
  if [ "$INTERACTIVE" -eq 1 ]; then ui_log 'DFU не найден' "$LAST_LOG"
  else tail -n 20 "$LAST_LOG" >&2
  fi
  return 1
}

upload_worker() {
  local artifact=$1
  "${DFU_CMD[@]}" -d 0483:df11 -a 0 -s 0x08000000:leave -D "$artifact"
}

upload_selected() {
  ensure_hardware_profile || return 1

  if [ "$INTERACTIVE" -eq 1 ]; then
    ui_yesno 'Собрать и прошить' "Профиль: $(profile_label "$PROFILE")
Контроллер: $(mcu_label "$MCU")
Метод: USB DFU

$(compile_options_details)

Собрать согласованный комплект и загрузить resident-прошивку в устройство?" || return 1
  fi

  build_selected || return 1
  ensure_dfu_ready || return 1
  local artifact
  artifact=$(profile_artifact_path "$PROFILE")
  if run_with_progress 'Загрузка прошивки' 'Записываю и перезапускаю STM32' \
      "$LAST_LOG" measured upload_worker "$artifact"; then
    DEVICE_STATUS='прошивка загружена; устройство перезапущено'
    if [ "$MCU" = f401 ] && f401_system_apps_enabled; then
      if [ "$INTERACTIVE" -eq 1 ]; then
        ui_msg 'Шаг 1 завершён' "Resident-прошивка F401 загружена.

Дождитесь запуска MK61s, откройте на нём Меню → USB-диск и выполните пункт «Шаг 2 · Установить System APP»."
      else
        printf 'Uploaded resident: %s\n' "$artifact"
        printf 'Step 2: on MK61s select Menu -> USB Disk, then run --install-apps.\n'
      fi
    elif [ "$INTERACTIVE" -eq 1 ]; then
      ui_msg 'Готово' "Прошивка загружена.

$(profile_label "$PROFILE")"
    else
      printf 'Uploaded: %s\n' "$artifact"
    fi
    return 0
  fi
  if [ "$INTERACTIVE" -eq 1 ]; then ui_log 'Ошибка загрузки' "$LAST_LOG"
  else tail -n 60 "$LAST_LOG" >&2
  fi
  return 1
}

show_dependencies() {
  ui_msg 'Зависимости' "$(dependency_report)"
}

interactive_main() {
  INTERACTIVE=1
  select_ui
  native_screen_enter
  load_config
  configure_dfu_util || true
  DEVICE_STATUS='не проверялось · пункт «Найти устройство»'
  local main_selection=upload
  while true; do
    local selection platform_text screen_text target_text upload_label install_label
    platform_text=$(platform_label "$HARDWARE_PLATFORM")
    screen_text=$(screen_label "$SCREEN_KIND")
    target_text=$(mcu_label "$MCU")
    if [ "$MCU" = f401 ]; then
      upload_label='▲ Шаг 1 · Собрать и прошить'
      install_label='↓ Шаг 2 · Установить System APP'
    else
      upload_label='▲ Собрать и прошить'
      install_label='↓ System APP · только F401'
    fi
    if platform_valid "$HARDWARE_PLATFORM" && screen_valid "$SCREEN_KIND" && \
        ! hardware_compatible "$HARDWARE_PLATFORM" "$SCREEN_KIND"; then
      screen_text="$screen_text · несовместим"
    fi
    selection=$(ui_menu 'MK61s · прошивка' "Платформа: $platform_text
Экран: $screen_text
Ключи: $(compile_options_summary)
Цель: $target_text · USB DFU
DFU: $DFU_STATUS
Устройство: $DEVICE_STATUS" "$main_selection" \
      upload  "$upload_label" \
      build   '⚒ Только собрать' \
      install_apps "$install_label" \
      mcu     '◉ Контроллер' \
      platform '◉ Платформа' \
      screen   '◉ Экран' \
      options '☑ Ключи компиляции' \
      detect  '⌕ Найти устройство' \
      deps    '✓ Проверить зависимости' \
      setup   '↓ Установить Arduino-зависимости' \
      log     '≡ Последний журнал' \
      quit    '× Выход') || break
    main_selection=$selection
    case "$selection" in
      upload) upload_selected || true ;;
      build) build_selected || true ;;
      install_apps) install_system_apps || true ;;
      mcu) choose_mcu || true ;;
      platform) choose_platform || true ;;
      screen) choose_screen || true ;;
      options) choose_compile_options || true ;;
      detect)
        if detect_device; then ui_msg 'Устройство' "$DEVICE_STATUS"
        else ui_msg 'Устройство' 'MK61s и STM32 DFU не найдены.'
        fi
        ;;
      deps) show_dependencies ;;
      setup) install_dependencies || true ;;
      log) ui_log 'Последний журнал' "$LAST_LOG" ;;
      quit) break ;;
    esac
  done
  native_screen_leave
}

ACTION=tui
FORCE_PLAIN=0
while [ "$#" -gt 0 ]; do
  case "$1" in
    --mcu)
      [ "$#" -ge 2 ] || { printf 'Error: --mcu needs f411 or f401.\n' >&2; exit 2; }
      MCU=$2
      CLI_MCU=1
      shift 2
      ;;
    --profile)
      [ "$#" -ge 2 ] || { printf 'Error: --profile needs an ID.\n' >&2; exit 2; }
      PROFILE=$2
      CLI_PROFILE=1
      shift 2
      ;;
    --build|--upload|--install-apps|--detect|--setup|--list-profiles|--show-config)
      ACTION=${1#--}
      shift
      ;;
    --plain)
      FORCE_PLAIN=1
      shift
      ;;
    -h|--help)
      usage
      exit 0
      ;;
    *)
      printf 'Error: unknown option: %s\n' "$1" >&2
      usage >&2
      exit 2
      ;;
  esac
done

if ! mcu_valid "$MCU"; then
  printf 'Error: unsupported MCU: %s (expected f411 or f401).\n' "$MCU" >&2
  exit 2
fi

if [ -n "$PROFILE" ] && ! profile_valid "$PROFILE"; then
  printf 'Error: unsupported profile: %s\n' "$PROFILE" >&2
  exit 2
fi

if [ "$FORCE_PLAIN" -eq 1 ]; then MK61_UI=plain; export MK61_UI; fi

case "$ACTION" in
  tui)
    if [ ! -t 0 ]; then
      printf 'Error: interactive mode needs a terminal. Use --build/--upload/--install-apps/--detect.\n' >&2
      exit 2
    fi
    interactive_main
    ;;
  list-profiles)
    list_profiles
    ;;
  build)
    INTERACTIVE=0
    select_ui
    load_config
    build_selected
    ;;
  upload)
    INTERACTIVE=0
    select_ui
    load_config
    upload_selected
    ;;
  install-apps)
    INTERACTIVE=0
    select_ui
    load_config
    install_system_apps
    ;;
  detect)
    INTERACTIVE=0
    select_ui
    load_config
    detect_device || true
    printf '%s\n' "$DEVICE_STATUS"
    [ -n "$DETECTED_VERSION" ] && printf '%s\n' "$DETECTED_VERSION"
    ;;
  show-config)
    load_config
    show_config
    ;;
  setup)
    INTERACTIVE=0
    select_ui
    if ! command_available "$ARDUINO_CLI"; then
      printf 'Error: arduino-cli is not installed.\n' >&2
      exit 1
    fi
    if run_with_progress 'Dependencies' 'Installing Arduino dependencies' "$LAST_LOG" \
        indeterminate install_dependencies_worker; then
      dependency_report
    else
      tail -n 60 "$LAST_LOG" >&2
      exit 1
    fi
    ;;
esac

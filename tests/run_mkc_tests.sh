#!/usr/bin/env bash
set -euo pipefail

root=$(cd "$(dirname "$0")/.." && pwd)
work=$(mktemp -d "${TMPDIR:-/tmp}/mkc-test.XXXXXX")
cleanup_test() {
  rm -rf "$work"
}
trap cleanup_test EXIT

mkdir -p "$work/local/Good" "$work/device/Programs" "$work/session" \
  "$work/module-limits" "$work/preflight-bad"
printf '2+2\n' > "$work/local/demo.foc"
printf '001\n' > "$work/local/Good/program.m61"
printf 'raw\n' > "$work/local/blocked.bin"
printf 'raw\n' > "$work/preflight-bad/blocked.bin"
printf '\000\001\177\200\377' > "$work/local/binary.wbmp"
printf '\000\000\010\002\017\360' > "$work/local/preview.wbmp"
dd if=/dev/zero of="$work/local/large.tbi" bs=1 count=1537 2>/dev/null
dd if=/dev/zero of="$work/preflight-bad/large.tbi" bs=1 count=1537 2>/dev/null
dd if=/dev/zero of="$work/local/chunked.m61" bs=1 count=100 2>/dev/null
dd if=/dev/zero of="$work/local/FOCAL.MOD" bs=1 count=64 2>/dev/null
dd if=/dev/zero of="$work/local/OTHER.MOD" bs=1 count=64 2>/dev/null
dd if=/dev/zero of="$work/module-limits/WBMP.MOD" bs=1 count=4097 2>/dev/null
dd if=/dev/zero of="$work/module-limits/BASIC.MOD" bs=1 count=63 2>/dev/null

test -x "$root/tools/mkc.cmd"
test -x "$root/tools/.mkc/mkc.sh"
test -f "$root/tools/.mkc/mkc.ps1"
test ! -e "$root/tools/mkc.sh"
test ! -e "$root/tools/mkc.ps1"
test "$("$root/tools/mkc.cmd" --classify "$work/local/demo.foc")" = supported
test "$("$root/tools/mkc.cmd" --classify "$work/local/Good")" = supported
test "$("$root/tools/mkc.cmd" --classify "$work/local/FOCAL.MOD")" = supported
test "$("$root/tools/mkc.cmd" --classify "$work/local/blocked.bin" || true)" = \
  'unsupported: формат не поддерживается'
test "$("$root/tools/mkc.cmd" --classify "$work/local/OTHER.MOD" || true)" = \
  'unsupported: допустимы только FOCAL.MOD, BASIC.MOD и WBMP.MOD'
case "$("$root/tools/mkc.cmd" --classify "$work/module-limits/WBMP.MOD" || true)" in
  'unsupported: слишком большой:'*) ;;
  *) echo 'mkc: oversized WBMP.MOD was accepted' >&2; exit 1 ;;
esac
case "$("$root/tools/mkc.cmd" --classify "$work/module-limits/BASIC.MOD" || true)" in
  'unsupported: слишком маленький:'*) ;;
  *) echo 'mkc: undersized BASIC.MOD was accepted' >&2; exit 1 ;;
esac
case "$("$root/tools/mkc.cmd" --classify "$work/local/large.tbi" || true)" in
  'unsupported: слишком большой:'*) ;;
  *) echo 'mkc: oversized file was accepted' >&2; exit 1 ;;
esac

MKC_SOURCE_ONLY=1 MKC_CONFIG_FILE="$work/config" source "$root/tools/.mkc/mkc.sh"
SESSION_DIR="$work/session"
MOCK_ROOT="$work/device"
shopt -s nullglob dotglob

remote_put_file "$work/local/demo.foc" /demo.foc
cmp "$work/local/demo.foc" "$work/device/demo.foc"
remote_get_file /demo.foc "$work/download.foc"
cmp "$work/local/demo.foc" "$work/download.foc"
remote_put_file "$work/local/FOCAL.MOD" /FOCAL.MOD
remote_get_file /FOCAL.MOD "$work/download.mod"
cmp "$work/local/FOCAL.MOD" "$work/download.mod"
file_to_hex "$work/local/binary.wbmp" > "$work/session/binary.hex"
hex_file_to_binary "$work/session/binary.hex" "$work/binary.roundtrip"
cmp "$work/local/binary.wbmp" "$work/binary.roundtrip"

# WBMP F3-preview декодирует Type 0 без ImageMagick в стандартный 1-bit BMP.
wbmp_to_bmp "$work/local/preview.wbmp" "$work/preview.bmp"
test "$(wc -c < "$work/preview.bmp" | tr -d '[:space:]')" = 70
test "$(od -An -tu1 -N2 "$work/preview.bmp" | awk '{$1=$1; print}')" = '66 77'
test "$(od -An -tu1 -j10 -N4 "$work/preview.bmp" | awk '{$1=$1; print}')" = '62 0 0 0'
wbmp_braille_preview "$work/local/preview.wbmp" "$work/preview.txt"
grep -q '8×2 · Braille preview' "$work/preview.txt"
test "$(sed -n '3p' "$work/preview.txt")" = '⠉⠉⠒⠒'
TERM_PROGRAM=iTerm.app; TMUX=
iterm_inline_images_supported
TMUX=/tmp/tmux-test
if iterm_inline_images_supported; then
  echo 'mkc: enabled raw iTerm images through unconfigured tmux' >&2
  exit 1
fi
unset TERM_PROGRAM TMUX

printf 'Unknown command: fsput begin /demo.foc 4 0\n' > "$work/old-firmware.txt"
exec 8< "$work/old-firmware.txt"
if wait_for_marker '@MKC:READY '; then
  echo 'mkc: old firmware was accepted as transfer-capable' >&2
  exit 1
fi
case "$STATUS_TEXT" in
  *'прошивка не поддерживает F3/F5'*) ;;
  *) echo "mkc: unclear old-firmware error: $STATUS_TEXT" >&2; exit 1 ;;
esac
exec 8<&-

# Реальный fsput идёт через arduino-cli monitor и STM32 CDC. Команда длиннее
# примерно 128 байт теряет хвост на некоторых сборках serial-monitor, поэтому
# передача должна резать файл на безопасные 48-байтные блоки.
chunk_crc=$(file_checksum "$work/local/chunked.m61")
{
  printf '@MKC:READY 100\n'
  printf '@MKC:ACK 48\n'
  printf '@MKC:ACK 96\n'
  printf '@MKC:ACK 100\n'
  printf '@MKC:DONE 100 %s\n' "$chunk_crc"
} > "$work/fsput.responses"
exec 7> "$work/fsput.commands"
exec 8< "$work/fsput.responses"
MONITOR_INPUT_FD=7
MONITOR_OUTPUT_FD=8
MOCK_ROOT=
remote_put_file "$work/local/chunked.m61" /chunked.m61
exec 7>&-
exec 8<&-
tr '\r' '\n' < "$work/fsput.commands" > "$work/fsput.commands.lines"
test "$(awk '$1 == "fsput" && $2 == "data" { print length($4) }' \
  "$work/fsput.commands.lines")" = "$(printf '96\n96\n8')"

# Потеря первой строки сразу после открытия CDC не должна превращаться в
# тихо усечённую правую панель: число в финале `ls` заставляет сделать retry.
{
  printf 'f\t4 B\tsecond.m61\n'
  printf '2 entries.\n'
  printf 'f\t3 B\tfirst.m61\n'
  printf 'f\t4 B\tsecond.m61\n'
  printf '2 entries.\n'
} > "$work/list-retry.responses"
exec 7> "$work/list-retry.commands"
exec 8< "$work/list-retry.responses"
MONITOR_INPUT_FD=7
MONITOR_OUTPUT_FD=8
remote_list_raw / "$work/list-retry.output"
exec 7>&-
exec 8<&-
test "$(cat "$work/list-retry.output")" = \
  "$(printf 'f\t3\tfirst.m61\nf\t4\tsecond.m61')"
test "$(tr '\r' '\n' < "$work/list-retry.commands" | grep -c '^ls "/"$')" = 2

# Произвольная команда правой панели должна отделять старый prompt, эхо
# команды и следующий prompt от текста, который увидит встроенный просмотрщик.
{
  printf '/> df\n'
  printf 'Flash: 16777216 bytes\n'
  printf 'Nodes: 9 used\n'
  printf '/> \n'
} > "$work/terminal.responses"
exec 7> "$work/terminal.commands"
exec 8< "$work/terminal.responses"
MONITOR_INPUT_FD=7
MONITOR_OUTPUT_FD=8
REMOTE_PATH=/
remote_capture_command df "$work/terminal.output"
exec 7>&-
exec 8<&-
test "$(cat "$work/terminal.output")" = "$(printf 'Flash: 16777216 bytes\nNodes: 9 used')"
test "$REMOTE_CAPTURE_PATH" = /
test "$(tr '\r' '\n' < "$work/terminal.commands")" = df
MOCK_ROOT="$work/device"

# Исполнитель нижней строки однозначно определяется активной панелью.
exec 9> "$work/command.draw"
run_local_command() { printf 'local:%s\n' "$1" >> "$work/command.routes"; }
run_remote_command() { printf 'remote:%s\n' "$1" >> "$work/command.routes"; }
ACTIVE_PANEL=L
command_set_text 'printf local'
execute_command_line
ACTIVE_PANEL=R
command_set_text help
execute_command_line
exec 9>&-
test "$(cat "$work/command.routes")" = "$(printf 'local:printf local\nremote:help')"

plan_reset
if plan_local_tree "$work/preflight-bad" /Imported; then
  echo 'mkc: a directory containing an unsupported file was accepted' >&2
  exit 1
fi
case "$PLAN_ERROR" in blocked.bin:*|large.tbi:*) ;;
  *) echo "mkc: unexpected preflight error: $PLAN_ERROR" >&2; exit 1 ;;
esac

plan_reset
plan_local_tree "$work/local/Good" /Good
test "${#PLAN_KINDS[@]}" -eq 2
test "$PLAN_TOTAL" -eq 4

plan_reset
plan_local_tree "$work/local/FOCAL.MOD" /FOCAL.MOD
test "${#PLAN_KINDS[@]}" -eq 1
test "$PLAN_TOTAL" -eq 64
plan_reset
if plan_local_tree "$work/local/FOCAL.MOD" /Modules/FOCAL.MOD; then
  echo 'mkc: loadable module was accepted outside the device root' >&2
  exit 1
fi
case "$PLAN_ERROR" in
  *'только в корне под своим фиксированным именем'*) ;;
  *) echo "mkc: unclear module destination error: $PLAN_ERROR" >&2; exit 1 ;;
esac

# iTerm2-viewer действительно посылает картинку внутрь заданной области окна.
exec 9> "$work/iterm.protocol"
read_key() { printf esc; }
draw_screen() { :; }
drain_pending_input() { :; }
draw_function_bar() { :; }
show_wbmp_iterm preview.wbmp "$work/preview.bmp"
exec 9>&-
LC_ALL=C grep -a -q ']1337;File=size=70;width=74;height=19;preserveAspectRatio=1;inline=1:' \
  "$work/iterm.protocol"

if [ "${MKC_SKIP_EXPECT_TESTS:-0}" != 1 ] && command -v expect >/dev/null 2>&1; then
  export MKC_TEST_LOCAL="$work/local/Good"
  export MKC_TEST_DEVICE="$work/device"
  expect -c '
    set timeout 10
    log_user 0
    proc must_see {text} {
      expect {
        -exact $text { return }
        timeout { puts stderr "mkc expect timeout: $text"; exit 1 }
        eof { puts stderr "mkc exited before: $text"; exit 1 }
      }
    }
    spawn env TERM=xterm-256color MKC_CONFIG_FILE=/dev/null \
      "'"$root"'/tools/mkc.cmd" --mock $env(MKC_TEST_DEVICE) \
      --local $env(MKC_TEST_LOCAL)
    after 400

    # Терминал macOS передаёт F1..F4 как SS3 (Esc O P..S). Эти проверки не дают
    # анализатору ошибочно принять префикс `O` за конечный байт.
    send "\033OP"
    must_see "MKC — файловый менеджер MK61s"
    must_see "Esc/F3 — close"
    must_see "Quit"
    send "\033"
    must_see "Good> "

    send "\033\[B"
    must_see "program.m61"
    # Повторная последовательность F3 не должна открыть и сразу закрыть просмотр.
    send "\033OR\033OR"
    must_see "001"
    must_see "Esc/F3 — close"
    must_see "Quit"
    send "\033\[B"
    must_see "001"
    must_see "Esc/F3 — close"
    must_see "Quit"
    send "\033"
    must_see "Good> "

    # F5 должна открыть модальный диалог копирования, а одиночный Esc — отменить его.
    send "\033\[15~"
    must_see "Copy 1 item(s) to MK61s:"
    send "\033"
    must_see "Good> "

    # Tab меняет и активную панель, и исполнителя нижней строки.
    send "\t"
    must_see "MK61s:/> "
    send "help"
    send "\r"
    must_see "Mock MK61s terminal"
    must_see "Commands are routed to the right panel."
    must_see "Esc/F3 — close"
    send "\033"
    must_see "MK61s:/> "
    send "\017"
    must_see "Mock MK61s terminal"
    send "\033"
    must_see "program.m61"
    send "\033\[21~"
    expect { eof {} timeout { exit 1 } }
    catch wait result
    exit [lindex $result 3]
  '
fi

if [ "${MKC_SKIP_EXPECT_TESTS:-0}" != 1 ] && command -v expect >/dev/null 2>&1 &&
   command -v pwsh >/dev/null 2>&1; then
  export MKC_TEST_LOCAL="$work/local/Good"
  export MKC_TEST_DEVICE="$work/device"
  expect -c '
    # После полного sanitizer-набора холодный запуск pwsh иногда занимает
    # больше десяти секунд; это не тайм-аут проверяемого интерфейса MKC.
    set timeout 20
    log_user 0
    proc must_see {text} {
      expect {
        -exact $text { return }
        timeout { puts stderr "mkc PowerShell expect timeout: $text"; exit 1 }
        eof { puts stderr "mkc PowerShell exited before: $text"; exit 1 }
      }
    }
    spawn env TERM=xterm-256color MKC_CONFIG_FILE=/dev/null \
      pwsh -NoLogo -NoProfile -File "'"$root"'/tools/.mkc/mkc.ps1" \
      --mock $env(MKC_TEST_DEVICE) --local $env(MKC_TEST_LOCAL)
    after 500

    send "\033OP"
    must_see "MKC — файловый менеджер MK61s"
    send "\033"
    must_see "Good> "

    send "\033\[B"
    send "\033OR"
    must_see "001"
    must_see "Esc/F3 — close"
    send "\033"
    must_see "Good> "

    send "\033\[15~"
    must_see "Copy 1 item(s) to MK61s:"
    send "\033"
    must_see "Good> "

    send "\033\[21~"
    expect { eof {} timeout { puts stderr "mkc PowerShell F10 timeout"; exit 1 } }
    catch wait result
    exit [lindex $result 3]
  '
fi

echo 'mkc_tests: ok'

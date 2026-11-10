#!/usr/bin/env bash

# Interactive game-library selector. Bash 3.2 compatible for older macOS.

set -u

SCRIPT_DIR=$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)
MANAGER="$SCRIPT_DIR/manager.py"

find_python() {
  if command -v python3 >/dev/null 2>&1 && python3 -c 'import sys; raise SystemExit(sys.version_info < (3, 10))' 2>/dev/null; then
    printf '%s\n' python3
  elif command -v python >/dev/null 2>&1 && python -c 'import sys; raise SystemExit(sys.version_info < (3, 10))' 2>/dev/null; then
    printf '%s\n' python
  else
    return 1
  fi
}

PYTHON=$(find_python) || {
  printf '%s\n' 'games: Python 3.10 or newer was not found.' >&2
  exit 127
}

if [ "$#" -gt 0 ]; then
  exec "$PYTHON" "$MANAGER" "$@"
fi

if [ ! -t 0 ] || [ ! -t 1 ]; then
  printf '%s\n' 'games: interactive mode needs a terminal; use `games.cmd run --select ID`.' >&2
  "$PYTHON" "$MANAGER" list
  exit 2
fi

IDS=()
CHECKED=()
TITLES=()
DESCRIPTIONS=()
while IFS=$'\t' read -r id checked title description; do
  IDS+=("$id")
  CHECKED+=("$checked")
  TITLES+=("$title")
  DESCRIPTIONS+=("$description")
done < <("$PYTHON" "$MANAGER" list --tsv)

selected=0

draw() {
  local i marker cursor
  printf '\033[2J\033[H'
  printf '\033[1;36m MK61S GAME LIBRARY \033[0m\n'
  printf ' Choose downloads and APP builds\n\n'
  for ((i = 0; i < ${#IDS[@]}; i++)); do
    marker='[ ]'
    [ "${CHECKED[$i]}" = 1 ] && marker='[x]'
    cursor='  '
    [ "$i" -eq "$selected" ] && cursor='> '
    if [ "$i" -eq "$selected" ]; then
      printf '\033[30;47m%s%s  %s\033[0m\n' "$cursor" "$marker" "${TITLES[$i]}"
    else
      printf '%s%s  %s\n' "$cursor" "$marker" "${TITLES[$i]}"
    fi
  done
  printf '\n %s\n' "${DESCRIPTIONS[$selected]}"
  printf '\n \033[36mUp/Down\033[0m choose  \033[36mSpace\033[0m toggle  \033[36mEnter\033[0m run  \033[36mEsc/Q\033[0m quit\n'
}

while :; do
  draw
  IFS= read -rsn1 key || key=
  if [ "$key" = $'\033' ]; then
    IFS= read -rsn1 -t 0.05 rest || rest=
    if [ "$rest" = '[' ]; then
      IFS= read -rsn1 -t 0.05 arrow || arrow=
      case "$arrow" in
        A) selected=$((selected - 1)); [ "$selected" -lt 0 ] && selected=$((${#IDS[@]} - 1)) ;;
        B) selected=$((selected + 1)); [ "$selected" -ge "${#IDS[@]}" ] && selected=0 ;;
      esac
    else
      printf '\033[2J\033[H'
      exit 0
    fi
  elif [ -z "$key" ]; then
    break
  elif [ "$key" = ' ' ] || [ "$key" = x ] || [ "$key" = X ]; then
    if [ "${CHECKED[$selected]}" = 1 ]; then CHECKED[$selected]=0; else CHECKED[$selected]=1; fi
  elif [ "$key" = q ] || [ "$key" = Q ]; then
    printf '\033[2J\033[H'
    exit 0
  elif [ "$key" = k ]; then
    selected=$((selected - 1)); [ "$selected" -lt 0 ] && selected=$((${#IDS[@]} - 1))
  elif [ "$key" = j ]; then
    selected=$((selected + 1)); [ "$selected" -ge "${#IDS[@]}" ] && selected=0
  fi
done

command=("$PYTHON" "$MANAGER" run)
for ((i = 0; i < ${#IDS[@]}; i++)); do
  [ "${CHECKED[$i]}" = 1 ] && command+=(--select "${IDS[$i]}")
done
printf '\033[2J\033[H'
"${command[@]}"

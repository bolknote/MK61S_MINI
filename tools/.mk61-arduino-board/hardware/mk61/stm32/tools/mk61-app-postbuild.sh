#!/usr/bin/env bash
set -euo pipefail

die() {
  printf 'MK61s F401 + APP: %s\n' "$*" >&2
  exit 1
}

require_value() {
  [ "$#" -ge 2 ] && [ -n "$2" ] || die "$1 requires a value"
}

profile_valid() {
  case "$1:$2" in
    mini-v2:lcd1602-a00|mini-v2:lcd1602-a02|\
    mini-v3:lcd1602-a00|mini-v3:lcd1602-a02|mini-v3:oled1602-ws0010|\
    classic-v2:uc1609|classic-v3:uc1609|40th:uc1609) return 0 ;;
  esac
  return 1
}

check_profile() {
  local platform= display= sketch= build_path= variant_ld=
  while [ "$#" -gt 0 ]; do
    case "$1" in
      --platform) require_value "$@"; platform=$2; shift 2 ;;
      --display) require_value "$@"; display=$2; shift 2 ;;
      --sketch) require_value "$@"; sketch=$2; shift 2 ;;
      --build-path) require_value "$@"; build_path=$2; shift 2 ;;
      --variant-ld) require_value "$@"; variant_ld=$2; shift 2 ;;
      *) die "unknown check-profile option: $1" ;;
    esac
  done
  profile_valid "$platform" "$display" ||
    die "incompatible platform/display pair: $platform + $display"
  [ -f "$sketch/mk61s-M.ino" ] && [ -f "$sketch/config.h" ] ||
    die 'open code/mk61s-M.ino before selecting this board'
  [ -n "$variant_ld" ] || return 0
  mkdir -p "$build_path"
  python3 "$sketch/../tools/.mk61-gcc/portable-layout.py" \
    "$variant_ld" "$build_path/mk61-portable.ld"
}

seal_resident() {
  local resident=$1 tool_dir host_cxx sealer_root sealer temporary
  tool_dir="$(cd "$(dirname "$0")" && pwd)"
  host_cxx=${MK61_HOST_CXX:-${CXX:-c++}}
  command -v "$host_cxx" >/dev/null 2>&1 ||
    die "host C++17 compiler not found: $host_cxx"
  [ -f "$tool_dir/mk61_firmware_seal.cpp" ] &&
    [ -f "$tool_dir/resident_firmware_format.hpp" ] &&
    [ -f "$tool_dir/rust_types.h" ] ||
    die 'resident firmware sealer payload is missing; reinstall the MK61s board'
  sealer_root="$build_path/.mk61-host-tools"
  sealer="$sealer_root/mk61_firmware_seal"
  mkdir -p "$sealer_root"
  if [ ! -x "$sealer" ] ||
     [ "$tool_dir/mk61_firmware_seal.cpp" -nt "$sealer" ] ||
     [ "$tool_dir/resident_firmware_format.hpp" -nt "$sealer" ] ||
     [ "$tool_dir/rust_types.h" -nt "$sealer" ]; then
    temporary="$sealer.tmp"
    "$host_cxx" -std=c++17 -O2 -Wall -Wextra -Werror -pedantic \
      -I"$tool_dir" "$tool_dir/mk61_firmware_seal.cpp" -o "$temporary" ||
      die 'could not build the resident firmware sealer'
    mv "$temporary" "$sealer"
  fi
  "$sealer" seal --max-size 262144 "$resident"
  "$sealer" check --max-size 262144 "$resident"
}

build_bundle() {
  local compiler= build_path_arg= sketch= project= bundle=
  local focal= basic= wbmp= markdown= chip8= local_float_math= compile_flags=
  while [ "$#" -gt 0 ]; do
    case "$1" in
      --compiler) require_value "$@"; compiler=$2; shift 2 ;;
      --build-path) require_value "$@"; build_path_arg=$2; shift 2 ;;
      --sketch) require_value "$@"; sketch=$2; shift 2 ;;
      --project) require_value "$@"; project=$2; shift 2 ;;
      --bundle) require_value "$@"; bundle=$2; shift 2 ;;
      --focal) require_value "$@"; focal=$2; shift 2 ;;
      --basic) require_value "$@"; basic=$2; shift 2 ;;
      --wbmp) require_value "$@"; wbmp=$2; shift 2 ;;
      --markdown) require_value "$@"; markdown=$2; shift 2 ;;
      --chip8) require_value "$@"; chip8=$2; shift 2 ;;
      --local-float-math) require_value "$@"; local_float_math=$2; shift 2 ;;
      --compile-flags) require_value "$@"; compile_flags=$2; shift 2 ;;
      *) die "unknown build option: $1" ;;
    esac
  done

  [ -x "$compiler" ] || die "ARM compiler not found: $compiler"
  [ -d "$build_path_arg" ] || die 'Arduino build path was not found'
  [ -n "$project" ] && [ -n "$bundle" ] ||
    die 'Arduino project or bundle name is missing'
  case "$focal:$basic:$wbmp:$markdown:$chip8:$local_float_math" in
    [01]:[01]:[01]:[01]:[01]:[01]) ;;
    *) die 'System APP selections must be 0 or 1' ;;
  esac
  if [ "$markdown" -eq 1 ]; then wbmp=0; fi
  if [ "$local_float_math" -eq 1 ] &&
     [[ "$compile_flags" != *MK61_MATH_BACKEND=1* ]]; then
    die 'local APP float math requires resident CORE math'
  fi

  build_path=$build_path_arg
  local resident_elf="$build_path/$project.elf"
  local resident_bin="$build_path/$project.bin"
  [ -s "$resident_elf" ] && [ -s "$resident_bin" ] ||
    die 'Arduino did not produce resident ELF and BIN files'
  seal_resident "$resident_bin"

  stage="$build_path/mk61-system-apps/$bundle"
  case "$stage" in "$build_path"/*) ;; *) die 'unsafe staging path' ;; esac
  rm -rf "$stage"
  mkdir -p "$stage/System"
  cp "$resident_bin" "$stage/$bundle.bin"

  local graphics=0 ui_fonts=0
  if [[ "$compile_flags" == *MK61_BOARD_CLASSIC* ]] ||
     [[ "$compile_flags" == *MK61_BOARD_40TH* ]] ||
     [[ "$compile_flags" == *DISPLAY_UC1609* ]] ||
     [[ "$compile_flags" == *MK61_ENABLE_USB_SCREEN=1* ]] ||
     [[ "$compile_flags" == *MK61_WS0010_GRAPHICS_100X16=1* ]]; then
    graphics=1
  fi
  if [[ "$compile_flags" == *MK61_BOARD_CLASSIC* ]] ||
     [[ "$compile_flags" == *MK61_BOARD_40TH* ]] ||
     [[ "$compile_flags" == *DISPLAY_UC1609* ]]; then
    ui_fonts=1
  fi
  python3 "$sketch/../tools/build_system_app_bundle.py" \
    --resident-elf "$resident_elf" \
    --arm-toolchain-bin "$(dirname "$compiler")" \
    --output-dir "$stage/System" --graphics "$graphics" \
    --ui-fonts "$ui_fonts" \
    --focal "$focal" --basic "$basic" --wbmp "$wbmp" \
    --markdown "$markdown" --chip8 "$chip8" \
    --local-float-math "$local_float_math"

  local output_root output canonical
  output_root="$(cd "$sketch/.." && pwd)/binary"
  output="$output_root/$bundle"
  mkdir -p "$output/System"
  cp "$stage/$bundle.bin" "$output/$bundle.bin"
  for canonical in FOCAL.APP BASIC.APP WBMP.APP MARKDOWN.APP CHIP8.APP \
                   SETUP.APP USBDISK.APP HELP0.TXT HELP1.TXT; do
    if [ -f "$stage/System/$canonical" ]; then
      cp "$stage/System/$canonical" "$output/System/$canonical"
    else
      rm -f "$output/System/$canonical"
    fi
  done
  rm -rf "$output/licenses/ui-fonts"
  if [ "$ui_fonts" -eq 1 ]; then
    python3 "$sketch/../tools/.fmk-font/package_ui_font_licenses.py" \
      --bundle "$output"
  fi
  printf '%s -DMK61_PORTABLE_UI_FONTS=%s -DMK61_APP_LOCAL_FLOAT_MATH=%s\n' \
    "$compile_flags" "$ui_fonts" "$local_float_math" > "$output/build.flags"
  printf 'format 1\nabi 6\n' > "$output/build.apps"
  printf '\nMK61s F401 unified ABI 6 bundle built by Arduino IDE:\n  %s\n' "$output"
  printf 'After Upload, copy the generated System directory to /System on MK61S C6.\n\n'
}

[ "$#" -gt 0 ] || die 'missing command'
command=$1
shift
case "$command" in
  check-profile) check_profile "$@" ;;
  build) build_bundle "$@" ;;
  *) die "unknown command: $command" ;;
esac

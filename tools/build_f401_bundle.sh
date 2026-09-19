#!/usr/bin/env bash

# Собирает комплект для STM32F401CC: resident и независимые APP текущего ABI.
# System — только набор канонических ролей того же общего загрузчика.

set -euo pipefail

root="$(cd "$(dirname "$0")/.." && pwd)"
arduino_cli=${MK61_ARDUINO_CLI:-arduino-cli}
build_root=${MK61_F401_BUILD_ROOT:-"$root/.build/mk61-f401"}
output_root=${MK61_OUTPUT_DIR:-"$root/binary"}
profile=mini-v3-a00

enable_focal=${MK61_ENABLE_FOCAL:-1}
enable_tinybasic=${MK61_ENABLE_TINYBASIC:-1}
enable_wbmp=${MK61_ENABLE_WBMP_VIEWER:-}
enable_markdown=${MK61_ENABLE_MARKDOWN_VIEWER:-1}
enable_chip8=${MK61_ENABLE_CHIP8:-0}
enable_usb_screen=${MK61_ENABLE_USB_SCREEN:-0}
enable_extended_font=${MK61_ENABLE_EXTENDED_FONT_SETTINGS:-0}
enable_user_explorer=${MK61_USER_EXPLORER_SHORTCUT:-1}
math_backend=${MK61_MATH_BACKEND:-0}
app_local_float=${MK61_APP_LOCAL_FLOAT_MATH:-0}
check_app_manifests=0
app_manifests=()
custom_app_names=()
custom_app_ids=()
custom_app_dirs=()
custom_app_sources=()
custom_app_files=()
custom_app_magics=()
custom_app_manifest_paths=()

fqbn_resident='STMicroelectronics:stm32:GenF4:pnum=BLACKPILL_F401CC,upload_method=dfuMethod,xserial=none,usb=CDCgen,opt=oslto'
platform_ram_flags='-DHAL_UART_MODULE_ONLY -DUSBD_CLASS_USER_STRING_DESC=0'

usage() {
  cat <<'EOF'
Build a matched STM32F401CC firmware/APP bundle.

Usage:
  tools/build_f401_bundle.sh [--profile ID] [--output-dir DIR]
                              [--build-root DIR]
                              [--app-manifest FILE]...
  tools/build_f401_bundle.sh --check-app-manifests
                              [--app-manifest FILE]...

Profiles:
  mini-v3-a00, mini-v3-a02, mini-v3-ws0010,
  mini-v2-a00, mini-v2-a02,
  classic-v2, classic-v3, 40th

Feature environment variables (0 or 1):
  MK61_ENABLE_FOCAL, MK61_ENABLE_TINYBASIC, MK61_ENABLE_WBMP_VIEWER,
  MK61_ENABLE_MARKDOWN_VIEWER, MK61_ENABLE_CHIP8,
  MK61_ENABLE_USB_SCREEN, MK61_ENABLE_EXTENDED_FONT_SETTINGS,
  MK61_USER_EXPLORER_SHORTCUT
Math backend: MK61_MATH_BACKEND=0 (LIBM), 1 (CORE), or 2 (FLOAT).
APP math: MK61_APP_LOCAL_FLOAT_MATH=1 links local float ln/lg/exp/sqrt into FOCAL/BASIC.
  Markdown handles T2 and graphical I1; WBMP.APP is built only with
  MK61_ENABLE_MARKDOWN_VIEWER=0.

Other overrides:
  MK61_ARDUINO_CLI, MK61_F401_BUILD_ROOT, MK61_OUTPUT_DIR,
  MK61_APP_MANIFESTS (colon-separated manifest paths)

Every generated APP uses the current relocatable ABI and the same public API.
EOF
}

profile_flags() {
  case "$1" in
    mini-v3-a00) printf '%s' '-DMK61_LCD1602_A00' ;;
    mini-v3-a02) printf '%s' '-DMK61_LCD1602_A02' ;;
    mini-v3-ws0010) printf '%s' '-DMK61_OLED1602_WS0010' ;;
    mini-v2-a00) printf '%s' '-DREVISION_V2 -DMK61_LCD1602_A00' ;;
    mini-v2-a02) printf '%s' '-DREVISION_V2 -DMK61_LCD1602_A02' ;;
    classic-v2)  printf '%s' '-DMK61_BOARD_CLASSIC_V2' ;;
    classic-v3)  printf '%s' '-DMK61_BOARD_CLASSIC_V3' ;;
    40th)        printf '%s' '-DMK61_BOARD_40TH' ;;
    *) return 1 ;;
  esac
}

artifact_name() {
  case "$1" in
    mini-v3-a00) printf '%s' 'mk61s-M-mini-v3-lcd1602-a00-f401.bin' ;;
    mini-v3-a02) printf '%s' 'mk61s-M-mini-v3-lcd1602-a02-f401.bin' ;;
    mini-v3-ws0010) printf '%s' 'mk61s-M-mini-v3-oled1602-ws0010-f401.bin' ;;
    mini-v2-a00) printf '%s' 'mk61s-M-mini-v2-lcd1602-a00-f401.bin' ;;
    mini-v2-a02) printf '%s' 'mk61s-M-mini-v2-lcd1602-a02-f401.bin' ;;
    classic-v2)  printf '%s' 'mk61s-M-classic-v2-uc1609-f401.bin' ;;
    classic-v3)  printf '%s' 'mk61s-M-classic-v3-uc1609-f401.bin' ;;
    40th)        printf '%s' 'mk61s-M-40th-f401.bin' ;;
    *) return 1 ;;
  esac
}

boolean_valid() {
  case "$1" in 0|1) return 0 ;; esac
  return 1
}

normalize_host_path() {
  local value=${1%$'\r'}
  case "$value" in
    [A-Za-z]:[\\/]*)
      if command -v cygpath >/dev/null 2>&1; then
        cygpath -u "$value"
      else
        printf '%s' "$value"
      fi
      ;;
    *) printf '%s' "$value" ;;
  esac
}

manifest_error() {
  printf 'Error: APP manifest %s: %s\n' "$1" "$2" >&2
  return 1
}

safe_app_relative_path() {
  case "$1" in
    ''|/*|*\\*|../*|*/../*|*/..|./*|*/./*|*/.|*[!A-Za-z0-9_./-]*)
      return 1
      ;;
  esac
  return 0
}

list_contains_word() {
  local wanted=$1
  shift
  local wanted_folded
  wanted_folded=$(printf '%s' "$wanted" | tr '[:lower:]' '[:upper:]')
  local candidate
  for candidate in "$@"; do
    [ "$(printf '%s' "$candidate" | tr '[:lower:]' '[:upper:]')" != \
      "$wanted_folded" ] || return 0
  done
  return 1
}

parse_app_manifest() {
  local requested_display=$1
  local requested
  requested=$(normalize_host_path "$requested_display")
  local manifest
  case "$requested" in
    /*) manifest=$requested ;;
    *) manifest="$root/$requested" ;;
  esac
  [ -f "$manifest" ] || {
    manifest_error "$requested_display" "file does not exist"
    return 1
  }
  local manifest_dir
  manifest_dir=$(cd "$(dirname "$manifest")" && pwd -P)
  manifest="$manifest_dir/$(basename "$manifest")"

  local format=
  local name=
  local magic=-
  local sources=()
  local files=()
  local line directive value extra path_lower folded
  local line_number=0
  while IFS= read -r line || [ -n "$line" ]; do
    line_number=$((line_number + 1))
    line=${line%$'\r'}
    directive=
    value=
    extra=
    IFS=$' \t' read -r directive value extra <<< "$line"
    [ -n "$directive" ] || continue
    case "$directive" in \#*) continue ;; esac
    if [ -z "$value" ] || [ -n "$extra" ]; then
      manifest_error "$requested:$line_number" \
        "expected exactly one directive and one value"
      return 1
    fi
    case "$directive" in
      format)
        if [ -n "$format" ] || [ "$value" != 1 ]; then
          manifest_error "$requested:$line_number" \
            "format must occur once and equal 1"
          return 1
        fi
        format=$value
        ;;
      name)
        if [ -n "$name" ]; then
          manifest_error "$requested:$line_number" "duplicate name"
          return 1
        fi
        case "$value" in
          ''|[-_]*|*[!A-Za-z0-9_-]*)
            manifest_error "$requested:$line_number" \
              "name must use ASCII letters, digits, '_' or '-'"
            return 1
            ;;
        esac
        if [ "${#value}" -gt 31 ]; then
          manifest_error "$requested:$line_number" \
            "name exceeds the 31-byte C5 basename limit"
          return 1
        fi
        folded=$(printf '%s' "$value" | tr '[:lower:]' '[:upper:]')
        case "$folded" in
          CON|PRN|AUX|NUL|COM[1-9]|LPT[1-9])
            manifest_error "$requested:$line_number" \
              "name is reserved by FAT/DOS"
            return 1
            ;;
        esac
        name=$value
        ;;
      magic)
        if [ "$magic" != - ]; then
          manifest_error "$requested:$line_number" "duplicate magic"
          return 1
        fi
        if [ "${#value}" -ne 2 ]; then
          manifest_error "$requested:$line_number" \
            "magic must contain exactly two ASCII bytes"
          return 1
        fi
        case "$value" in
          *[!A-Za-z0-9]*)
            manifest_error "$requested:$line_number" \
              "magic must use ASCII letters or digits"
            return 1
            ;;
        esac
        magic=$value
        ;;
      source|file)
        if ! safe_app_relative_path "$value"; then
          manifest_error "$requested:$line_number" \
            "path must be a safe relative ASCII path"
          return 1
        fi
        if [ "$directive" = source ]; then
          case "$value" in
            *.c|*.cc|*.cpp|*.cxx|*.rs|*.S|*.s) ;;
            *)
              manifest_error "$requested:$line_number" \
                "source must be C, C++, Rust or assembler"
              return 1
              ;;
          esac
        else
          path_lower=$(printf '%s' "$value" | tr '[:upper:]' '[:lower:]')
          case "$path_lower" in
            *.c|*.cc|*.cpp|*.cxx|*.s|*.ino)
              manifest_error "$requested:$line_number" \
                "compiled source must use the source directive"
              return 1
              ;;
          esac
        fi
        if [ ! -f "$manifest_dir/$value" ]; then
          manifest_error "$requested:$line_number" \
            "referenced file does not exist: $value"
          return 1
        fi
        if list_contains_word "$value" "${sources[@]}" "${files[@]}"; then
          manifest_error "$requested:$line_number" \
            "duplicate source/file path: $value"
          return 1
        fi
        if [ "$directive" = source ]; then
          sources+=("$value")
        else
          files+=("$value")
        fi
        ;;
      *)
        manifest_error "$requested:$line_number" \
          "unknown directive: $directive"
        return 1
        ;;
    esac
  done < "$manifest"

  [ "$format" = 1 ] || {
    manifest_error "$requested" "missing 'format 1'"
    return 1
  }
  [ -n "$name" ] || {
    manifest_error "$requested" "missing name"
    return 1
  }
  [ "${#sources[@]}" -ne 0 ] || {
    manifest_error "$requested" "at least one source is required"
    return 1
  }

  folded=$(printf '%s' "$name" | tr '[:lower:]' '[:upper:]')
  local existing
  for existing in "${custom_app_names[@]}"; do
    if [ "$(printf '%s' "$existing" | tr '[:lower:]' '[:upper:]')" = \
         "$folded" ]; then
      manifest_error "$requested" "duplicate APP name: $name"
      return 1
    fi
  done

  local id
  id=$(printf '%s' "$name" | tr '[:upper:]-' '[:lower:]_')
  custom_app_names+=("$name")
  custom_app_ids+=("$id")
  custom_app_dirs+=("$manifest_dir")
  custom_app_sources+=("${sources[*]}")
  custom_app_files+=("${files[*]}")
  custom_app_magics+=("$magic")
  custom_app_manifest_paths+=("$manifest")
}

while [ "$#" -gt 0 ]; do
  case "$1" in
    --profile)
      [ "$#" -ge 2 ] || { printf 'Error: --profile needs an ID.\n' >&2; exit 2; }
      profile=$2
      shift 2
      ;;
    --output-dir)
      [ "$#" -ge 2 ] || { printf 'Error: --output-dir needs a path.\n' >&2; exit 2; }
      output_root=$2
      shift 2
      ;;
    --build-root)
      [ "$#" -ge 2 ] || { printf 'Error: --build-root needs a path.\n' >&2; exit 2; }
      build_root=$2
      shift 2
      ;;
    --app-manifest)
      [ "$#" -ge 2 ] || {
        printf 'Error: --app-manifest needs a path.\n' >&2
        exit 2
      }
      app_manifests+=("$2")
      shift 2
      ;;
    --check-app-manifests)
      check_app_manifests=1
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

if [ -n "${MK61_APP_MANIFESTS:-}" ]; then
  previous_ifs=$IFS
  case "$MK61_APP_MANIFESTS" in
    *';'*) IFS=';' ;;
    [A-Za-z]:[\\/]*) IFS=$'\n' ;;
    *) IFS=: ;;
  esac
  for manifest in $MK61_APP_MANIFESTS; do
    [ -n "$manifest" ] && app_manifests+=("$manifest")
  done
  IFS=$previous_ifs
fi
for manifest in "${app_manifests[@]}"; do
  parse_app_manifest "$manifest"
done
if [ "$check_app_manifests" -eq 1 ]; then
  printf 'Validated APP manifests: %u\n' "${#custom_app_names[@]}"
  for index in "${!custom_app_names[@]}"; do
    printf 'Apps/%s.APP <- %s\n' \
      "${custom_app_names[$index]}" "${custom_app_manifest_paths[$index]}"
  done
  exit 0
fi

board_flags=$(profile_flags "$profile") || {
  printf 'Error: unsupported profile: %s\n' "$profile" >&2
  exit 2
}
firmware_name=$(artifact_name "$profile")

if [ -z "$enable_wbmp" ]; then
  if [ "$enable_markdown" -eq 1 ]; then
    enable_wbmp=0
  else
    case "$profile" in
      classic-v2|classic-v3|40th) enable_wbmp=1 ;;
      *) enable_wbmp=$enable_usb_screen ;;
    esac
  fi
fi

for value in "$enable_focal" "$enable_tinybasic" "$enable_wbmp" \
             "$enable_markdown" "$enable_chip8" \
             "$enable_usb_screen" "$enable_extended_font" \
             "$enable_user_explorer" "$app_local_float"; do
  boolean_valid "$value" || {
    printf 'Error: all MK61 feature values must be 0 or 1.\n' >&2
    exit 2
  }
done
case "$math_backend" in
  0|1|2) ;;
  *)
    printf 'Error: MK61_MATH_BACKEND must be 0, 1, or 2.\n' >&2
    exit 2
    ;;
esac
if [ "$app_local_float" -eq 1 ] && [ "$math_backend" -ne 1 ]; then
  printf 'Error: MK61_APP_LOCAL_FLOAT_MATH=1 requires MK61_MATH_BACKEND=1 (CORE).\n' >&2
  exit 2
fi
if [ "$enable_markdown" -eq 1 ]; then
  enable_wbmp=0
fi
case "$profile" in
  classic-v2|classic-v3|40th)
    compiled_graphics=1
    ui_fonts=1
    ;;
  *)
    compiled_graphics=$enable_usb_screen
    ui_fonts=0
    ;;
esac
if [ "$compiled_graphics" -eq 0 ] &&
   { [ "$enable_wbmp" -eq 1 ] || [ "$enable_chip8" -eq 1 ]; }; then
  printf 'Error: WBMP/CHIP-8 requires UC1609 or MK61_ENABLE_USB_SCREEN=1.\n' >&2
  exit 2
fi
resident_link_flags='-Wl,--wrap=USBD_CDC_ClearBuffer,--wrap=USBD_LL_SetupStage,--wrap=USBD_LL_Reset,--wrap=USBD_LL_Suspend,--wrap=USBD_LL_Resume,--wrap=USBD_LL_DevConnected,--wrap=USBD_LL_DevDisconnected'

command -v "$arduino_cli" >/dev/null 2>&1 || {
  printf 'Error: arduino-cli is not installed.\n' >&2
  exit 1
}
command -v python3 >/dev/null 2>&1 || {
  printf 'Error: python3 is required for the stack-usage release gate.\n' >&2
  exit 1
}
if ! command -v "${MK61_HOST_CXX:-${CXX:-c++}}" >/dev/null 2>&1; then
  printf 'Error: a host C++17 compiler is required for firmware sealing.\n' >&2
  exit 1
fi

compile_flags="$board_flags"
compile_flags="$compile_flags -DMK61_ENABLE_FOCAL=$enable_focal"
compile_flags="$compile_flags -DMK61_ENABLE_TINYBASIC=$enable_tinybasic"
compile_flags="$compile_flags -DMK61_ENABLE_WBMP_VIEWER=$enable_wbmp"
compile_flags="$compile_flags -DMK61_ENABLE_MARKDOWN_VIEWER=$enable_markdown"
compile_flags="$compile_flags -DMK61_ENABLE_CHIP8=$enable_chip8"
compile_flags="$compile_flags -DMK61_ENABLE_USB_SCREEN=$enable_usb_screen"
compile_flags="$compile_flags -DMK61_ENABLE_EXTENDED_FONT_SETTINGS=$enable_extended_font"
compile_flags="$compile_flags -DMK61_USER_EXPLORER_SHORTCUT=$enable_user_explorer"
compile_flags="$compile_flags -DMK61_MATH_BACKEND=$math_backend"
compile_flags="$compile_flags -DMK61_APP_LOCAL_FLOAT_MATH=$app_local_float"
compile_flags="$compile_flags -DMK61_ENABLE_LOADABLE_MODULES=1"
compile_flags="$compile_flags -DMK61_F401_PRODUCT_BUILD=1"
compile_flags="$compile_flags -DMK61_REQUIRE_RESIDENT_CRC=1"
compile_flags="$compile_flags -DMK61_REQUIRE_F401_SELECTIVE_O3=1"
compile_flags="$compile_flags $platform_ram_flags"

mkdir -p "$build_root" "$output_root"
work=$(mktemp -d "$build_root/work.XXXXXX")
cleanup() {
  rm -rf "$work"
}
trap cleanup EXIT INT TERM

sketch_dir="$work/sketch/mk61s-M"
resident_build="$work/resident"
bundle_stage="$work/bundle"
mkdir -p "$sketch_dir" "$resident_build" "$bundle_stage"
cp -R "$root/code/." "$sketch_dir/"

"$arduino_cli" compile --fqbn "$fqbn_resident" \
  --build-path "$work/properties-layout" --show-properties=expanded \
  "$sketch_dir" > "$work/layout.properties"
variant_path=$(sed -n 's/^build\.variant\.path=//p' "$work/layout.properties" | tr -d '\r')
ld_name=$(sed -n 's/^build\.ldscript=//p' "$work/layout.properties" | tr -d '\r')
python3 "$root/tools/.mk61-gcc/portable-layout.py" \
  "$variant_path/$ld_name" "$resident_build/mk61-portable.ld"
resident_link_flags="$resident_link_flags -Wl,--default-script=$resident_build/mk61-portable.ld"

printf 'Building F401 resident firmware (%s)…\n' "$profile"
"$arduino_cli" compile \
  --fqbn "$fqbn_resident" \
  --build-path "$resident_build" \
  --build-property "compiler.cpp.extra_flags=$compile_flags" \
  --build-property "compiler.c.extra_flags=$platform_ram_flags" \
  --build-property "compiler.c.elf.extra_flags=$resident_link_flags" \
  "$sketch_dir"

python3 "$root/tests/analyze_stack_usage.py" \
  --compile-commands "$resident_build/compile_commands.json" \
  --source-root "$resident_build/sketch" --top 3

resident_elf="$resident_build/mk61s-M.ino.elf"
resident_bin="$resident_build/mk61s-M.ino.bin"
if [ ! -s "$resident_elf" ] || [ ! -s "$resident_bin" ]; then
  printf 'Error: Arduino build did not create resident ELF and BIN files.\n' >&2
  exit 1
fi
"$root/tools/seal-firmware.sh" seal --max-size 262144 "$resident_bin"
"$root/tools/seal-firmware.sh" check --max-size 262144 "$resident_bin"

compiler=
compiler_path=$(sed -n 's/^compiler\.path=//p' "$work/layout.properties" | head -n 1)
compiler_cpp=$(sed -n 's/^compiler\.cpp\.cmd=//p' "$work/layout.properties" | head -n 1)
compiler_path=${compiler_path%$'\r'}
compiler_cpp=${compiler_cpp%$'\r'}
if [ -z "$compiler_path" ] || [ -z "$compiler_cpp" ]; then
  printf 'Error: cannot resolve the STM32 ARM compiler from Arduino properties.\n' >&2
  exit 1
fi
compiler=$(normalize_host_path "$compiler_path$compiler_cpp")
[ -x "$compiler" ] || {
  printf 'Error: required STM32 compiler is missing: %s\n' "$compiler" >&2
  exit 1
}

build_custom_app() {
  custom_index=$1
  custom_name=${custom_app_names[$custom_index]}
  custom_id="${custom_app_ids[$custom_index]}-$custom_index"
  custom_dir=${custom_app_dirs[$custom_index]}
  custom_out="$work/module-app-$custom_id"
  custom_args=(--name "$custom_name" --arm-toolchain-bin "$(dirname "$compiler")"
               --output-dir "$custom_out" --include "$custom_dir")
  for relative in ${custom_app_sources[$custom_index]}; do
    custom_args+=(--source "$custom_dir/$relative")
  done
  if [ "${custom_app_magics[$custom_index]}" != - ]; then
    custom_args+=(--handled-magic "${custom_app_magics[$custom_index]}")
  fi
  python3 "$root/tools/build_portable_app.py" "${custom_args[@]}"
  mkdir -p "$bundle_stage/Apps"
  cp "$custom_out/$custom_name.APP" "$bundle_stage/Apps/$custom_name.APP"
}

cp "$resident_bin" "$bundle_stage/$firmware_name"
python3 "$root/tools/build_system_app_bundle.py" \
  --resident-elf "$resident_elf" \
  --arm-toolchain-bin "$(dirname "$compiler")" \
  --output-dir "$bundle_stage/System" \
  --graphics "$compiled_graphics" --ui-fonts "$ui_fonts" \
  --focal "$enable_focal" --basic "$enable_tinybasic" \
  --wbmp "$enable_wbmp" --markdown "$enable_markdown" \
  --chip8 "$enable_chip8" --local-float-math "$app_local_float"
for index in "${!custom_app_names[@]}"; do
  build_custom_app "$index"
done

bundle_name=${firmware_name%.bin}
bundle_dir="$output_root/$bundle_name"
mkdir -p "$bundle_dir"
# Выключенный ключ не должен оставлять в новом комплекте APP от предыдущей
# сборки этого же профиля.
rm -f "$bundle_dir/System/FOCAL.APP" \
      "$bundle_dir/System/BASIC.APP" "$bundle_dir/System/WBMP.APP" \
      "$bundle_dir/System/MARKDOWN.APP" \
      "$bundle_dir/System/CHIP8.APP" "$bundle_dir/System/SETUP.APP" \
      "$bundle_dir/System/HELP0.TXT" "$bundle_dir/System/HELP1.TXT" \
      "$bundle_dir/$firmware_name" "$bundle_dir/build.apps"
if [ -d "$bundle_dir/System" ]; then
  rmdir "$bundle_dir/System" 2>/dev/null || true
fi
# Apps — полностью генерируемая часть комплекта. Чистая замена не позволяет
# удалённому из manifest приложению незаметно остаться от предыдущей сборки.
if [ -d "$bundle_dir/Apps" ]; then
  rm -rf "$bundle_dir/Apps"
fi
if [ -d "$bundle_dir/licenses/ui-fonts" ]; then
  rm -rf "$bundle_dir/licenses/ui-fonts"
fi
if [ -d "$bundle_dir/licenses" ]; then
  rmdir "$bundle_dir/licenses" 2>/dev/null || true
fi
cp -R "$bundle_stage/." "$bundle_dir/"
if [ "$ui_fonts" -eq 1 ]; then
  python3 "$root/tools/.fmk-font/package_ui_font_licenses.py" \
    --bundle "$bundle_dir"
fi
printf '%s -DMK61_PORTABLE_UI_FONTS=%s -DMK61_APP_LOCAL_FLOAT_MATH=%s\n' \
  "$compile_flags" "$ui_fonts" "$app_local_float" > "$bundle_dir/build.flags"
{
  printf 'format 1\n'
  printf 'abi 5\n'
  for index in "${!custom_app_names[@]}"; do
    printf 'app Apps/%s.APP\n' "${custom_app_names[$index]}"
  done
} > "$bundle_dir/build.apps"

printf 'Built F401 bundle: %s\n' "$bundle_dir"
find "$bundle_dir" -maxdepth 2 -type f -print | sort

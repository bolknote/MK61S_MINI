#!/usr/bin/env bash

# Собирает согласованный комплект для STM32F401CC: resident-прошивку и
# включённые системные APP, привязанные к её точному ELF/.bin. Resident остаётся
# на штатном -Os, чтобы экспортируемые символы не локализовал LTO; каждый APP
# отдельно собирается с -Os -flto и оптимально упаковывается ZX0.

set -euo pipefail

root="$(cd "$(dirname "$0")/.." && pwd)"
arduino_cli=${MK61_ARDUINO_CLI:-arduino-cli}
build_root=${MK61_F401_BUILD_ROOT:-"$root/.build/mk61-f401"}
output_root=${MK61_OUTPUT_DIR:-"$root/binary"}
profile=mini-v3-a00

enable_focal=${MK61_ENABLE_FOCAL:-1}
enable_tinybasic=${MK61_ENABLE_TINYBASIC:-1}
enable_wbmp=${MK61_ENABLE_WBMP_VIEWER:-1}
enable_usb_screen=${MK61_ENABLE_USB_SCREEN:-0}
enable_extended_font=${MK61_ENABLE_EXTENDED_FONT_SETTINGS:-0}
enable_user_explorer=${MK61_USER_EXPLORER_SHORTCUT:-1}
math_backend=${MK61_MATH_BACKEND:-0}
check_app_manifests=0
app_manifests=()
custom_app_names=()
custom_app_ids=()
custom_app_dirs=()
custom_app_sources=()
custom_app_files=()
custom_app_manifest_paths=()

fqbn_resident='STMicroelectronics:stm32:GenF4:pnum=BLACKPILL_F401CC,upload_method=dfuMethod,xserial=generic,usb=CDCgen,opt=osstd'
fqbn_module='STMicroelectronics:stm32:GenF4:pnum=BLACKPILL_F401CC,upload_method=dfuMethod,xserial=generic,usb=CDCgen,opt=oslto'

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
  mini-v3-a00, mini-v3-a02, mini-v2-a00, mini-v2-a02,
  classic-v2, classic-v3, 40th

Feature environment variables (0 or 1):
  MK61_ENABLE_FOCAL, MK61_ENABLE_TINYBASIC, MK61_ENABLE_WBMP_VIEWER,
  MK61_ENABLE_USB_SCREEN, MK61_ENABLE_EXTENDED_FONT_SETTINGS,
  MK61_USER_EXPLORER_SHORTCUT, MK61_MATH_BACKEND

Other overrides:
  MK61_ARDUINO_CLI, MK61_F401_BUILD_ROOT, MK61_OUTPUT_DIR,
  MK61_APP_MANIFESTS (colon-separated manifest paths)
EOF
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

artifact_name() {
  case "$1" in
    mini-v3-a00) printf '%s' 'mk61s-M-mini-v3-lcd1602-a00-f401.bin' ;;
    mini-v3-a02) printf '%s' 'mk61s-M-mini-v3-lcd1602-a02-f401.bin' ;;
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
      source|file)
        if ! safe_app_relative_path "$value"; then
          manifest_error "$requested:$line_number" \
            "path must be a safe relative ASCII path"
          return 1
        fi
        if [ "$directive" = source ]; then
          case "$value" in
            *.cpp) ;;
            *)
              manifest_error "$requested:$line_number" \
                "source must have the .cpp extension"
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

for value in "$enable_focal" "$enable_tinybasic" "$enable_wbmp" \
             "$enable_usb_screen" "$enable_extended_font" \
             "$enable_user_explorer" "$math_backend"; do
  boolean_valid "$value" || {
    printf 'Error: all MK61 feature values must be 0 or 1.\n' >&2
    exit 2
  }
done
custom_app_count=${#custom_app_names[@]}
any_module=$((enable_focal | enable_tinybasic | enable_wbmp |
              (custom_app_count > 0)))

command -v "$arduino_cli" >/dev/null 2>&1 || {
  printf 'Error: arduino-cli is not installed.\n' >&2
  exit 1
}
if [ "$any_module" -eq 1 ] && ! command -v c++ >/dev/null 2>&1; then
  printf 'Error: a host C++17 compiler is required for the ZX0 packer.\n' >&2
  exit 1
fi

compile_flags="$board_flags"
compile_flags="$compile_flags -DMK61_ENABLE_FOCAL=$enable_focal"
compile_flags="$compile_flags -DMK61_ENABLE_TINYBASIC=$enable_tinybasic"
compile_flags="$compile_flags -DMK61_ENABLE_WBMP_VIEWER=$enable_wbmp"
compile_flags="$compile_flags -DMK61_ENABLE_USB_SCREEN=$enable_usb_screen"
compile_flags="$compile_flags -DMK61_ENABLE_EXTENDED_FONT_SETTINGS=$enable_extended_font"
compile_flags="$compile_flags -DMK61_USER_EXPLORER_SHORTCUT=$enable_user_explorer"
compile_flags="$compile_flags -DMK61_MATH_BACKEND=$math_backend"

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

printf 'Building F401 resident firmware (%s)…\n' "$profile"
"$arduino_cli" compile \
  --fqbn "$fqbn_resident" \
  --build-path "$resident_build" \
  --build-property "compiler.cpp.extra_flags=$compile_flags" \
  "$sketch_dir"

resident_elf="$resident_build/mk61s-M.ino.elf"
resident_bin="$resident_build/mk61s-M.ino.bin"
if [ ! -s "$resident_elf" ] || [ ! -s "$resident_bin" ]; then
  printf 'Error: Arduino build did not create resident ELF and BIN files.\n' >&2
  exit 1
fi

compiler=
objcopy=
size_tool=
nm_tool=
overlay_hex=
if [ "$any_module" -eq 1 ]; then
  # Получаем имена инструментов из раскрытых properties выбранного STM32 Core,
  # не привязываясь к каталогу Arduino15 конкретной ОС или пользователя.
  properties_build="$work/properties"
  properties_file="$work/properties.txt"
  mkdir -p "$properties_build"
  "$arduino_cli" compile \
    --fqbn "$fqbn_module" \
    --build-path "$properties_build" \
    --show-properties=expanded \
    "$sketch_dir" > "$properties_file"
  compiler_path=$(sed -n 's/^compiler\.path=//p' "$properties_file" | head -n 1)
  compiler_cpp=$(sed -n 's/^compiler\.cpp\.cmd=//p' "$properties_file" | head -n 1)
  objcopy_cmd=$(sed -n 's/^compiler\.objcopy\.cmd=//p' "$properties_file" | head -n 1)
  size_cmd=$(sed -n 's/^compiler\.size\.cmd=//p' "$properties_file" | head -n 1)
  compiler_path=${compiler_path%$'\r'}
  compiler_cpp=${compiler_cpp%$'\r'}
  objcopy_cmd=${objcopy_cmd%$'\r'}
  size_cmd=${size_cmd%$'\r'}
  if [ -z "$compiler_path" ] || [ -z "$compiler_cpp" ] || \
     [ -z "$objcopy_cmd" ] || [ -z "$size_cmd" ]; then
    printf 'Error: cannot discover the STM32 compiler tools.\n' >&2
    exit 1
  fi

  compiler=$(normalize_host_path "$compiler_path$compiler_cpp")
  objcopy=$(normalize_host_path "$compiler_path$objcopy_cmd")
  size_tool=$(normalize_host_path "$compiler_path$size_cmd")
  nm_tool=$(normalize_host_path "${compiler_path}${compiler_cpp%g++}nm")
  for tool in "$compiler" "$objcopy" "$size_tool" "$nm_tool"; do
    [ -x "$tool" ] || {
      printf 'Error: required STM32 tool is missing: %s\n' "$tool" >&2
      exit 1
    }
  done

  overlay_hex=$("$nm_tool" -g --defined-only "$resident_elf" | tr -d '\r' |
    awk '$3 == "mk61_module_overlay" && !found { print $1; found=1 }')
  if [ -z "$overlay_hex" ]; then
    printf 'Error: resident ELF has no mk61_module_overlay symbol.\n' >&2
    exit 1
  fi
fi

symbol_hex() {
  "$nm_tool" -g --defined-only "$1" | tr -d '\r' |
    awk -v wanted="$2" '$3 == wanted && !found { print $1; found=1 }
      END { if(!found) exit 1 }'
}

build_module() {
  module_id=$1
  module_file=$2
  module_kind=$3
  module_macro=$4
  module_sketch=$5
  shift 5

  module_build="$work/build-$module_id"
  module_out="$work/module-$module_id"
  mkdir -p "$module_build" "$module_out"
  printf 'Building %s APP with -Os -flto…\n' "$module_id"
  module_compile_flags=$compile_flags
  if [ "$module_macro" != - ]; then
    module_compile_flags="$module_compile_flags -D$module_macro"
  fi
  "$arduino_cli" compile \
    --fqbn "$fqbn_module" \
    --build-path "$module_build" \
    --build-property "compiler.cpp.extra_flags=$module_compile_flags" \
    "$module_sketch"

  objects=()
  for source_name in "$@"; do
    object="$module_build/sketch/$source_name.o"
    [ -s "$object" ] || {
      printf 'Error: APP object was not produced: %s\n' "$object" >&2
      return 1
    }
    objects+=("$object")
  done

  module_elf="$module_out/$module_id.elf"
  module_map="$module_out/$module_id.map"
  "$compiler" \
    -mcpu=cortex-m4 -mfpu=fpv4-sp-d16 -mfloat-abi=hard -mthumb \
    -Os -flto -nostartfiles -nostdlib \
    -Wl,--gc-sections \
    -Wl,--just-symbols="$resident_elf" \
    -Wl,--defsym=MK61_MODULE_ORIGIN=0x$overlay_hex \
    -Wl,-T,"$root/tools/mk61_module.ld" \
    -Wl,-Map,"$module_map" \
    "${objects[@]}" -o "$module_elf"

  unexpected_sections=$("$size_tool" -A "$module_elf" | tr -d '\r' |
    awk '$1 ~ /^\./ && $1 != ".module_image" &&
         $1 != ".module_bss" && ($2 + 0) != 0 { print $1 }')
  if [ -n "$unexpected_sections" ]; then
    printf 'Error: %s has unpacked ELF sections: %s\n' \
      "$module_id" "$unexpected_sections" >&2
    return 1
  fi

  image_start_hex=$(symbol_hex "$module_elf" __module_image_start)
  memory_end_hex=$(symbol_hex "$module_elf" __module_memory_end)
  entry_hex=$(symbol_hex "$module_elf" mk61_module_entry)
  image_start=$((0x$image_start_hex))
  memory_end=$((0x$memory_end_hex))
  entry_address=$((0x$entry_hex))
  memory_size=$((memory_end - image_start))
  entry_offset=$((entry_address - image_start))
  if [ "$memory_size" -le 0 ] || [ "$memory_size" -gt 20480 ] || \
     [ "$entry_offset" -lt 0 ]; then
    printf 'Error: invalid APP SRAM layout for %s.\n' "$module_id" >&2
    return 1
  fi

  module_image="$module_out/$module_id.bin"
  "$objcopy" -O binary -j .module_image "$module_elf" "$module_image"
  module_target="$bundle_stage/$module_file"
  mkdir -p "$(dirname "$module_target")"
  MK61_MODULE_PACK_BIN="$work/mk61_module_pack" \
    "$root/tools/build_mk61_module_pack.sh" \
    --kind "$module_kind" \
    --resident "$resident_bin" \
    --image "$module_image" \
    --memory-size "$memory_size" \
    --entry-offset "$entry_offset" \
    --load-address "0x$overlay_hex" \
    --require-zx0 \
    --output "$module_target"
  "$size_tool" -A "$module_elf"
}

build_custom_app() {
  custom_index=$1
  custom_name=${custom_app_names[$custom_index]}
  custom_id="${custom_app_ids[$custom_index]}-$custom_index"
  custom_dir=${custom_app_dirs[$custom_index]}
  custom_sketch="$work/sketch-app-$custom_id/mk61s-M"
  custom_source_root="$custom_sketch/src/mk61_app"
  mkdir -p "$custom_sketch" "$custom_source_root"
  cp "$root/tools/loadable_app_template/mk61s-M.ino" "$custom_sketch/"
  cp "$root/code/loadable_app_api.hpp" \
     "$root/code/loadable_module_abi.hpp" \
     "$root/code/rust_types.h" \
     "$custom_sketch/"

  custom_all_files="${custom_app_sources[$custom_index]}"
  if [ -n "${custom_app_files[$custom_index]}" ]; then
    custom_all_files="$custom_all_files ${custom_app_files[$custom_index]}"
  fi
  for relative in $custom_all_files; do
    target="$custom_source_root/$relative"
    mkdir -p "$(dirname "$target")"
    cp "$custom_dir/$relative" "$target"
  done

  custom_objects=()
  for relative in ${custom_app_sources[$custom_index]}; do
    custom_objects+=("src/mk61_app/$relative")
  done
  build_module "app-$custom_id" "Apps/$custom_name.APP" app - \
    "$custom_sketch" "${custom_objects[@]}"
}

cp "$resident_bin" "$bundle_stage/$firmware_name"
if [ "$enable_focal" -eq 1 ]; then
  build_module focal System/FOCAL.APP focal MK61_BUILD_FOCAL_MODULE "$sketch_dir" \
    focal.cpp focal_module_entry.cpp
fi
if [ "$enable_tinybasic" -eq 1 ]; then
  build_module tinybasic System/BASIC.APP tinybasic MK61_BUILD_TINYBASIC_MODULE "$sketch_dir" \
    tinybasic.cpp tinybasic_module_entry.cpp
fi
if [ "$enable_wbmp" -eq 1 ]; then
  build_module wbmp System/WBMP.APP wbmp-viewer MK61_BUILD_WBMP_MODULE "$sketch_dir" \
    wbmp.cpp a00_image_multiplex.cpp image1_viewer.cpp \
    image1_viewer_module_entry.cpp
fi
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
      "$bundle_dir/$firmware_name" "$bundle_dir/build.apps"
if [ -d "$bundle_dir/System" ]; then
  rmdir "$bundle_dir/System" 2>/dev/null || true
fi
# Apps — полностью генерируемая часть комплекта. Чистая замена не позволяет
# удалённому из manifest приложению незаметно остаться от предыдущей сборки.
if [ -d "$bundle_dir/Apps" ]; then
  rm -rf "$bundle_dir/Apps"
fi
cp -R "$bundle_stage/." "$bundle_dir/"
printf '%s\n' "$compile_flags" > "$bundle_dir/build.flags"
{
  printf 'format 1\n'
  for index in "${!custom_app_names[@]}"; do
    printf 'app Apps/%s.APP\n' "${custom_app_names[$index]}"
  done
} > "$bundle_dir/build.apps"

printf 'Built F401 bundle: %s\n' "$bundle_dir"
find "$bundle_dir" -maxdepth 2 -type f -print | sort

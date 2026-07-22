#!/usr/bin/env bash

# Собирает согласованный комплект для STM32F401CC: resident-прошивку и
# включённые модули, привязанные к её точному ELF/.bin. Resident остаётся на
# штатном -Os, чтобы экспортируемые символы не локализовал LTO; каждый модуль
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

fqbn_resident='STMicroelectronics:stm32:GenF4:pnum=BLACKPILL_F401CC,upload_method=dfuMethod,xserial=generic,usb=CDCgen,opt=osstd'
fqbn_module='STMicroelectronics:stm32:GenF4:pnum=BLACKPILL_F401CC,upload_method=dfuMethod,xserial=generic,usb=CDCgen,opt=oslto'

usage() {
  cat <<'EOF'
Build a matched STM32F401CC firmware/module bundle.

Usage:
  tools/build_f401_bundle.sh [--profile ID] [--output-dir DIR]
                              [--build-root DIR]

Profiles:
  mini-v3-a00, mini-v3-a02, mini-v2-a00, mini-v2-a02,
  classic-v2, classic-v3, 40th

Feature environment variables (0 or 1):
  MK61_ENABLE_FOCAL, MK61_ENABLE_TINYBASIC, MK61_ENABLE_WBMP_VIEWER,
  MK61_ENABLE_USB_SCREEN, MK61_ENABLE_EXTENDED_FONT_SETTINGS,
  MK61_USER_EXPLORER_SHORTCUT, MK61_MATH_BACKEND

Other overrides:
  MK61_ARDUINO_CLI, MK61_F401_BUILD_ROOT, MK61_OUTPUT_DIR
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
any_module=$((enable_focal | enable_tinybasic | enable_wbmp))

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
  if [ -z "$compiler_path" ] || [ -z "$compiler_cpp" ] || \
     [ -z "$objcopy_cmd" ] || [ -z "$size_cmd" ]; then
    printf 'Error: cannot discover the STM32 compiler tools.\n' >&2
    exit 1
  fi

  compiler="$compiler_path$compiler_cpp"
  objcopy="$compiler_path$objcopy_cmd"
  size_tool="$compiler_path$size_cmd"
  nm_tool="${compiler_path}${compiler_cpp%g++}nm"
  for tool in "$compiler" "$objcopy" "$size_tool" "$nm_tool"; do
    [ -x "$tool" ] || {
      printf 'Error: required STM32 tool is missing: %s\n' "$tool" >&2
      exit 1
    }
  done

  overlay_hex=$("$nm_tool" -g --defined-only "$resident_elf" |
    awk '$3 == "mk61_module_overlay" { print $1; exit }')
  if [ -z "$overlay_hex" ]; then
    printf 'Error: resident ELF has no mk61_module_overlay symbol.\n' >&2
    exit 1
  fi
fi

symbol_hex() {
  "$nm_tool" -g --defined-only "$1" |
    awk -v wanted="$2" '$3 == wanted { print $1; found=1; exit }
      END { if(!found) exit 1 }'
}

build_module() {
  module_id=$1
  module_file=$2
  module_kind=$3
  module_macro=$4
  shift 4

  module_build="$work/build-$module_id"
  module_out="$work/module-$module_id"
  mkdir -p "$module_build" "$module_out"
  printf 'Building %s module with -Os -flto…\n' "$module_id"
  "$arduino_cli" compile \
    --fqbn "$fqbn_module" \
    --build-path "$module_build" \
    --build-property "compiler.cpp.extra_flags=$compile_flags -D$module_macro" \
    "$sketch_dir"

  objects=()
  for source_name in "$@"; do
    object="$module_build/sketch/$source_name.o"
    [ -s "$object" ] || {
      printf 'Error: module object was not produced: %s\n' "$object" >&2
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

  unexpected_sections=$("$size_tool" -A "$module_elf" |
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
    printf 'Error: invalid SRAM layout for %s.\n' "$module_id" >&2
    return 1
  fi

  module_image="$module_out/$module_id.bin"
  "$objcopy" -O binary -j .module_image "$module_elf" "$module_image"
  "$root/tools/build_mk61_module_pack.sh" \
    --kind "$module_kind" \
    --resident "$resident_bin" \
    --image "$module_image" \
    --memory-size "$memory_size" \
    --entry-offset "$entry_offset" \
    --load-address "0x$overlay_hex" \
    --require-zx0 \
    --output "$bundle_stage/$module_file"
  "$size_tool" -A "$module_elf"
}

cp "$resident_bin" "$bundle_stage/$firmware_name"
if [ "$enable_focal" -eq 1 ]; then
  build_module focal FOCAL.MOD focal MK61_BUILD_FOCAL_MODULE \
    focal.cpp focal_module_entry.cpp
fi
if [ "$enable_tinybasic" -eq 1 ]; then
  build_module tinybasic BASIC.MOD tinybasic MK61_BUILD_TINYBASIC_MODULE \
    tinybasic.cpp tinybasic_module_entry.cpp
fi
if [ "$enable_wbmp" -eq 1 ]; then
  build_module wbmp WBMP.MOD wbmp-viewer MK61_BUILD_WBMP_MODULE \
    wbmp.cpp a00_image_multiplex.cpp image1_viewer.cpp \
    image1_viewer_module_entry.cpp
fi

bundle_name=${firmware_name%.bin}
bundle_dir="$output_root/$bundle_name"
mkdir -p "$bundle_dir"
# Удаляются только артефакты, которыми владеет этот сборщик: выключенный ключ
# не должен оставлять в новом комплекте модуль от предыдущей сборки.
rm -f "$bundle_dir/FOCAL.MOD" "$bundle_dir/BASIC.MOD" \
      "$bundle_dir/WBMP.MOD" "$bundle_dir/$firmware_name"
cp -R "$bundle_stage/." "$bundle_dir/"
printf '%s\n' "$compile_flags" > "$bundle_dir/build.flags"

printf 'Built F401 bundle: %s\n' "$bundle_dir"
find "$bundle_dir" -maxdepth 1 -type f -print | sort

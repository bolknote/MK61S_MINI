#!/usr/bin/env bash

set -euo pipefail

die() {
  printf 'MK61s F401 + APP: %s\n' "$*" >&2
  exit 1
}

require_value() {
  [ "$#" -ge 2 ] && [ -n "$2" ] ||
    die "$1 requires a value"
}

profile_valid() {
  case "$1:$2" in
    mini-v2:lcd1602-a00|mini-v2:lcd1602-a02|\
    mini-v3:lcd1602-a00|mini-v3:lcd1602-a02|\
    classic-v2:uc1609|classic-v3:uc1609|40th:uc1609)
      return 0
      ;;
  esac
  return 1
}

check_profile() {
  local platform= display= sketch=
  while [ "$#" -gt 0 ]; do
    case "$1" in
      --platform)
        require_value "$@"; platform=$2; shift 2 ;;
      --display)
        require_value "$@"; display=$2; shift 2 ;;
      --sketch)
        require_value "$@"; sketch=$2; shift 2 ;;
      *) die "unknown check-profile option: $1" ;;
    esac
  done
  profile_valid "$platform" "$display" ||
    die "incompatible platform/display pair: $platform + $display"
  [ -f "$sketch/mk61s-M.ino" ] && [ -f "$sketch/config.h" ] ||
    die 'open code/mk61s-M.ino before selecting this board'
}

symbol_hex() {
  local elf=$1 symbol=$2
  "$nm_tool" -g --defined-only "$elf" |
    awk -v wanted="$symbol" '$3 == wanted && !found {
      print $1
      found = 1
    }
    END { if(!found) exit 1 }'
}

crc32_file() {
  local file=$1 trailer
  command -v gzip >/dev/null 2>&1 ||
    die 'gzip is required to calculate APP checksums'
  trailer=$(gzip -cn "$file" | tail -c 8 | od -An -v -tu1)
  set -- $trailer
  [ "$#" -eq 8 ] || die "cannot calculate CRC32 for $file"
  printf '%u' "$(( $1 | ($2 << 8) | ($3 << 16) | ($4 << 24) ))"
}

emit_byte() {
  local value=$(( $1 & 255 )) octal
  octal=$(printf '%03o' "$value")
  printf "\\$octal"
}

emit_le16() {
  emit_byte "$1"
  emit_byte "$(( $1 >> 8 ))"
}

emit_le32() {
  emit_byte "$1"
  emit_byte "$(( $1 >> 8 ))"
  emit_byte "$(( $1 >> 16 ))"
  emit_byte "$(( $1 >> 24 ))"
}

pack_uncompressed() {
  local kind=$1 resident=$2 image=$3 memory_size=$4
  local entry_offset=$5 load_address=$6 output=$7
  local resident_size image_size resident_crc image_crc header header_crc

  resident_size=$(wc -c < "$resident" | tr -d '[:space:]')
  image_size=$(wc -c < "$image" | tr -d '[:space:]')
  [ "$resident_size" -gt 0 ] && [ "$resident_size" -le 524288 ] ||
    die 'resident BIN has an invalid size'
  [ "$image_size" -gt 0 ] && [ "$image_size" -le "$memory_size" ] ||
    die 'System APP image has an invalid size'
  [ "$memory_size" -le 20480 ] ||
    die "System APP uses $memory_size bytes; maximum is 20480"
  [ "$((image_size + 64))" -le 20544 ] ||
    die "System APP container uses $((image_size + 64)) bytes; maximum is 20544"

  resident_crc=$(crc32_file "$resident")
  image_crc=$(crc32_file "$image")
  header="${output}.header"

  {
    printf 'MK61APP\000'
    emit_le16 1
    emit_le16 64
    emit_le16 2
    emit_byte "$kind"
    emit_byte 0
    emit_le32 0
    emit_le32 "$load_address"
    emit_le32 "$image_size"
    emit_le32 "$image_size"
    emit_le32 "$memory_size"
    emit_le32 "$entry_offset"
    emit_le32 "$resident_size"
    emit_le32 "$resident_crc"
    emit_le32 "$image_crc"
    emit_le32 "$image_crc"
    emit_le32 0
  } > "$header"
  [ "$(wc -c < "$header" | tr -d '[:space:]')" -eq 60 ] ||
    die 'internal APP header size error'
  header_crc=$(crc32_file "$header")
  emit_le32 "$header_crc" >> "$header"
  cat "$header" "$image" > "$output"
  rm -f "$header"
}

build_module() {
  local id=$1 file_name=$2 kind=$3 entry_symbol=$4 object_name=$5
  local object module_dir module_elf module_map module_image
  local unexpected image_start_hex memory_end_hex entry_hex
  local image_start memory_end entry_address memory_size entry_offset

  object="$build_path/sketch/$object_name"
  [ -s "$object" ] ||
    die "Arduino did not produce $object_name"
  module_dir="$stage/modules/$id"
  mkdir -p "$module_dir" "$stage/System"
  module_elf="$module_dir/$id.elf"
  module_map="$module_dir/$id.map"
  module_image="$module_dir/$id.bin"

  "$compiler" \
    -mcpu=cortex-m4 -mfpu=fpv4-sp-d16 -mfloat-abi=hard -mthumb \
    -Os -nostartfiles -nostdlib \
    -Wl,--gc-sections \
    -Wl,--just-symbols="$resident_elf" \
    -Wl,--defsym=MK61_MODULE_ORIGIN=0x"$overlay_hex" \
    -Wl,--defsym=mk61_module_entry="$entry_symbol" \
    -Wl,-T,"$linker_script" \
    -Wl,-Map,"$module_map" \
    "$object" -o "$module_elf"

  unexpected=$("$size_tool" -A "$module_elf" |
    awk '$1 ~ /^\./ && $1 != ".module_image" &&
         $1 != ".module_bss" && ($2 + 0) != 0 { print $1 }')
  [ -z "$unexpected" ] ||
    die "$file_name has unexpected ELF sections: $unexpected"

  image_start_hex=$(symbol_hex "$module_elf" __module_image_start) ||
    die "$file_name has no image start symbol"
  memory_end_hex=$(symbol_hex "$module_elf" __module_memory_end) ||
    die "$file_name has no memory end symbol"
  entry_hex=$(symbol_hex "$module_elf" "$entry_symbol") ||
    die "$file_name has no entry symbol"
  image_start=$((0x$image_start_hex))
  memory_end=$((0x$memory_end_hex))
  entry_address=$((0x$entry_hex))
  memory_size=$((memory_end - image_start))
  entry_offset=$((entry_address - image_start))
  [ "$memory_size" -gt 0 ] && [ "$memory_size" -le 20480 ] ||
    die "$file_name does not fit the 20 KiB SRAM overlay"
  [ "$entry_offset" -ge 0 ] && [ "$entry_offset" -lt 20480 ] &&
    [ "$((entry_offset & 1))" -eq 0 ] ||
    die "$file_name has an invalid entry point"

  "$objcopy" -O binary -j .module_image "$module_elf" "$module_image"
  [ "$entry_offset" -lt "$(wc -c < "$module_image" |
      tr -d '[:space:]')" ] ||
    die "$file_name entry point is outside its stored image"
  pack_uncompressed "$kind" "$resident_bin" "$module_image" \
    "$memory_size" "$entry_offset" "$((0x$overlay_hex))" \
    "$stage/System/$file_name"
  printf 'MK61s APP: %-10s %5s bytes, SRAM %5s / 20480\n' \
    "$file_name" "$(wc -c < "$stage/System/$file_name" |
      tr -d '[:space:]')" "$memory_size"
}

build_bundle() {
  local compiler= objcopy= size_tool_arg= build_path_arg=
  local sketch= project= bundle= focal= basic= wbmp= compile_flags=
  while [ "$#" -gt 0 ]; do
    case "$1" in
      --compiler)
        require_value "$@"; compiler=$2; shift 2 ;;
      --objcopy)
        require_value "$@"; objcopy=$2; shift 2 ;;
      --size)
        require_value "$@"; size_tool_arg=$2; shift 2 ;;
      --build-path)
        require_value "$@"; build_path_arg=$2; shift 2 ;;
      --sketch)
        require_value "$@"; sketch=$2; shift 2 ;;
      --project)
        require_value "$@"; project=$2; shift 2 ;;
      --bundle)
        require_value "$@"; bundle=$2; shift 2 ;;
      --focal)
        require_value "$@"; focal=$2; shift 2 ;;
      --basic)
        require_value "$@"; basic=$2; shift 2 ;;
      --wbmp)
        require_value "$@"; wbmp=$2; shift 2 ;;
      --compile-flags)
        require_value "$@"; compile_flags=$2; shift 2 ;;
      *) die "unknown build option: $1" ;;
    esac
  done

  [ -x "$compiler" ] || die "ARM compiler not found: $compiler"
  [ -x "$objcopy" ] || die "ARM objcopy not found: $objcopy"
  [ -x "$size_tool_arg" ] || die "ARM size tool not found: $size_tool_arg"
  [ -n "$build_path_arg" ] && [ -d "$build_path_arg" ] ||
    die 'Arduino build path was not found'
  [ -n "$project" ] && [ -n "$bundle" ] ||
    die 'Arduino project or bundle name is missing'
  case "$focal:$basic:$wbmp" in
    [01]:[01]:[01]) ;;
    *) die 'System APP selections must be 0 or 1' ;;
  esac

  build_path=$build_path_arg
  size_tool=$size_tool_arg
  nm_tool="$(dirname "$compiler")/arm-none-eabi-nm"
  [ -x "$nm_tool" ] || die "ARM nm tool not found: $nm_tool"
  linker_script="$(cd "$(dirname "$0")" && pwd)/mk61_module.ld"
  resident_elf="$build_path/$project.elf"
  resident_bin="$build_path/$project.bin"
  [ -s "$resident_elf" ] && [ -s "$resident_bin" ] ||
    die 'Arduino did not produce resident ELF and BIN files'
  overlay_hex=$(symbol_hex "$resident_elf" mk61_module_overlay) ||
    die 'resident ELF has no mk61_module_overlay symbol'

  stage="$build_path/mk61-system-apps/$bundle"
  case "$stage" in "$build_path"/*) ;; *) die 'unsafe staging path' ;; esac
  rm -rf "$stage"
  mkdir -p "$stage/System"
  cp "$resident_bin" "$stage/$bundle.bin"

  [ "$focal" -eq 0 ] ||
    build_module focal FOCAL.APP 1 mk61_ide_focal_module_entry \
      mk61_ide_focal_app.cpp.o
  [ "$basic" -eq 0 ] ||
    build_module basic BASIC.APP 2 mk61_ide_basic_module_entry \
      mk61_ide_basic_app.cpp.o
  [ "$wbmp" -eq 0 ] ||
    build_module wbmp WBMP.APP 3 mk61_ide_wbmp_module_entry \
      mk61_ide_wbmp_app.cpp.o

  output_root="$(cd "$sketch/.." && pwd)/binary"
  output="$output_root/$bundle"
  mkdir -p "$output/System"
  cp "$stage/$bundle.bin" "$output/$bundle.bin"
  for canonical in FOCAL.APP BASIC.APP WBMP.APP; do
    if [ -f "$stage/System/$canonical" ]; then
      cp "$stage/System/$canonical" "$output/System/$canonical"
    else
      rm -f "$output/System/$canonical"
    fi
  done
  rmdir "$output/System" 2>/dev/null || true
  printf '%s\n' "$compile_flags" > "$output/build.flags"
  printf 'format 1\n' > "$output/build.apps"

  printf '\nMK61s F401 bundle built by Arduino IDE:\n  %s\n' "$output"
  printf 'After Upload, copy the generated System directory to /System on MK61S C5.\n\n'
}

[ "$#" -gt 0 ] || die 'missing command'
command=$1
shift
case "$command" in
  check-profile) check_profile "$@" ;;
  build) build_bundle "$@" ;;
  *) die "unknown command: $command" ;;
esac

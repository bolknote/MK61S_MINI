#!/usr/bin/env bash
set -euo pipefail

root="$(cd "$(dirname "$0")/.." && pwd)"
out="${TMPDIR:-/tmp}/mk61_board_profile_self_test"
sanitizer_flags=()
if [[ "${MK61_TEST_SANITIZERS:-0}" == "1" ]]; then
  sanitizer_flags=(-fsanitize=address,undefined -fno-omit-frame-pointer)
fi

common=(
  -std=c++17 -Wall -Wextra -Werror
  "${sanitizer_flags[@]}"
  -I"$root/tests/program_store_shim"
  -I"$root/code"
  "$root/tests/board_profile_self_test.cpp"
)

clang++ "${common[@]}" -DREVISION_V3 -DMK61_CONFIG_EXPECT_V3 -o "$out-v3"
"$out-v3"

clang++ -Os "${common[@]}" -DREVISION_V3 -DSTM32F411xE \
  -DMK61_CONFIG_EXPECT_V3 -DMK61_CONFIG_EXPECT_NATIVE_HOT_PATHS \
  -o "$out-f411-native-core"
"$out-f411-native-core"

clang++ -O3 "${common[@]}" -DREVISION_V3 -DSTM32F411xE \
  -DMK61_CONFIG_EXPECT_V3 -DMK61_CONFIG_EXPECT_GENERIC_HOT_PATHS \
  -o "$out-f411-o3-generic-core"
"$out-f411-o3-generic-core"

clang++ -Os "${common[@]}" -DREVISION_V3 -DSTM32F401xC \
  -DMK61_CONFIG_EXPECT_V3 -DMK61_CONFIG_EXPECT_GENERIC_HOT_PATHS \
  -o "$out-f401-generic-core"
"$out-f401-generic-core"

clang++ "${common[@]}" -DREVISION_V3 -DARDUINO_BLACKPILL_F401CC \
  -DMK61_CONFIG_EXPECT_V3 -DMK61_CONFIG_EXPECT_LOADABLE_MODULES \
  -o "$out-f401-modules"
"$out-f401-modules"

clang++ "${common[@]}" -DREVISION_V3 -DARDUINO_BLACKPILL_F401CC \
  -DMK61_ENABLE_USB_SCREEN=1 -DMK61_ENABLE_CHIP8=1 \
  -DMK61_CONFIG_EXPECT_V3 -DMK61_CONFIG_EXPECT_LOADABLE_MODULES \
  -DMK61_CONFIG_EXPECT_GRAPHICS -DMK61_CONFIG_EXPECT_CHIP8 \
  -o "$out-f401-graphics-modules"
"$out-f401-graphics-modules"

clang++ "${common[@]}" -DREVISION_V3 -DARDUINO_BLACKPILL_F401CC \
  -DMK61_ENABLE_USB_SCREEN=1 -DMK61_ENABLE_MARKDOWN_VIEWER=0 \
  -DMK61_CONFIG_EXPECT_V3 -DMK61_CONFIG_EXPECT_LOADABLE_MODULES \
  -DMK61_CONFIG_EXPECT_GRAPHICS -DMK61_CONFIG_EXPECT_MARKDOWN_DISABLED \
  -o "$out-f401-wbmp-module"
"$out-f401-wbmp-module"

clang++ "${common[@]}" -DREVISION_V3 -DARDUINO_BLACKPILL_F401CC \
  -DMK61_ENABLE_LOADABLE_MODULES=0 \
  -DMK61_CONFIG_EXPECT_V3 -DMK61_CONFIG_EXPECT_MODULES_DISABLED \
  -o "$out-f401-builtins"
"$out-f401-builtins"

clang++ "${common[@]}" -DREVISION_V3 -DARDUINO_BLACKPILL_F401CC \
  -DMK61_ENABLE_FOCAL=0 -DMK61_ENABLE_TINYBASIC=0 \
  -DMK61_ENABLE_WBMP_VIEWER=0 -DMK61_ENABLE_MARKDOWN_VIEWER=0 \
  -DMK61_CONFIG_EXPECT_V3 -DMK61_CONFIG_EXPECT_WBMP_DISABLED \
  -DMK61_CONFIG_EXPECT_MARKDOWN_DISABLED \
  -DMK61_CONFIG_EXPECT_NO_MODULE_ARTIFACTS \
  -o "$out-f401-no-modules"
"$out-f401-no-modules"

clang++ "${common[@]}" -DREVISION_V3 -DMK61_CONFIG_EXPECT_V3 \
  -DMK61_ENABLE_WBMP_VIEWER=0 -DMK61_CONFIG_EXPECT_WBMP_DISABLED \
  -o "$out-v3-no-wbmp"
"$out-v3-no-wbmp"

clang++ "${common[@]}" -DREVISION_V3 -DMK61_ENABLE_USB_SCREEN=1 \
  -DMK61_ENABLE_CHIP8=1 -DMK61_CONFIG_EXPECT_V3 \
  -DMK61_CONFIG_EXPECT_GRAPHICS -DMK61_CONFIG_EXPECT_CHIP8 \
  -o "$out-v3-usb-chip8"
"$out-v3-usb-chip8"

clang++ "${common[@]}" -DREVISION_V2 -DMK61_CONFIG_EXPECT_V2 -o "$out-v2"
"$out-v2"

clang++ "${common[@]}" -DREVISION_V3 -DMK61_OLED1602_WS0010 \
  -DMK61_CONFIG_EXPECT_V3 -DMK61_CONFIG_EXPECT_WS0010 -o "$out-ws0010"
"$out-ws0010"

clang++ "${common[@]}" -DREVISION_V3 -DMK61_OLED1602_WS0010 \
  -DMK61_WS0010_GRAPHICS_100X16=1 -DMK61_ENABLE_MARKDOWN_VIEWER=0 \
  -DMK61_CONFIG_EXPECT_V3 -DMK61_CONFIG_EXPECT_WS0010 \
  -DMK61_CONFIG_EXPECT_FULLSCREEN_BITMAP \
  -DMK61_CONFIG_EXPECT_MARKDOWN_DISABLED -o "$out-ws0010-wbmp"
"$out-ws0010-wbmp"

clang++ "${common[@]}" -DREVISION_V3 -DMK61_OLED1602_WS0010 \
  -DMK61_WS0010_GRAPHICS_100X16=1 -DMK61_ENABLE_WBMP_VIEWER=1 \
  -DMK61_CONFIG_EXPECT_V3 -DMK61_CONFIG_EXPECT_WS0010 \
  -DMK61_CONFIG_EXPECT_FULLSCREEN_BITMAP -DMK61_CONFIG_EXPECT_WBMP_ENABLED \
  -o "$out-ws0010-wbmp-markdown"
"$out-ws0010-wbmp-markdown"

clang++ "${common[@]}" -DMK61_BOARD_CLASSIC_V2 \
  -DMK61_CONFIG_EXPECT_CLASSIC_V2 -o "$out-classic-v2"
"$out-classic-v2"

clang++ "${common[@]}" -DMK61_BOARD_CLASSIC_V3 \
  -DMK61_CONFIG_EXPECT_CLASSIC_V3 -o "$out-classic-v3"
"$out-classic-v3"

# Прежняя комбинация флагов остаётся алиасом Classic V2.
clang++ "${common[@]}" -DMK61_DISPLAY_UC1609 -DMK61_KEYBOARD_CLASSIC \
  -DMK61_CONFIG_EXPECT_CLASSIC_V2 -o "$out-classic-legacy"
"$out-classic-legacy"

clang++ "${common[@]}" -DMK61_BOARD_40TH \
  -DMK61_CONFIG_EXPECT_40TH -o "$out-40th"
"$out-40th"

if clang++ "${common[@]}" -DREVISION_V2 -DREVISION_V3 -o "$out-invalid" \
    >/dev/null 2>&1; then
  echo "conflicting board revisions unexpectedly compiled" >&2
  exit 1
fi

if clang++ "${common[@]}" -DREVISION_V3 -DMK61_LCD1602_A00 \
    -DMK61_OLED1602_WS0010 -o "$out-invalid-display-profile" \
    >/dev/null 2>&1; then
  echo "conflicting A00/WS0010 profiles unexpectedly compiled" >&2
  exit 1
fi

if clang++ "${common[@]}" -DREVISION_V2 -DMK61_OLED1602_WS0010 \
    -DMK61_LCD1602_BUSY_FLAG=1 -o "$out-invalid-ws0010-read" \
    >/dev/null 2>&1; then
  echo "unqualified V2 WS0010 busy-flag read unexpectedly compiled" >&2
  exit 1
fi

if clang++ "${common[@]}" -DREVISION_V3 -DMK61_OLED1602_WS0010 \
    -DMK61_WS0010_BRIGHTNESS_CONTROL=1 -o "$out-invalid-ws0010-brightness" \
    >/dev/null 2>&1; then
  echo "unqualified WS0010 brightness command unexpectedly compiled" >&2
  exit 1
fi

if clang++ "${common[@]}" -DMK61_BOARD_CLASSIC_V2 -DMK61_BOARD_CLASSIC_V3 \
    -o "$out-invalid-classic" >/dev/null 2>&1; then
  echo "conflicting Classic profiles unexpectedly compiled" >&2
  exit 1
fi

if clang++ "${common[@]}" -DREVISION_V2 -DMK61_BOARD_CLASSIC_V3 \
    -o "$out-invalid-revision" >/dev/null 2>&1; then
  echo "Classic profile with mini REVISION_V2 unexpectedly compiled" >&2
  exit 1
fi

if clang++ "${common[@]}" -DREVISION_V3 -DMK61_CONFIG_EXPECT_V3 \
    -DMK61_ENABLE_WBMP_VIEWER=2 -o "$out-invalid-wbmp" \
    >/dev/null 2>&1; then
  echo "invalid WBMP viewer flag unexpectedly compiled" >&2
  exit 1
fi

if clang++ "${common[@]}" -DREVISION_V3 -DMK61_CONFIG_EXPECT_V3 \
    -DMK61_ENABLE_MARKDOWN_VIEWER=2 -o "$out-invalid-markdown" \
    >/dev/null 2>&1; then
  echo "invalid Markdown viewer flag unexpectedly compiled" >&2
  exit 1
fi

if clang++ "${common[@]}" -DREVISION_V3 -DMK61_CONFIG_EXPECT_V3 \
    -DMK61_ENABLE_CHIP8=1 -o "$out-invalid-chip8-display" \
    >/dev/null 2>&1; then
  echo "CHIP-8 without compiled graphics unexpectedly compiled" >&2
  exit 1
fi

if clang++ "${common[@]}" -DREVISION_V3 -DMK61_CONFIG_EXPECT_V3 \
    -DMK61_ENABLE_USB_SCREEN=2 -o "$out-invalid-usb-screen" \
    >/dev/null 2>&1; then
  echo "invalid USB Screen flag unexpectedly compiled" >&2
  exit 1
fi

if clang++ "${common[@]}" -DREVISION_V3 -DMK61_CONFIG_EXPECT_V3 \
    -DMK61_ENABLE_LOADABLE_MODULES=2 -o "$out-invalid-modules" \
    >/dev/null 2>&1; then
  echo "invalid loadable module flag unexpectedly compiled" >&2
  exit 1
fi

if clang++ "${common[@]}" -DREVISION_V3 -DMK61_CONFIG_EXPECT_V3 \
    -DMK61_ENABLE_FOCAL=2 -o "$out-invalid-focal" \
    >/dev/null 2>&1; then
  echo "invalid FOCAL flag unexpectedly compiled" >&2
  exit 1
fi

if clang++ "${common[@]}" -DREVISION_V3 -DMK61_CONFIG_EXPECT_V3 \
    -DMK61_ENABLE_TINYBASIC=2 -o "$out-invalid-tinybasic" \
    >/dev/null 2>&1; then
  echo "invalid TinyBASIC flag unexpectedly compiled" >&2
  exit 1
fi

if clang++ "${common[@]}" -DREVISION_V3 -DMK61_CONFIG_EXPECT_V3 \
    -DMK61_ENABLE_SPI1_ARBITER=0 -DMK61_ENABLE_SPI1_DMA=1 \
    -o "$out-invalid-spi1-dma" >/dev/null 2>&1; then
  echo "SPI1 DMA without the arbiter unexpectedly compiled" >&2
  exit 1
fi

#ifndef MK61_DISPLAY_PROFILE_HPP
#define MK61_DISPLAY_PROFILE_HPP
#include "rust_types.h"
namespace lcd_display {
struct TextProfile {
  u8 rows;
  u8 glyph_width;
  u8 glyph_height;
  u8 line_gap;
};

#if MK61_HAS_GRAPHICAL_TEXT_SETTINGS
// Виртуальный USB-дисплей и UC1609 используют общую текстовую геометрию 192x64.
// Эти профили не зависят от геометрии физического LCD1602, чтобы LCD-сборка
// сохраняла выбранный шрифт USB-экрана между сеансами.
static constexpr u8 FONT_10X16_ROWS = 4;
static constexpr u8 FONT_5X8_ROWS = 6;
static constexpr u8 FONT_5X9_ROWS = 7;
static constexpr u8 FONT_3X5_ROWS = 10;
static constexpr u8 MIN_ROWS = 4;
static constexpr u8 COMPACT_ROWS = 8;
static constexpr u8 GRAPHICS_MAX_ROWS = FONT_3X5_ROWS;
static constexpr u8 PIXEL_WIDTH = 192;
static constexpr u8 PIXEL_HEIGHT = 64;
static constexpr u8 CELL_WIDTH = 12;
static constexpr u8 CELL_HEIGHT = 16;

static inline u8 clamp_u8(u8 value, u8 min_value, u8 max_value) {
  if(value < min_value) return min_value;
  if(value > max_value) return max_value;
  return value;
}

static inline u8 maxLineGap(u8 rows, u8 glyph_height) {
  if(rows <= 1) return 0;
  if((u16) rows * glyph_height >= PIXEL_HEIGHT) return 0;
  return (u8) ((PIXEL_HEIGHT - (u16) rows * glyph_height) / (rows - 1));
}

static constexpr TextProfile textProfile5x8(void) {
  return {FONT_5X8_ROWS, 5, 8, 2};
}

static constexpr TextProfile textProfile10x16(void) {
  return {FONT_10X16_ROWS, 10, 16, 0};
}

static constexpr TextProfile textProfile5x9(void) {
  return {FONT_5X9_ROWS, 5, 9, 0};
}

static constexpr TextProfile textProfile3x5(void) {
  return {FONT_3X5_ROWS, 3, 5, 1};
}

static inline bool isTextProfile3x5(TextProfile profile) {
  return profile.glyph_width == 3 && profile.glyph_height == 5;
}

static constexpr TextProfile defaultGraphicalTextProfileForRows(u8 rows) {
  if(rows <= FONT_10X16_ROWS) return textProfile10x16();
  if(rows <= FONT_5X8_ROWS) return textProfile5x8();
  if(rows == FONT_5X9_ROWS) return textProfile5x9();
  return textProfile3x5();
}

static inline TextProfile presetGraphicalTextProfile(TextProfile profile) {
  if(profile.rows <= FONT_10X16_ROWS || profile.glyph_width >= 10 ||
     profile.glyph_height >= 16) return textProfile10x16();
  if(profile.glyph_width <= 3 || profile.rows >= FONT_3X5_ROWS) return textProfile3x5();
  if(profile.glyph_height >= 9 || profile.rows == FONT_5X9_ROWS) return textProfile5x9();
  return textProfile5x8();
}

static inline TextProfile normalizeGraphicalTextProfile(TextProfile profile) {
#if MK61_ENABLE_EXTENDED_FONT_SETTINGS
  profile.rows = clamp_u8(profile.rows, MIN_ROWS, GRAPHICS_MAX_ROWS);
  profile.glyph_width = clamp_u8(profile.glyph_width, 3, 10);

  const u8 max_height = PIXEL_HEIGHT / profile.rows;
  profile.glyph_height = clamp_u8(profile.glyph_height, 5, max_height);
  profile.line_gap = clamp_u8(profile.line_gap, 0, maxLineGap(profile.rows, profile.glyph_height));
  return profile;
#else
  return presetGraphicalTextProfile(profile);
#endif
}
#endif

}
#endif

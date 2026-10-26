#ifndef MK61_SEGMENT_LCD1602_HPP
#define MK61_SEGMENT_LCD1602_HPP

#include "lcd_charset.hpp"

// A character LCD cannot draw twelve independent seven-segment cells directly.
// Reuse recognizable CGROM digits/letters first, then spend its eight CGRAM
// slots on the remaining distinct masks in the current frame.
namespace segment_lcd1602 {

static constexpr u8 CELLS = 12;
static constexpr u8 CUSTOM_GLYPHS = 8;

struct NativeGlyph {
  u8 mask;
  u8 character;
};

// Bits 0..6 are A..G; bit 7 is the decimal point. These are deliberately
// semantic approximations: the LCD's 5x8 CGROM does not have a seven-segment
// font. Prefer digits over letters when the same mask has both readings.
static constexpr NativeGlyph NATIVE_GLYPHS[] = {
  {0x00, ' '}, {0x08, '_'}, {0x40, '-'}, {0x48, '='}, {0x80, '.'},
  {0x3F, '0'}, {0x06, '1'}, {0x5B, '2'}, {0x4F, '3'}, {0x66, '4'},
  {0x6D, '5'}, {0x7D, '6'}, {0x07, '7'}, {0x7F, '8'}, {0x6F, '9'},
  {0x77, 'A'}, {0x7C, 'b'}, {0x39, 'C'}, {0x58, 'c'}, {0x5E, 'd'},
  {0x79, 'E'}, {0x71, 'F'}, {0x76, 'H'}, {0x74, 'h'}, {0x1E, 'J'},
  {0x38, 'L'}, {0x54, 'n'}, {0x5C, 'o'}, {0x73, 'P'}, {0x50, 'r'},
  {0x3E, 'U'}, {0x1C, 'u'}, {0x6E, 'y'},
#if defined(MK61_LCD1602_A00)
  {0x78, 0xCB}, // A00's 203 has a more seven-segment-like t
  {0xC9, 0xD0}, // A00's 208: three horizontal bars and a point
#else
  {0x78, 't'},
#endif
#if defined(MK61_LCD1602_A02)
  {0x31, lcd_charset::CYR_GHE}, {0x37, lcd_charset::CYR_PE},
#endif
  // A00 147 / A02 Э also resemble mask 4F, but 4F is digit 3; A02 Ч
  // resembles 66, but 66 is digit 4. Digits retain precedence.
};

inline bool native_character(u8 mask, u8& character) {
  for(const NativeGlyph& glyph : NATIVE_GLYPHS) {
    if(glyph.mask == mask) {
      character = glyph.character;
      return true;
    }
  }
  return false;
}

inline void custom_rows(u8 mask, u8 rows[8]) {
  for(u8 row = 0; row < 8; ++row) rows[row] = 0;
  if(mask & 0x01U) rows[0] |= 0x0EU; // A: top
  if(mask & 0x02U) { rows[1] |= 0x01U; rows[2] |= 0x01U; } // B
  if(mask & 0x04U) { rows[4] |= 0x01U; rows[5] |= 0x01U;
                     rows[6] |= 0x01U; } // C
  if(mask & 0x08U) rows[7] |= 0x0EU; // D: bottom
  if(mask & 0x10U) { rows[4] |= 0x10U; rows[5] |= 0x10U;
                     rows[6] |= 0x10U; } // E
  if(mask & 0x20U) { rows[1] |= 0x10U; rows[2] |= 0x10U; } // F
  if(mask & 0x40U) rows[3] |= 0x0EU; // G: middle
  if(mask & 0x80U) rows[7] |= 0x01U; // decimal point
}

struct Plan {
  u8 characters[CELLS];
  u8 custom_masks[CUSTOM_GLYPHS];
  u8 custom_count;
  u8 overflow_count;
};

inline Plan plan(const u8 masks[CELLS]) {
  Plan result = {};
  u8 unique[CELLS] = {};
  u8 frequency[CELLS] = {};
  bool selected[CELLS] = {};
  u8 unique_count = 0;

  for(u8 cell = 0; cell < CELLS; ++cell) {
    u8 native = 0;
    if(native_character(masks[cell], native)) continue;
    u8 index = 0;
    while(index < unique_count && unique[index] != masks[cell]) ++index;
    if(index == unique_count) unique[unique_count++] = masks[cell];
    frequency[index]++;
  }

  // If the frame needs more than eight custom glyphs, keep the most repeated
  // masks exact; ties retain their left-to-right order. Remaining cells show
  // '?' instead of silently displaying the wrong segment pattern.
  while(result.custom_count < CUSTOM_GLYPHS &&
        result.custom_count < unique_count) {
    u8 best = CELLS;
    for(u8 index = 0; index < unique_count; ++index) {
      if(!selected[index] &&
         (best == CELLS || frequency[index] > frequency[best])) best = index;
    }
    selected[best] = true;
    result.custom_masks[result.custom_count++] = unique[best];
  }

  for(u8 cell = 0; cell < CELLS; ++cell) {
    u8 character = 0;
    if(native_character(masks[cell], character)) {
      result.characters[cell] = character;
      continue;
    }
    u8 slot = 0;
    while(slot < result.custom_count &&
          result.custom_masks[slot] != masks[cell]) ++slot;
    if(slot < result.custom_count) result.characters[cell] = slot;
    else {
      result.characters[cell] = '?';
      result.overflow_count++;
    }
  }
  return result;
}

} // namespace segment_lcd1602

#endif

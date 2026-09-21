#include "builtin_font.hpp"

#include "config.h"
#include "display_symbols.hpp"
#if MK61_HAS_COMPILED_GRAPHICS || MK61_MARKDOWN_USES_WBMP
  #include "ERM19264_graphics_font.h"
#endif

#include <string.h>

namespace builtin_font {

namespace {

struct Glyph5x8 {
  u16 codepoint;
  u8 rows[8];
};

#if MK61_HAS_COMPILED_GRAPHICS || MK61_MARKDOWN_USES_WBMP
  #define MK61_BUILTIN_FULL_CYRILLIC 1
#else
  #define MK61_BUILTIN_FULL_CYRILLIC 0
#endif

// Character displays already contain most or all of the Russian alphabet in
// CGROM.  Keep only the A00 omissions in firmware; A02 and WS0010 need no
// standard Russian CGRAM copies at all.  Graphics backends still need every
// raster, including lowercase.
#if MK61_BUILTIN_FULL_CYRILLIC || \
    (!defined(MK61_LCD1602_A02) && !defined(MK61_OLED1602_WS0010))
  #define MK61_BUILTIN_HAS_STANDARD_CYRILLIC 1
#else
  #define MK61_BUILTIN_HAS_STANDARD_CYRILLIC 0
#endif

#if MK61_BUILTIN_HAS_STANDARD_CYRILLIC
static constexpr Glyph5x8 CYRILLIC[] = {
#if MK61_BUILTIN_FULL_CYRILLIC
  {0x0410, {0b01110, 0b10001, 0b10001, 0b11111, 0b10001, 0b10001, 0b10001, 0b00000}},
#endif
  {0x0411, {0b11111, 0b10000, 0b10000, 0b11110, 0b10001, 0b10001, 0b11110, 0b00000}},
#if MK61_BUILTIN_FULL_CYRILLIC
  {0x0412, {0b11110, 0b10001, 0b10001, 0b11110, 0b10001, 0b10001, 0b11110, 0b00000}},
#endif
  {0x0413, {0b11111, 0b10000, 0b10000, 0b10000, 0b10000, 0b10000, 0b10000, 0b00000}},
  {0x0414, {0b00110, 0b01010, 0b01010, 0b01010, 0b01010, 0b01010, 0b11111, 0b10001}},
#if MK61_BUILTIN_FULL_CYRILLIC
  {0x0415, {0b11111, 0b10000, 0b10000, 0b11110, 0b10000, 0b10000, 0b11111, 0b00000}},
  {0x0401, {0b01010, 0b00000, 0b11111, 0b10000, 0b11110, 0b10000, 0b11111, 0b00000}},
#endif
  {0x0416, {0b10101, 0b10101, 0b01110, 0b00100, 0b01110, 0b10101, 0b10101, 0b00000}},
#if MK61_BUILTIN_FULL_CYRILLIC
  {0x0417, {0b11110, 0b00001, 0b00001, 0b01110, 0b00001, 0b00001, 0b11110, 0b00000}},
#endif
  {0x0418, {0b10001, 0b10001, 0b10001, 0b10011, 0b10101, 0b11001, 0b10001, 0b00000}},
  {0x0419, {0b01010, 0b00100, 0b10001, 0b10011, 0b10101, 0b11001, 0b10001, 0b00000}},
#if MK61_BUILTIN_FULL_CYRILLIC
  {0x041A, {0b10001, 0b10010, 0b10100, 0b11000, 0b10100, 0b10010, 0b10001, 0b00000}},
#endif
  {0x041B, {0b00111, 0b01001, 0b01001, 0b01001, 0b01001, 0b01001, 0b10001, 0b00000}},
#if MK61_BUILTIN_FULL_CYRILLIC
  {0x041C, {0b10001, 0b11011, 0b10101, 0b10101, 0b10001, 0b10001, 0b10001, 0b00000}},
  {0x041D, {0b10001, 0b10001, 0b10001, 0b11111, 0b10001, 0b10001, 0b10001, 0b00000}},
  {0x041E, {0b01110, 0b10001, 0b10001, 0b10001, 0b10001, 0b10001, 0b01110, 0b00000}},
#endif
  {0x041F, {0b11111, 0b10001, 0b10001, 0b10001, 0b10001, 0b10001, 0b10001, 0b00000}},
#if MK61_BUILTIN_FULL_CYRILLIC
  {0x0420, {0b11110, 0b10001, 0b10001, 0b11110, 0b10000, 0b10000, 0b10000, 0b00000}},
  {0x0421, {0b01111, 0b10000, 0b10000, 0b10000, 0b10000, 0b10000, 0b01111, 0b00000}},
  {0x0422, {0b11111, 0b00100, 0b00100, 0b00100, 0b00100, 0b00100, 0b00100, 0b00000}},
#endif
  {0x0423, {0b10001, 0b10001, 0b10001, 0b01111, 0b00001, 0b00001, 0b11110, 0b00000}},
  {0x0424, {0b00100, 0b01110, 0b10101, 0b10101, 0b10101, 0b01110, 0b00100, 0b00000}},
#if MK61_BUILTIN_FULL_CYRILLIC
  {0x0425, {0b10001, 0b10001, 0b01010, 0b00100, 0b01010, 0b10001, 0b10001, 0b00000}},
#endif
  {0x0426, {0b10010, 0b10010, 0b10010, 0b10010, 0b10010, 0b11111, 0b00001, 0b00000}},
  {0x0427, {0b10001, 0b10001, 0b10001, 0b01111, 0b00001, 0b00001, 0b00001, 0b00000}},
  {0x0428, {0b10101, 0b10101, 0b10101, 0b10101, 0b10101, 0b10101, 0b11111, 0b00000}},
  {0x0429, {0b10101, 0b10101, 0b10101, 0b10101, 0b10101, 0b11111, 0b00001, 0b00000}},
  {0x042A, {0b11000, 0b01000, 0b01000, 0b01110, 0b01001, 0b01001, 0b01110, 0b00000}},
  {0x042B, {0b10001, 0b10001, 0b10001, 0b11101, 0b10011, 0b10011, 0b11101, 0b00000}},
#if MK61_BUILTIN_FULL_CYRILLIC
  {0x042C, {0b10000, 0b10000, 0b10000, 0b11110, 0b10001, 0b10001, 0b11110, 0b00000}},
#endif
  {0x042D, {0b11110, 0b00001, 0b00001, 0b01111, 0b00001, 0b00001, 0b11110, 0b00000}},
  {0x042E, {0b10010, 0b10101, 0b10101, 0b11101, 0b10101, 0b10101, 0b10010, 0b00000}},
  {0x042F, {0b01111, 0b10001, 0b10001, 0b01111, 0b00101, 0b01001, 0b10001, 0b00000}},
#if MK61_BUILTIN_FULL_CYRILLIC
  {0x0430, {0b00000, 0b01110, 0b00001, 0b01111, 0b10001, 0b10011, 0b01101, 0b00000}},
  {0x0431, {0b00111, 0b01000, 0b10000, 0b11110, 0b10001, 0b10001, 0b01110, 0b00000}},
  {0x0432, {0b00000, 0b11110, 0b10001, 0b11110, 0b10001, 0b10001, 0b11110, 0b00000}},
  {0x0433, {0b00000, 0b11111, 0b10000, 0b10000, 0b10000, 0b10000, 0b10000, 0b00000}},
  {0x0434, {0b00000, 0b00110, 0b01010, 0b01010, 0b01010, 0b11111, 0b10001, 0b00000}},
  {0x0435, {0b00000, 0b01110, 0b10001, 0b11111, 0b10000, 0b10001, 0b01110, 0b00000}},
  {0x0451, {0b01010, 0b00000, 0b01110, 0b10001, 0b11111, 0b10000, 0b01110, 0b00000}},
  {0x0436, {0b00000, 0b10101, 0b10101, 0b01110, 0b01110, 0b10101, 0b10101, 0b00000}},
  {0x0437, {0b00000, 0b11110, 0b00001, 0b00110, 0b00001, 0b00001, 0b11110, 0b00000}},
  {0x0438, {0b00000, 0b10001, 0b10011, 0b10101, 0b11001, 0b10001, 0b10001, 0b00000}},
  {0x0439, {0b01010, 0b00100, 0b10001, 0b10011, 0b10101, 0b11001, 0b10001, 0b00000}},
  {0x043A, {0b00000, 0b10001, 0b10010, 0b10100, 0b11000, 0b10100, 0b10010, 0b00000}},
  {0x043B, {0b00000, 0b00111, 0b01001, 0b01001, 0b01001, 0b01001, 0b10001, 0b00000}},
  {0x043C, {0b00000, 0b10001, 0b11011, 0b10101, 0b10101, 0b10001, 0b10001, 0b00000}},
  {0x043D, {0b00000, 0b10001, 0b10001, 0b11111, 0b10001, 0b10001, 0b10001, 0b00000}},
  {0x043E, {0b00000, 0b01110, 0b10001, 0b10001, 0b10001, 0b10001, 0b01110, 0b00000}},
  {0x043F, {0b00000, 0b11111, 0b10001, 0b10001, 0b10001, 0b10001, 0b10001, 0b00000}},
  {0x0440, {0b00000, 0b11110, 0b10001, 0b10001, 0b11110, 0b10000, 0b10000, 0b10000}},
  {0x0441, {0b00000, 0b01111, 0b10000, 0b10000, 0b10000, 0b10000, 0b01111, 0b00000}},
  {0x0442, {0b00000, 0b11111, 0b00100, 0b00100, 0b00100, 0b00100, 0b00100, 0b00000}},
  {0x0443, {0b00000, 0b10001, 0b10001, 0b01111, 0b00001, 0b00001, 0b11110, 0b00000}},
  {0x0444, {0b00100, 0b01110, 0b10101, 0b10101, 0b10101, 0b01110, 0b00100, 0b00000}},
  {0x0445, {0b00000, 0b10001, 0b01010, 0b00100, 0b01010, 0b10001, 0b10001, 0b00000}},
  {0x0446, {0b00000, 0b10010, 0b10010, 0b10010, 0b10010, 0b11111, 0b00001, 0b00000}},
  {0x0447, {0b00000, 0b10001, 0b10001, 0b01111, 0b00001, 0b00001, 0b00001, 0b00000}},
  {0x0448, {0b00000, 0b10101, 0b10101, 0b10101, 0b10101, 0b10101, 0b11111, 0b00000}},
  {0x0449, {0b00000, 0b10101, 0b10101, 0b10101, 0b10101, 0b11111, 0b00001, 0b00000}},
  {0x044A, {0b00000, 0b11000, 0b01000, 0b01110, 0b01001, 0b01001, 0b01110, 0b00000}},
  {0x044B, {0b00000, 0b10001, 0b10001, 0b11101, 0b10011, 0b10011, 0b11101, 0b00000}},
  {0x044C, {0b00000, 0b10000, 0b10000, 0b11110, 0b10001, 0b10001, 0b11110, 0b00000}},
  {0x044D, {0b00000, 0b11110, 0b00001, 0b01111, 0b00001, 0b00001, 0b11110, 0b00000}},
  {0x044E, {0b00000, 0b10010, 0b10101, 0b10101, 0b11101, 0b10101, 0b10010, 0b00000}},
  {0x044F, {0b00000, 0b01111, 0b10001, 0b10001, 0b01111, 0b00101, 0b01001, 0b00000}}
#endif
};

#if MK61_BUILTIN_FULL_CYRILLIC
static constexpr usize STANDARD_CYRILLIC_COUNT =
    sizeof(CYRILLIC) / sizeof(CYRILLIC[0]);
static_assert(STANDARD_CYRILLIC_COUNT == 66,
              "packed 5x8 Cyrillic index contract");
static_assert(CYRILLIC[6].codepoint == 0x0401 &&
              CYRILLIC[39].codepoint == 0x0451,
              "packed 5x8 Cyrillic order");

struct PackedCyrillic5x8 {
  u8 bytes[STANDARD_CYRILLIC_COUNT * 5] = {};

  constexpr PackedCyrillic5x8() {
    for(usize index = 0; index < STANDARD_CYRILLIC_COUNT; ++index) {
      for(u8 y = 0; y < 8; ++y) {
        for(u8 x = 0; x < 5; ++x) {
          if((CYRILLIC[index].rows[y] & ((u8) 1U << (4U - x))) == 0) {
            continue;
          }
          const usize bit = (usize) y * 5U + x;
          bytes[index * 5U + bit / 8U] |= (u8) (0x80U >> (bit & 7U));
        }
      }
    }
  }
};

static constexpr PackedCyrillic5x8 PACKED_CYRILLIC_5X8;

static i16 standardCyrillicIndex(u16 codepoint) {
  if(codepoint >= 0x0410 && codepoint <= 0x0415) {
    return (i16) (codepoint - 0x0410);
  }
  if(codepoint == 0x0401) return 6;
  if(codepoint >= 0x0416 && codepoint <= 0x042F) {
    return (i16) (codepoint - 0x0410 + 1U);
  }
  if(codepoint >= 0x0430 && codepoint <= 0x0435) {
    return (i16) (33U + codepoint - 0x0430);
  }
  if(codepoint == 0x0451) return 39;
  if(codepoint >= 0x0436 && codepoint <= 0x044F) {
    return (i16) (34U + codepoint - 0x0430);
  }
  return -1;
}

static const u8* standardCyrillicBitmap(u16 codepoint) {
  const i16 index = standardCyrillicIndex(codepoint);
  return index >= 0
      ? &PACKED_CYRILLIC_5X8.bytes[(usize) index * 5U] : NULL;
}
#endif
#endif

// The WS0010 FT=10 ROM contains the complete Russian alphabet, but not the
// Ukrainian/Belarusian additions below.  They live in Flash and can be leased
// into the same eight CGRAM cells as any other non-ROM Unicode glyph.  WS0010
// and graphics preserve both cases; A00/A02 uppercase their two-line output,
// so their lowercase copies would be unreachable.
static const Glyph5x8 CYRILLIC_SUPPLEMENTAL[] = {
  {0x0404, {0b01110, 0b10000, 0b10000, 0b11110, 0b10000, 0b10000, 0b01110, 0b00000}}, // Є
  {0x0406, {0b01110, 0b00100, 0b00100, 0b00100, 0b00100, 0b00100, 0b01110, 0b00000}}, // І
  {0x0407, {0b01010, 0b00000, 0b01110, 0b00100, 0b00100, 0b00100, 0b01110, 0b00000}}, // Ї
  {0x0490, {0b00001, 0b11111, 0b10000, 0b10000, 0b10000, 0b10000, 0b10000, 0b00000}}, // Ґ
  {0x040E, {0b01010, 0b00100, 0b10001, 0b10001, 0b01111, 0b00001, 0b11110, 0b00000}}, // Ў
#if MK61_BUILTIN_FULL_CYRILLIC || defined(MK61_OLED1602_WS0010)
  {0x0454, {0b00000, 0b01110, 0b10000, 0b11110, 0b10000, 0b10000, 0b01110, 0b00000}}, // є
  {0x0456, {0b00100, 0b00000, 0b01100, 0b00100, 0b00100, 0b00100, 0b01110, 0b00000}}, // і
  {0x0457, {0b01010, 0b00000, 0b01100, 0b00100, 0b00100, 0b00100, 0b01110, 0b00000}}, // ї
  {0x0491, {0b00001, 0b01111, 0b01000, 0b01000, 0b01000, 0b01000, 0b01000, 0b00000}}, // ґ
  {0x045E, {0b01010, 0b00100, 0b10001, 0b10001, 0b01111, 0b00001, 0b11110, 0b00000}}, // ў
#endif
};

// M8 text is decoded to Unicode before reaching the display grid. The
// original UC1609 font has several of these drawings at unrelated C0 byte
// positions, so indexing that font with an M8 byte would display the wrong
// symbol. Keep the semantic Unicode mapping here for every private M8 sign.
// Existing shapes are transcribed from UC_Font_One; the missing comparisons,
// multiplication, superscript minus and return arrow have dedicated rasters.
static const Glyph5x8 SPECIAL_5X8[] = {
  {0x2190, {0b00010, 0b00100, 0b01000, 0b11111, 0b01000, 0b00100, 0b00010, 0}}, // ←
  {0x2192, {0b01000, 0b00100, 0b00010, 0b11111, 0b00010, 0b00100, 0b01000, 0}}, // →
  {0x2191, {0b00100, 0b01110, 0b10101, 0b00100, 0b00100, 0b00100, 0b00100, 0}}, // ↑
  {0x2193, {0, 0b00100, 0b00100, 0b00100, 0b10101, 0b01110, 0b00100, 0}}, // ↓
  {0x03C0, {0, 0b11111, 0b01010, 0b01010, 0b01010, 0b01010, 0b10011, 0}}, // π
  {0x221A, {0, 0b00111, 0b00100, 0b00100, 0b00100, 0b10100, 0b01000, 0}}, // √
  {0x21BB, {0, 0b11110, 0b10010, 0b10010, 0b10010, 0b10010, 0b11110, 0}}, // ↻
  {0x2260, {0b00001, 0b00010, 0b11111, 0b00100, 0b11111, 0b01000, 0b10000, 0}}, // ≠
  {0x2264, {0, 0b00010, 0b00100, 0b01000, 0b00100, 0b00010, 0b11111, 0}}, // ≤
  {0x2265, {0, 0b01000, 0b00100, 0b00010, 0b00100, 0b01000, 0b11111, 0}}, // ≥
  {0x00D7, {0, 0b10001, 0b01010, 0b00100, 0b01010, 0b10001, 0, 0}}, // ×
  {0x00F7, {0, 0, 0b00100, 0, 0b11111, 0, 0b00100, 0}}, // ÷
  {0x00B2, {0b11100, 0b00100, 0b01100, 0b10000, 0b11100, 0, 0, 0}}, // ²
  {0x02B8, {0b10100, 0b10100, 0b01100, 0b00100, 0b11000, 0, 0, 0}}, // ʸ
  {0x02E3, {0b10100, 0b10100, 0b01000, 0b10100, 0b10100, 0, 0, 0}}, // ˣ
  {0x22BB, {0b01110, 0b10101, 0b10101, 0b11111, 0b10101, 0b10101, 0b01110, 0}}, // ⊻
  {0x207B, {0, 0b01110, 0, 0, 0, 0, 0, 0}}, // ⁻
  {0x21B5, {0b00010, 0b00010, 0b00010, 0b01010, 0b11110, 0b01000, 0, 0}}, // ↵
  {display_symbol::uc1609::GE, {0b00100, 0b00010, 0b00001, 0b00010, 0b00100, 0b01001, 0b00010, 0b00100}}
};

static u16 aliasedCodepoint(u16 codepoint) {
#if MK61_HAS_COMPILED_GRAPHICS || MK61_MARKDOWN_USES_WBMP
  return display_symbol::uc1609::builtinCodepoint(codepoint);
#else
  (void) codepoint;
#endif
  return codepoint;
}

static const u8* specialRows5x8(u16 codepoint) {
  for(usize i = 0; i < sizeof(SPECIAL_5X8) / sizeof(SPECIAL_5X8[0]); i++) {
    if(SPECIAL_5X8[i].codepoint == codepoint) return SPECIAL_5X8[i].rows;
  }
  return NULL;
}

#if MK61_HAS_COMPILED_GRAPHICS || MK61_MARKDOWN_USES_WBMP
static void setPixel(Raster& raster, u8 x, u8 y) {
  const usize stride = (raster.width + 7) / 8;
  raster.data[(usize) y * stride + x / 8] |= (u8) (0x80 >> (x & 7));
}

static bool decodeRows5x8(const u8* rows, Raster& out) {
  if(rows == NULL) return false;
  out.width = 5;
  out.height = 8;
  memset(out.data, 0, sizeof(out.data));
  for(u8 y = 0; y < out.height; y++) {
    for(u8 x = 0; x < out.width; x++) {
      if((rows[y] & ((u8) 1 << (4 - x))) != 0) setPixel(out, x, y);
    }
  }
  return true;
}

static bool decodeTightBitmap(const u8* bitmap, u8 width, u8 height,
                              Raster& out) {
  if(bitmap == NULL) return false;
  out.width = width;
  out.height = height;
  memset(out.data, 0, sizeof(out.data));
  for(u8 y = 0; y < height; ++y) {
    for(u8 x = 0; x < width; ++x) {
      const usize bit = (usize) y * width + x;
      if((bitmap[bit / 8U] & (0x80U >> (bit & 7U))) != 0) {
        setPixel(out, x, y);
      }
    }
  }
  return true;
}
#endif

} // анонимное пространство имён

const u8* rows5x8(u16 codepoint) {
  if(const u8* rows = specialRows5x8(codepoint)) return rows;
  codepoint = aliasedCodepoint(codepoint);
#if MK61_BUILTIN_HAS_STANDARD_CYRILLIC && !MK61_BUILTIN_FULL_CYRILLIC
  for(usize i = 0; i < sizeof(CYRILLIC) / sizeof(CYRILLIC[0]); i++) {
    if(CYRILLIC[i].codepoint == codepoint) return CYRILLIC[i].rows;
  }
#endif
  for(usize i = 0;
      i < sizeof(CYRILLIC_SUPPLEMENTAL) / sizeof(CYRILLIC_SUPPLEMENTAL[0]);
      i++) {
    if(CYRILLIC_SUPPLEMENTAL[i].codepoint == codepoint) {
      return CYRILLIC_SUPPLEMENTAL[i].rows;
    }
  }
  return NULL;
}

FaceId closest(u8 width, u8 height) {
  const u8 width_3x5 = width > 3 ? (u8) (width - 3) : (u8) (3 - width);
  const u8 height_3x5 = height > 5 ? (u8) (height - 5) : (u8) (5 - height);
  const u8 width_5x8 = width > 5 ? (u8) (width - 5) : (u8) (5 - width);
  const u8 height_5x8 = height > 8 ? (u8) (height - 8) : (u8) (8 - height);
  return width_3x5 + height_3x5 <= width_5x8 + height_5x8
    ? FaceId::FONT_3X5
    : FaceId::FONT_5X8;
}

bool decode(FaceId face, u16 codepoint, Raster& out) {
#if !MK61_HAS_COMPILED_GRAPHICS && !MK61_MARKDOWN_USES_WBMP
  (void) face;
  (void) codepoint;
  (void) out;
  return false;
#else
  memset(out.data, 0, sizeof(out.data));
  if(decodeRows5x8(specialRows5x8(codepoint), out)) return true;
  codepoint = aliasedCodepoint(codepoint);

  if(face == FaceId::FONT_3X5) {
    return decodeTightBitmap(font3x5Bitmap(codepoint), 3, 5, out);
  }

  out.width = 5;
  out.height = 8;
  if(const u8* rows = rows5x8(codepoint)) {
    return decodeRows5x8(rows, out);
  }
#if MK61_BUILTIN_FULL_CYRILLIC
  if(decodeTightBitmap(standardCyrillicBitmap(codepoint), 5, 8, out)) {
    return true;
  }
#endif

  if(codepoint > 0x7E) return false;
  const unsigned char* columns = &UC_Font_One[(usize) codepoint * 5];
  for(u8 x = 0; x < out.width; x++) {
    for(u8 y = 0; y < out.height; y++) {
      if((columns[x] & ((u8) 1 << y)) != 0) setPixel(out, x, y);
    }
  }
  return true;
#endif
}

} // пространство имён builtin_font

#undef MK61_BUILTIN_HAS_STANDARD_CYRILLIC
#undef MK61_BUILTIN_FULL_CYRILLIC

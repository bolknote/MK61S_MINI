#ifndef LCD_CHARSET_HPP
#define LCD_CHARSET_HPP

#include "config.h"
#include "rust_types.h"

namespace lcd_charset {

#if defined(MK61_LCD1602_A02)
// HD44780UA02 / Wokwi A02 CGROM codes for Cyrillic glyphs that do not
// have an identical ASCII glyph in the base ROM.
static constexpr u8 CYR_BE       = 0x80; // Б
static constexpr u8 CYR_DE       = 0x81; // Д
static constexpr u8 CYR_ZHE      = 0x82; // Ж
static constexpr u8 CYR_ZE       = 0x83; // З
static constexpr u8 CYR_I        = 0x84; // И
static constexpr u8 CYR_SHORT_I  = 0x85; // Й
static constexpr u8 CYR_EL       = 0x86; // Л
static constexpr u8 CYR_PE       = 0x87; // П
static constexpr u8 CYR_U        = 0x88; // У
static constexpr u8 CYR_TSE      = 0x89; // Ц
static constexpr u8 CYR_CHE      = 0x8A; // Ч
static constexpr u8 CYR_SHA      = 0x8B; // Ш
static constexpr u8 CYR_SHCHA    = 0x8C; // Щ
static constexpr u8 CYR_HARD     = 0x8D; // Ъ
static constexpr u8 CYR_YERU     = 0x8E; // Ы
static constexpr u8 CYR_E        = 0x8F; // Э
static constexpr u8 CYR_GHE      = 0x92; // Г
static constexpr u8 CYR_YU       = 0xAC; // Ю
static constexpr u8 CYR_YA       = 0xAD; // Я
static constexpr u8 CYR_IO       = 0xCB; // Ё
static constexpr u8 CYR_EF       = 0xD8; // Ф
#endif

} // namespace lcd_charset

#endif

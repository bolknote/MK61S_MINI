#ifndef LCD_RU_ENCODER
#define LCD_RU_ENCODER

#include "lcd_gui.hpp"
#include "lcd_charset.hpp"
#include "builtin_font.hpp"
#include "cgram_window_plan.hpp"
#if defined(MK61_OLED1602_WS0010)
  #include "ws0010_charset.hpp"
#endif

namespace lcd_ru {

static constexpr u8 LCD_WIDTH = lcd_display::COLS;
static constexpr u8 CUSTOM_GLYPHS = 8;

using font_map_t = cgram_window_plan::Plan;

inline u16 uppercase(u16 codepoint) {
  if(codepoint >= 0x0430 && codepoint <= 0x044F) return codepoint - 0x20;
  if(codepoint == 0x0451) return 0x0401;
  return codepoint;
}

inline u16 display_codepoint(u16 codepoint) {
#if defined(MK61_OLED1602_WS0010) || defined(MK61_DISPLAY_UC1609)
  // These backends have native lowercase glyphs. A00/A02 retain their
  // long-standing uppercase UI policy.
  return codepoint;
#else
  return uppercase(codepoint);
#endif
}

inline u16 read_utf8(const char*& text) {
  const u8 first = (u8) *text++;
  if(first < 0x80) return first;

  if((first & 0xE0) == 0xC0) {
    const u8 second = (u8) *text;
    if(second != 0) text++;
    return (u16) (((first & 0x1F) << 6) | (second & 0x3F));
  }

  if((first & 0xF0) == 0xE0) {
    const u8 second = (u8) *text;
    if(second != 0) text++;
    const u8 third = (u8) *text;
    if(third != 0) text++;
    return (u16) (((first & 0x0F) << 12) | ((second & 0x3F) << 6) | (third & 0x3F));
  }

  return '?';
}

inline bool a02_rom_char(u16 codepoint, u8& out) {
#if defined(MK61_LCD1602_A02)
  codepoint = uppercase(codepoint);
  if(codepoint < 0x80) {
    out = (u8) codepoint;
    return true;
  }

  switch(codepoint) {
    case 0x0410: out = 'A'; return true; // А
    case 0x0411: out = lcd_charset::CYR_BE; return true; // Б
    case 0x0412: out = 'B'; return true; // В
    case 0x0413: out = lcd_charset::CYR_GHE; return true; // Г
    case 0x0414: out = lcd_charset::CYR_DE; return true; // Д
    case 0x0415: out = 'E'; return true; // Е
    case 0x0401: out = lcd_charset::CYR_IO; return true; // Ё
    case 0x0416: out = lcd_charset::CYR_ZHE; return true; // Ж
    case 0x0417: out = lcd_charset::CYR_ZE; return true; // З
    case 0x0418: out = lcd_charset::CYR_I; return true; // И
    case 0x0419: out = lcd_charset::CYR_SHORT_I; return true; // Й
    case 0x041A: out = 'K'; return true; // К
    case 0x041B: out = lcd_charset::CYR_EL; return true; // Л
    case 0x041C: out = 'M'; return true; // М
    case 0x041D: out = 'H'; return true; // Н
    case 0x041E: out = 'O'; return true; // О
    case 0x041F: out = lcd_charset::CYR_PE; return true; // П
    case 0x0420: out = 'P'; return true; // Р
    case 0x0421: out = 'C'; return true; // С
    case 0x0422: out = 'T'; return true; // Т
    case 0x0423: out = lcd_charset::CYR_U; return true; // У
    case 0x0424: out = lcd_charset::CYR_EF; return true; // Ф
    case 0x0425: out = 'X'; return true; // Х
    case 0x0426: out = lcd_charset::CYR_TSE; return true; // Ц
    case 0x0427: out = lcd_charset::CYR_CHE; return true; // Ч
    case 0x0428: out = lcd_charset::CYR_SHA; return true; // Ш
    case 0x0429: out = lcd_charset::CYR_SHCHA; return true; // Щ
    case 0x042A: out = lcd_charset::CYR_HARD; return true; // Ъ
    case 0x042B: out = lcd_charset::CYR_YERU; return true; // Ы
    case 0x042C: out = 'b'; return true; // Ь: ближайшая встроенная замена
    case 0x042D: out = lcd_charset::CYR_E; return true; // Э
    case 0x042E: out = lcd_charset::CYR_YU; return true; // Ю
    case 0x042F: out = lcd_charset::CYR_YA; return true; // Я
    default: return false;
  }
#else
  (void) codepoint;
  (void) out;
  return false;
#endif
}

inline bool a00_rom_char(u16 codepoint, u8& out) {
  codepoint = uppercase(codepoint);
  if(codepoint < 0x80) {
    out = (u8) codepoint;
    return true;
  }

  switch(codepoint) {
    case 0x0410: out = 'A'; return true; // А
    case 0x0412: out = 'B'; return true; // В
    case 0x0415: out = 'E'; return true; // Е
    case 0x0401: out = 'E'; return true; // Ё -> Е для японской A00
    case 0x0417: out = '3'; return true; // З
    case 0x041A: out = 'K'; return true; // К
    case 0x041C: out = 'M'; return true; // М
    case 0x041D: out = 'H'; return true; // Н
    case 0x041E: out = 'O'; return true; // О
    case 0x0420: out = 'P'; return true; // Р
    case 0x0421: out = 'C'; return true; // С
    case 0x0422: out = 'T'; return true; // Т
    case 0x0425: out = 'X'; return true; // Х
    case 0x042C: out = 'b'; return true; // Ь
    default: return false;
  }
}

inline bool rom_char(u16 codepoint, u8& out) {
#if defined(MK61_DISPLAY_UC1609)
  if(codepoint < 0x80) {
    out = (u8) codepoint;
    return true;
  }
  (void) out;
  return false;
#else
  #if defined(MK61_OLED1602_WS0010)
    return ws0010_charset::unicodeToByte(codepoint, out);
  #else
    if(a02_rom_char(codepoint, out)) return true;
    return a00_rom_char(codepoint, out);
  #endif
#endif
}

inline bool fixed_cgram_char(u16 codepoint, u8& slot) {
#if defined(MK61_OLED1602_WS0010)
  switch(display_codepoint(codepoint)) {
    case 0x2265: slot = ws0010_charset::cgram::GREATER_OR_EQUAL; return true;
    case 0x02B8: slot = ws0010_charset::cgram::POWER_Y; return true;
    case 0x22BB: slot = ws0010_charset::cgram::XOR; return true;
    case 0x2260: slot = ws0010_charset::cgram::NOT_EQUAL; return true;
    case 0x221A: slot = ws0010_charset::cgram::SQUARE_ROOT; return true;
    case 0x21BB: slot = ws0010_charset::cgram::CYCLE_ARROW; return true;
    case 0x02E3: slot = ws0010_charset::cgram::POWER_X; return true;
    case 0x00B2: slot = ws0010_charset::cgram::POWER_2; return true;
    default: return false;
  }
#else
  (void) codepoint;
  (void) slot;
  return false;
#endif
}

inline bool fallback_char(u16 codepoint, u8& out) {
  codepoint = display_codepoint(codepoint);
  if(codepoint == 0x0427) {
    out = '4'; // Ч: допустимо, только когда уже используются все 8 пользовательских символов.
    return true;
  }
  if(codepoint == 0x0423) {
    out = 'Y'; // У: только когда текущему экрану нужно более 8 пользовательских символов.
    return true;
  }
  return false;
}

inline const u8* glyph_for(u16 codepoint) {
#if !defined(MK61_DISPLAY_UC1609) && !defined(MK61_OLED1602_WS0010)
  codepoint = uppercase(codepoint);
#endif
  if(const u8* glyph = builtin_font::rows5x8(codepoint)) return glyph;
#if defined(MK61_DISPLAY_UC1609)
  const u16 upper = uppercase(codepoint);
  if(upper != codepoint) return builtin_font::rows5x8(upper);
#endif
  return NULL;
}

inline i8 slot_for(const font_map_t& map, u16 codepoint) {
  codepoint = display_codepoint(codepoint);
  return cgram_window_plan::slotFor(map, codepoint);
}

inline void add_custom(font_map_t& map, u16 codepoint) {
  u8 rom;
  codepoint = display_codepoint(codepoint);
  u8 fixed_slot = 0;
  if(fixed_cgram_char(codepoint, fixed_slot)) {
    cgram_window_plan::reserve(map, fixed_slot);
    return;
  }
  if(rom_char(codepoint, rom)) return;
  if(glyph_for(codepoint) == NULL) return;
  if(slot_for(map, codepoint) >= 0) return;
  (void) cgram_window_plan::add(map, codepoint);
}

inline void scan_text(font_map_t& map, const char* text, u8 width) {
  for(u8 used = 0; *text != 0 && used < width; used++) {
    add_custom(map, read_utf8(text));
  }
}

inline void load_custom_font(const font_map_t& map) {
#if defined(MK61_DISPLAY_UC1609)
  (void) map;
#else
  if(main_lcd().graphicsMode()) return;
#if defined(MK61_OLED1602_WS0010)
  const class_LCD_fonts default_fonts;
  for(u8 slot = 0; slot < CUSTOM_GLYPHS; slot++) {
    if((map.reserved_mask & ((u8) 1u << slot)) != 0) {
      default_fonts.loadWs0010Slot(slot);
    }
  }
#endif
  for(u8 i = 0; i < map.count; i++) {
    main_lcd().createChar(map.slots[i],
                          (uint8_t*) glyph_for(map.codepoints[i]));
  }
#endif
}

inline void restore_default_font(void) {
#if defined(MK61_DISPLAY_UC1609)
  main_lcd().clearCustomChars();
#else
  if(main_lcd().graphicsMode()) {
    main_lcd().clearCustomChars();
    return;
  }
  const class_LCD_fonts lcd_fonts;
  lcd_fonts.load();
#endif
}

inline void write_text(const font_map_t& map, const char* text, u8 width) {
#if defined(MK61_DISPLAY_UC1609)
  (void) map;
#endif
  u8 used = 0;
  while(*text != 0 && used < width) {
    const u16 raw_codepoint = read_utf8(text);
#if defined(MK61_DISPLAY_UC1609)
    main_lcd().writeCodepoint(raw_codepoint);
#else
    if(main_lcd().graphicsMode()) {
      main_lcd().writeCodepoint(raw_codepoint);
    } else {
      const u16 codepoint = display_codepoint(raw_codepoint);
      u8 out;
      if(rom_char(codepoint, out)) {
        main_lcd().write(out);
      } else {
        const i8 slot = slot_for(map, codepoint);
        if(slot >= 0) {
          main_lcd().write((u8) slot);
        } else if(fallback_char(codepoint, out)) {
          main_lcd().write(out);
        } else {
          main_lcd().write((u8) '?');
        }
      }
    }
#endif
    used++;
  }

  while(used++ < width) main_lcd().write((u8) ' ');
}

inline void print_at(u8 x, u8 y, const char* text, u8 width = LCD_WIDTH) {
  MK61DisplayUpdate update(main_lcd());
  font_map_t map = {};
  scan_text(map, text, width);
  load_custom_font(map);
  main_lcd().setCursor(x, y);
  write_text(map, text, width);
}

inline void print_window(const char* const* lines, u8 count) {
  MK61DisplayUpdate update(main_lcd());
  if(count > main_lcd().rows()) count = main_lcd().rows();
  font_map_t map = {};
  for(u8 row = 0; row < count; row++) {
    scan_text(map, lines[row], LCD_WIDTH);
  }
  load_custom_font(map);

  for(u8 row = 0; row < count; row++) {
    main_lcd().setCursor(0, row);
    write_text(map, lines[row], LCD_WIDTH);
  }
}

inline void print_lines(const char* text0, const char* text1) {
  const char* lines[] = {text0, text1};
  print_window(lines, 2);
}

inline void print_menu_window(char mark0, const char* text0, char mark1, const char* text1) {
  MK61DisplayUpdate update(main_lcd());
  font_map_t map = {};
  scan_text(map, text0, LCD_WIDTH - 1);
  scan_text(map, text1, LCD_WIDTH - 1);
  load_custom_font(map);

  main_lcd().setCursor(0, 0);
  main_lcd().write((u8) mark0);
  write_text(map, text0, LCD_WIDTH - 1);

  main_lcd().setCursor(0, 1);
  main_lcd().write((u8) mark1);
  write_text(map, text1, LCD_WIDTH - 1);
}

inline void print_menu_line(u8 y, char mark, const char* text) {
  MK61DisplayUpdate update(main_lcd());
  font_map_t map = {};
  scan_text(map, text, LCD_WIDTH - 1);
  load_custom_font(map);

  main_lcd().setCursor(0, y);
  main_lcd().write((u8) mark);
  write_text(map, text, LCD_WIDTH - 1);
}

} // пространство имён lcd_ru

#endif

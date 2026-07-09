#ifndef LCD_RU_ENCODER
#define LCD_RU_ENCODER

#include "lcd_gui.hpp"
#include "lcd_charset.hpp"
#if defined(MK61_DISPLAY_UC1609)
  #include "ERM19264_graphics_font.h"
#endif

namespace lcd_ru {

static constexpr u8 LCD_WIDTH = lcd_display::COLS;
static constexpr u8 CUSTOM_GLYPHS = 8;

struct glyph_t {
  u16 codepoint;
  u8  rows[8];
};

struct font_map_t {
  u16 codepoints[CUSTOM_GLYPHS];
  u8  count;
  bool overflow;
};

static const glyph_t CYRILLIC_GLYPHS[] = {
  {0x0410, {0b01110, 0b10001, 0b10001, 0b11111, 0b10001, 0b10001, 0b10001, 0b00000}}, // А
  {0x0411, {0b11111, 0b10000, 0b10000, 0b11110, 0b10001, 0b10001, 0b11110, 0b00000}}, // Б
  {0x0412, {0b11110, 0b10001, 0b10001, 0b11110, 0b10001, 0b10001, 0b11110, 0b00000}}, // В
  {0x0413, {0b11111, 0b10000, 0b10000, 0b10000, 0b10000, 0b10000, 0b10000, 0b00000}}, // Г
  {0x0414, {0b00110, 0b01010, 0b01010, 0b01010, 0b01010, 0b01010, 0b11111, 0b10001}}, // Д
  {0x0415, {0b11111, 0b10000, 0b10000, 0b11110, 0b10000, 0b10000, 0b11111, 0b00000}}, // Е
  {0x0401, {0b01010, 0b00000, 0b11111, 0b10000, 0b11110, 0b10000, 0b11111, 0b00000}}, // Ё
  {0x0416, {0b10101, 0b10101, 0b01110, 0b00100, 0b01110, 0b10101, 0b10101, 0b00000}}, // Ж
  {0x0417, {0b11110, 0b00001, 0b00001, 0b01110, 0b00001, 0b00001, 0b11110, 0b00000}}, // З
  {0x0418, {0b10001, 0b10001, 0b10001, 0b10011, 0b10101, 0b11001, 0b10001, 0b00000}}, // И
  {0x0419, {0b01010, 0b00100, 0b10001, 0b10011, 0b10101, 0b11001, 0b10001, 0b00000}}, // Й
  {0x041A, {0b10001, 0b10010, 0b10100, 0b11000, 0b10100, 0b10010, 0b10001, 0b00000}}, // К
  {0x041B, {0b00111, 0b01001, 0b01001, 0b01001, 0b01001, 0b01001, 0b10001, 0b00000}}, // Л
  {0x041C, {0b10001, 0b11011, 0b10101, 0b10101, 0b10001, 0b10001, 0b10001, 0b00000}}, // М
  {0x041D, {0b10001, 0b10001, 0b10001, 0b11111, 0b10001, 0b10001, 0b10001, 0b00000}}, // Н
  {0x041E, {0b01110, 0b10001, 0b10001, 0b10001, 0b10001, 0b10001, 0b01110, 0b00000}}, // О
  {0x041F, {0b11111, 0b10001, 0b10001, 0b10001, 0b10001, 0b10001, 0b10001, 0b00000}}, // П
  {0x0420, {0b11110, 0b10001, 0b10001, 0b11110, 0b10000, 0b10000, 0b10000, 0b00000}}, // Р
  {0x0421, {0b01111, 0b10000, 0b10000, 0b10000, 0b10000, 0b10000, 0b01111, 0b00000}}, // С
  {0x0422, {0b11111, 0b00100, 0b00100, 0b00100, 0b00100, 0b00100, 0b00100, 0b00000}}, // Т
  {0x0423, {0b10001, 0b10001, 0b10001, 0b01111, 0b00001, 0b00001, 0b11110, 0b00000}}, // У
  {0x0424, {0b00100, 0b01110, 0b10101, 0b10101, 0b10101, 0b01110, 0b00100, 0b00000}}, // Ф
  {0x0425, {0b10001, 0b10001, 0b01010, 0b00100, 0b01010, 0b10001, 0b10001, 0b00000}}, // Х
  {0x0426, {0b10010, 0b10010, 0b10010, 0b10010, 0b10010, 0b11111, 0b00001, 0b00000}}, // Ц
  {0x0427, {0b10001, 0b10001, 0b10001, 0b01111, 0b00001, 0b00001, 0b00001, 0b00000}}, // Ч
  {0x0428, {0b10101, 0b10101, 0b10101, 0b10101, 0b10101, 0b10101, 0b11111, 0b00000}}, // Ш
  {0x0429, {0b10101, 0b10101, 0b10101, 0b10101, 0b10101, 0b11111, 0b00001, 0b00000}}, // Щ
  {0x042A, {0b11000, 0b01000, 0b01000, 0b01110, 0b01001, 0b01001, 0b01110, 0b00000}}, // Ъ
  {0x042B, {0b10001, 0b10001, 0b10001, 0b11101, 0b10011, 0b10011, 0b11101, 0b00000}}, // Ы
  {0x042C, {0b10000, 0b10000, 0b10000, 0b11110, 0b10001, 0b10001, 0b11110, 0b00000}}, // Ь
  {0x042D, {0b11110, 0b00001, 0b00001, 0b01111, 0b00001, 0b00001, 0b11110, 0b00000}}, // Э
  {0x042E, {0b10010, 0b10101, 0b10101, 0b11101, 0b10101, 0b10101, 0b10010, 0b00000}}, // Ю
  {0x042F, {0b01111, 0b10001, 0b10001, 0b01111, 0b00101, 0b01001, 0b10001, 0b00000}}, // Я
#if defined(MK61_DISPLAY_UC1609)
  {0x0430, {0b00000, 0b01110, 0b00001, 0b01111, 0b10001, 0b10011, 0b01101, 0b00000}}, // а
  {0x0431, {0b00111, 0b01000, 0b10000, 0b11110, 0b10001, 0b10001, 0b01110, 0b00000}}, // б
  {0x0432, {0b00000, 0b11110, 0b10001, 0b11110, 0b10001, 0b10001, 0b11110, 0b00000}}, // в
  {0x0433, {0b00000, 0b11111, 0b10000, 0b10000, 0b10000, 0b10000, 0b10000, 0b00000}}, // г
  {0x0434, {0b00000, 0b00110, 0b01010, 0b01010, 0b01010, 0b11111, 0b10001, 0b00000}}, // д
  {0x0435, {0b00000, 0b01110, 0b10001, 0b11111, 0b10000, 0b10001, 0b01110, 0b00000}}, // е
  {0x0451, {0b01010, 0b00000, 0b01110, 0b10001, 0b11111, 0b10000, 0b01110, 0b00000}}, // ё
  {0x0436, {0b00000, 0b10101, 0b10101, 0b01110, 0b01110, 0b10101, 0b10101, 0b00000}}, // ж
  {0x0437, {0b00000, 0b11110, 0b00001, 0b00110, 0b00001, 0b00001, 0b11110, 0b00000}}, // з
  {0x0438, {0b00000, 0b10001, 0b10011, 0b10101, 0b11001, 0b10001, 0b10001, 0b00000}}, // и
  {0x0439, {0b01010, 0b00100, 0b10001, 0b10011, 0b10101, 0b11001, 0b10001, 0b00000}}, // й
  {0x043A, {0b00000, 0b10001, 0b10010, 0b10100, 0b11000, 0b10100, 0b10010, 0b00000}}, // к
  {0x043B, {0b00000, 0b00111, 0b01001, 0b01001, 0b01001, 0b01001, 0b10001, 0b00000}}, // л
  {0x043C, {0b00000, 0b10001, 0b11011, 0b10101, 0b10101, 0b10001, 0b10001, 0b00000}}, // м
  {0x043D, {0b00000, 0b10001, 0b10001, 0b11111, 0b10001, 0b10001, 0b10001, 0b00000}}, // н
  {0x043E, {0b00000, 0b01110, 0b10001, 0b10001, 0b10001, 0b10001, 0b01110, 0b00000}}, // о
  {0x043F, {0b00000, 0b11111, 0b10001, 0b10001, 0b10001, 0b10001, 0b10001, 0b00000}}, // п
  {0x0440, {0b00000, 0b11110, 0b10001, 0b10001, 0b11110, 0b10000, 0b10000, 0b10000}}, // р
  {0x0441, {0b00000, 0b01111, 0b10000, 0b10000, 0b10000, 0b10000, 0b01111, 0b00000}}, // с
  {0x0442, {0b00000, 0b11111, 0b00100, 0b00100, 0b00100, 0b00100, 0b00100, 0b00000}}, // т
  {0x0443, {0b00000, 0b10001, 0b10001, 0b01111, 0b00001, 0b00001, 0b11110, 0b00000}}, // у
  {0x0444, {0b00100, 0b01110, 0b10101, 0b10101, 0b10101, 0b01110, 0b00100, 0b00000}}, // ф
  {0x0445, {0b00000, 0b10001, 0b01010, 0b00100, 0b01010, 0b10001, 0b10001, 0b00000}}, // х
  {0x0446, {0b00000, 0b10010, 0b10010, 0b10010, 0b10010, 0b11111, 0b00001, 0b00000}}, // ц
  {0x0447, {0b00000, 0b10001, 0b10001, 0b01111, 0b00001, 0b00001, 0b00001, 0b00000}}, // ч
  {0x0448, {0b00000, 0b10101, 0b10101, 0b10101, 0b10101, 0b10101, 0b11111, 0b00000}}, // ш
  {0x0449, {0b00000, 0b10101, 0b10101, 0b10101, 0b10101, 0b11111, 0b00001, 0b00000}}, // щ
  {0x044A, {0b00000, 0b11000, 0b01000, 0b01110, 0b01001, 0b01001, 0b01110, 0b00000}}, // ъ
  {0x044B, {0b00000, 0b10001, 0b10001, 0b11101, 0b10011, 0b10011, 0b11101, 0b00000}}, // ы
  {0x044C, {0b00000, 0b10000, 0b10000, 0b11110, 0b10001, 0b10001, 0b11110, 0b00000}}, // ь
  {0x044D, {0b00000, 0b11110, 0b00001, 0b01111, 0b00001, 0b00001, 0b11110, 0b00000}}, // э
  {0x044E, {0b00000, 0b10010, 0b10101, 0b10101, 0b11101, 0b10101, 0b10010, 0b00000}}, // ю
  {0x044F, {0b00000, 0b01111, 0b10001, 0b10001, 0b01111, 0b00101, 0b01001, 0b00000}}  // я
#endif
};

inline u16 uppercase(u16 codepoint) {
  if(codepoint >= 0x0430 && codepoint <= 0x044F) return codepoint - 0x20;
  if(codepoint == 0x0451) return 0x0401;
  return codepoint;
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
    case 0x042C: out = 'b'; return true; // Ь: closest built-in fallback
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
    case 0x0401: out = 'E'; return true; // Ё -> Е for Japanese A00
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
  if(a02_rom_char(codepoint, out)) return true;
  return a00_rom_char(codepoint, out);
#endif
}

inline bool fallback_char(u16 codepoint, u8& out) {
  codepoint = uppercase(codepoint);
  if(codepoint == 0x0427) {
    out = '4'; // Ч: acceptable only when all 8 custom glyphs are already used.
    return true;
  }
  if(codepoint == 0x0423) {
    out = 'Y'; // У: only when the current screen needs more than 8 custom glyphs.
    return true;
  }
  return false;
}

inline const u8* glyph_for(u16 codepoint) {
#if !defined(MK61_DISPLAY_UC1609)
  codepoint = uppercase(codepoint);
#endif
  for(usize i = 0; i < sizeof(CYRILLIC_GLYPHS) / sizeof(CYRILLIC_GLYPHS[0]); i++) {
    if(CYRILLIC_GLYPHS[i].codepoint == codepoint) return CYRILLIC_GLYPHS[i].rows;
  }
#if defined(MK61_DISPLAY_UC1609)
  const u16 upper = uppercase(codepoint);
  if(upper != codepoint) {
    for(usize i = 0; i < sizeof(CYRILLIC_GLYPHS) / sizeof(CYRILLIC_GLYPHS[0]); i++) {
      if(CYRILLIC_GLYPHS[i].codepoint == upper) return CYRILLIC_GLYPHS[i].rows;
    }
  }
#endif
  return NULL;
}

inline i8 slot_for(const font_map_t& map, u16 codepoint) {
  codepoint = uppercase(codepoint);
  for(u8 i = 0; i < map.count; i++) {
    if(map.codepoints[i] == codepoint) return i;
  }
  return -1;
}

inline void add_custom(font_map_t& map, u16 codepoint) {
  u8 rom;
  codepoint = uppercase(codepoint);
  if(rom_char(codepoint, rom)) return;
  if(glyph_for(codepoint) == NULL) return;
  if(slot_for(map, codepoint) >= 0) return;

  if(map.count < CUSTOM_GLYPHS) {
    map.codepoints[map.count++] = codepoint;
  } else {
    map.overflow = true;
  }
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
  for(u8 i = 0; i < map.count; i++) {
    lcd.createChar(i, (uint8_t*) glyph_for(map.codepoints[i]));
  }
#endif
}

inline void restore_default_font(void) {
#if defined(MK61_DISPLAY_UC1609)
  lcd.clearCustomChars();
#else
  const class_LCD_fonts lcd_fonts;
  lcd_fonts.load();
#endif
}

inline void write_text(const font_map_t& map, const char* text, u8 width) {
  u8 used = 0;
  while(*text != 0 && used < width) {
    const u16 raw_codepoint = read_utf8(text);
#if defined(MK61_DISPLAY_UC1609)
    const u16 codepoint = raw_codepoint;
#else
    const u16 codepoint = uppercase(raw_codepoint);
#endif
    u8 out;
    if(rom_char(codepoint, out)) {
      lcd.write(out);
    } else {
#if defined(MK61_DISPLAY_UC1609)
      const unsigned char* glyph3x5 = lcd_display::isTextProfile3x5(lcd.textProfile())
        ? font3x5Glyph(codepoint)
        : NULL;
      if(glyph3x5 != NULL) {
        lcd.writeGlyph3x5(glyph3x5);
      } else if(const u8* glyph = glyph_for(codepoint)) {
        lcd.writeGlyph(glyph);
      } else if(fallback_char(codepoint, out)) {
        lcd.write(out);
      } else {
        lcd.write((u8) '?');
      }
#else
      const i8 slot = slot_for(map, codepoint);
      if(slot >= 0) {
        lcd.write((u8) slot);
      } else if(fallback_char(codepoint, out)) {
        lcd.write(out);
      } else {
        lcd.write((u8) '?');
      }
#endif
    }
    used++;
  }

  while(used++ < width) lcd.write((u8) ' ');
}

inline void print_at(u8 x, u8 y, const char* text, u8 width = LCD_WIDTH) {
  MK61DisplayUpdate update(lcd);
  font_map_t map = {{0}, 0, false};
  scan_text(map, text, width);
  load_custom_font(map);
  lcd.setCursor(x, y);
  write_text(map, text, width);
}

inline void print_lines(const char* text0, const char* text1) {
  MK61DisplayUpdate update(lcd);
  font_map_t map = {{0}, 0, false};
  scan_text(map, text0, LCD_WIDTH);
  scan_text(map, text1, LCD_WIDTH);
  load_custom_font(map);

  lcd.setCursor(0, 0);
  write_text(map, text0, LCD_WIDTH);

  lcd.setCursor(0, 1);
  write_text(map, text1, LCD_WIDTH);
}

inline void print_menu_window(char mark0, const char* text0, char mark1, const char* text1) {
  MK61DisplayUpdate update(lcd);
  font_map_t map = {{0}, 0, false};
  scan_text(map, text0, LCD_WIDTH - 1);
  scan_text(map, text1, LCD_WIDTH - 1);
  load_custom_font(map);

  lcd.setCursor(0, 0);
  lcd.write((u8) mark0);
  write_text(map, text0, LCD_WIDTH - 1);

  lcd.setCursor(0, 1);
  lcd.write((u8) mark1);
  write_text(map, text1, LCD_WIDTH - 1);
}

inline void print_menu_line(u8 y, char mark, const char* text) {
  MK61DisplayUpdate update(lcd);
  font_map_t map = {{0}, 0, false};
  scan_text(map, text, LCD_WIDTH - 1);
  load_custom_font(map);

  lcd.setCursor(0, y);
  lcd.write((u8) mark);
  write_text(map, text, LCD_WIDTH - 1);
}

} // namespace lcd_ru

#endif

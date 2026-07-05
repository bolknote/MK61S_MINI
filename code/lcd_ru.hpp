#ifndef LCD_RU_ENCODER
#define LCD_RU_ENCODER

#include "lcd_gui.hpp"

namespace lcd_ru {

static constexpr u8 LCD_WIDTH = 16;
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
  {0x042F, {0b01111, 0b10001, 0b10001, 0b01111, 0b00101, 0b01001, 0b10001, 0b00000}}  // Я
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

inline bool rom_char(u16 codepoint, u8& out) {
  codepoint = uppercase(codepoint);
  if(codepoint < 0x80) {
    out = (u8) codepoint;
    return true;
  }

  switch(codepoint) {
    case 0x0410: out = 'A'; return true; // А
    case 0x0412: out = 'B'; return true; // В
    case 0x0415: out = 'E'; return true; // Е
    case 0x0401: out = 'E'; return true; // Ё
    case 0x0417: out = '3'; return true; // З
    case 0x041A: out = 'K'; return true; // К
    case 0x041C: out = 'M'; return true; // М
    case 0x041D: out = 'H'; return true; // Н
    case 0x041E: out = 'O'; return true; // О
    case 0x0420: out = 'P'; return true; // Р
    case 0x0421: out = 'C'; return true; // С
    case 0x0422: out = 'T'; return true; // Т
    case 0x0425: out = 'X'; return true; // Х
    default: return false;
  }
}

inline bool fallback_char(u16 codepoint, u8& out) {
  codepoint = uppercase(codepoint);
  if(codepoint == 0x0423) {
    out = 'Y'; // У: only when the current screen needs more than 8 custom glyphs.
    return true;
  }
  return false;
}

inline const u8* glyph_for(u16 codepoint) {
  codepoint = uppercase(codepoint);
  for(usize i = 0; i < sizeof(CYRILLIC_GLYPHS) / sizeof(CYRILLIC_GLYPHS[0]); i++) {
    if(CYRILLIC_GLYPHS[i].codepoint == codepoint) return CYRILLIC_GLYPHS[i].rows;
  }
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
  for(u8 i = 0; i < map.count; i++) {
    lcd.createChar(i, (uint8_t*) glyph_for(map.codepoints[i]));
  }
}

inline void restore_default_font(void) {
  const class_LCD_fonts lcd_fonts;
  lcd_fonts.load();
}

inline void write_text(const font_map_t& map, const char* text, u8 width) {
  u8 used = 0;
  while(*text != 0 && used < width) {
    const u16 codepoint = uppercase(read_utf8(text));
    u8 out;
    if(rom_char(codepoint, out)) {
      lcd.write(out);
    } else {
      const i8 slot = slot_for(map, codepoint);
      if(slot >= 0) {
        lcd.write((u8) slot);
      } else if(fallback_char(codepoint, out)) {
        lcd.write(out);
      } else {
        lcd.write((u8) '?');
      }
    }
    used++;
  }

  while(used++ < width) lcd.write((u8) ' ');
}

inline void print_at(u8 x, u8 y, const char* text, u8 width = LCD_WIDTH) {
  font_map_t map = {{0}, 0, false};
  scan_text(map, text, width);
  load_custom_font(map);
  lcd.setCursor(x, y);
  write_text(map, text, width);
}

inline void print_menu_window(char mark0, const char* text0, char mark1, const char* text1) {
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

} // namespace lcd_ru

#endif

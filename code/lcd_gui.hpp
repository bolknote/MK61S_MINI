#ifndef LCD_FONT_PACK
#define LCD_FONT_PACK
#include  "config.h"
#include  "rust_types.h"
#include  "display.hpp"
#include  "display_symbols.hpp"
#include  "lcd_charset.hpp"
#if defined(MK61_OLED1602_WS0010)
  #include "ws0010_charset.hpp"
#endif
#include  "mk61emu_core.h"

#if defined(MK61_DISPLAY_UC1609)
static const u8 GE                = display_symbol::uc1609::GE;
static const u8 P_RUS             = display_symbol::uc1609::CYR_PE;
static const u8 B_RUS             = display_symbol::uc1609::CYR_BE;
static const u8 D_RUS             = display_symbol::uc1609::CYR_DE;
static const u8 I_RUS             = display_symbol::uc1609::CYR_I;
static const u8 G_RUS             = display_symbol::uc1609::CYR_GHE;
static const u8 LCD_CHAR_POW2     = display_symbol::uc1609::POW2;
static const u8 LCD_CHAR_POWY     = display_symbol::uc1609::POWY;
static const u8 LCD_CHAR_XOR      = display_symbol::uc1609::XOR;

/* Набор символов авторского UC1609-шрифта */
static const u8 LCD_CYC_ARROW     = display_symbol::uc1609::CYC_ARROW;
static const u8 LCD_DIVIDE_CHAR   = display_symbol::uc1609::DIVIDE;
static const u8 LCD_NOT_EQU_CHAR  = display_symbol::uc1609::NOT_EQUAL;
static const u8 LCD_POW_X_CHAR    = display_symbol::uc1609::POW_X;
static const u8 LCD_UP_ARROW_CHAR = display_symbol::uc1609::UP_ARROW;
static const u8 LCD_LT_ARROW_CHAR = display_symbol::uc1609::LT_ARROW;
static const u8 LCD_RT_ARROW_CHAR = display_symbol::uc1609::RT_ARROW;
static const u8 LCD_PI_CHAR       = display_symbol::uc1609::PI_SYMBOL;
static const u8 LCD_SQRT_CHAR     = display_symbol::uc1609::SQRT;
static const u8 LCD_Em1_CHAR      = display_symbol::uc1609::EM1;
static const u8 LCD_GRAD_CHAR     = display_symbol::uc1609::GRAD;
static const u8 LCD_QUOTE_CHAR    = 0x60;
static const u8 LCD_DOUBLE_QUOTE_CHAR    = 0x22;
static const u8 CH_RUS            = display_symbol::uc1609::CYR_CHE;
#elif defined(MK61_OLED1602_WS0010)
static const u8 GE                = ws0010_charset::cgram::GREATER_OR_EQUAL;
static const u8 P_RUS             = ws0010_charset::CYR_PE;
static const u8 B_RUS             = ws0010_charset::CYR_BE;
static const u8 D_RUS             = ws0010_charset::CYR_DE;
static const u8 I_RUS             = ws0010_charset::CYR_I;
static const u8 G_RUS             = ws0010_charset::CYR_GHE;
static const u8 LCD_CHAR_POW2     = ws0010_charset::cgram::POWER_2;
static const u8 LCD_CHAR_POWY     = ws0010_charset::cgram::POWER_Y;
static const u8 LCD_CHAR_XOR      = ws0010_charset::cgram::XOR;

/* FT=10 ROM plus the project's fixed WS0010 CGRAM slots. */
static const u8 LCD_CYC_ARROW     = ws0010_charset::cgram::CYCLE_ARROW;
static const u8 LCD_DIVIDE_CHAR   = ws0010_charset::DIVIDE;
static const u8 LCD_NOT_EQU_CHAR  = ws0010_charset::cgram::NOT_EQUAL;
static const u8 LCD_POW_X_CHAR    = ws0010_charset::cgram::POWER_X;
static const u8 LCD_UP_ARROW_CHAR = ws0010_charset::UP_ARROW_FALLBACK;
static const u8 LCD_LT_ARROW_CHAR = ws0010_charset::LEFT_ARROW;
static const u8 LCD_RT_ARROW_CHAR = ws0010_charset::RIGHT_ARROW;
static const u8 LCD_PI_CHAR       = ws0010_charset::PI_SYMBOL;
static const u8 LCD_SQRT_CHAR     = ws0010_charset::cgram::SQUARE_ROOT;
static const u8 LCD_Em1_CHAR      = ws0010_charset::INVERSE_MARKER_FALLBACK;
static const u8 LCD_GRAD_CHAR     = ws0010_charset::DEGREE;
static const u8 LCD_QUOTE_CHAR    = 0x60;
static const u8 LCD_DOUBLE_QUOTE_CHAR = 0x22;
static const u8 CH_RUS            = ws0010_charset::CYR_CHE;
#elif defined(MK61_LCD1602_A02)
static const u8 GE                = 0x00;
static const u8 P_RUS             = lcd_charset::CYR_PE;
static const u8 B_RUS             = lcd_charset::CYR_BE;
static const u8 D_RUS             = lcd_charset::CYR_DE;
static const u8 I_RUS             = lcd_charset::CYR_I;
static const u8 G_RUS             = lcd_charset::CYR_GHE;
static const u8 LCD_CHAR_POW2     = 0xB2;
static const u8 LCD_CHAR_POWY     = 0x01;
static const u8 LCD_CHAR_XOR      = 0x02;

/* Набор символов LCD1602 A02 */
static const u8 LCD_CYC_ARROW     = 0x05;
static const u8 LCD_DIVIDE_CHAR   = 0xF7;
static const u8 LCD_NOT_EQU_CHAR  = 0x03;
static const u8 LCD_POW_X_CHAR    = 0x06;
static const u8 LCD_UP_ARROW_CHAR = '^';
static const u8 LCD_LT_ARROW_CHAR = 0x7F;
static const u8 LCD_RT_ARROW_CHAR = 0x7E;
static const u8 LCD_PI_CHAR       = 0x93;
static const u8 LCD_SQRT_CHAR     = 0x04;
static const u8 LCD_Em1_CHAR      = 0xB9;
static const u8 LCD_GRAD_CHAR     = 0xB7;
static const u8 LCD_QUOTE_CHAR    = 0x60;
static const u8 LCD_DOUBLE_QUOTE_CHAR    = 0x22;
static const u8 CH_RUS            = lcd_charset::CYR_CHE;
#else
static const u8 GE                = 0x00;
static const u8 P_RUS             = 0x01;
static const u8 B_RUS             = 0x02;
static const u8 D_RUS             = 0x03;
static const u8 I_RUS             = 0x04;
static const u8 G_RUS             = 0x05;
static const u8 LCD_CHAR_POW2     = 0x06;
static const u8 LCD_CHAR_POWY     = 0x07;
static const u8 LCD_CHAR_XOR      = 0x08;

/* Стандартный набор символов из ПЗУ LCD */
static const u8 LCD_CYC_ARROW     = 0xDB;
static const u8 LCD_DIVIDE_CHAR   = 0xFD;
static const u8 LCD_NOT_EQU_CHAR  = 0xB7;
static const u8 LCD_POW_X_CHAR    = 0xEB;
static const u8 LCD_UP_ARROW_CHAR = '^';
static const u8 LCD_LT_ARROW_CHAR = 0x7F;
static const u8 LCD_RT_ARROW_CHAR = 0x7E;
static const u8 LCD_PI_CHAR       = 0xF7;
static const u8 LCD_SQRT_CHAR     = 0xE8;
static const u8 LCD_Em1_CHAR      = 0xE9;
static const u8 LCD_GRAD_CHAR     = 0xDF;
static const u8 LCD_QUOTE_CHAR    = 0x60;
static const u8 LCD_DOUBLE_QUOTE_CHAR    = 0x22;
static const u8 CH_RUS            = 0xD1;
#endif

class class_LCD_Label {
  private:
    u8 x, y;

  public:

    constexpr class_LCD_Label(u8 to_x, u8 to_y) : x(to_x), y(to_y) {}
    void print(const char* text) const {
      MK61DisplayUpdate update(main_lcd());
      main_lcd().setCursor(x, y);
      main_lcd().print(text);
    }
    void print(char symbol) const {
      MK61DisplayUpdate update(main_lcd());
      main_lcd().setCursor(x, y);
      main_lcd().print(symbol);
    }
    void print(int num) const {
      MK61DisplayUpdate update(main_lcd());
      main_lcd().setCursor(x, y);
      main_lcd().print(num);
    }
    void print_hex(int num) const {
      MK61DisplayUpdate update(main_lcd());
      main_lcd().setCursor(x, y);
      if(num < 10) main_lcd().print(' ');
      main_lcd().print(num, HEX);
    }
};

class LCD_GRD_Label {
  private:
    
    static constexpr u8 X = 6;
    static constexpr u8 Y = 0;

    const u32 ANGLE_UNIT_TEXT[3] = {
      0 << 24 | ' ' << 16   | ' ' << 8   |     'P',  // "Р  "
      0 << 24 | G_RUS << 16 | ' ' << 8   |     ' ',  // "  Г"
      0 << 24 | D_RUS << 16 | 'P' << 8   |   G_RUS   // "ГРД"
    };
    
    bool   on;

  public:

    constexpr LCD_GRD_Label(void) : on(true) {}

    void  disable(void) {
      MK61DisplayUpdate update(main_lcd());
      main_lcd().setCursor(X, Y);
      main_lcd().print("  ");
      on = false;
    };

    void  enable(void)  {on = true;};

    void  print(AngleUnit angle) {
      if(on) {
        MK61DisplayUpdate update(main_lcd());
        main_lcd().setCursor(X, Y); main_lcd().print((const char*) &ANGLE_UNIT_TEXT[angle - RADIAN]);
      }
    }

    void  print(const char* text) const {
      if(on) {
        MK61DisplayUpdate update(main_lcd());
        main_lcd().setCursor(X, Y); main_lcd().print(text);
      }
    }

    void  print(char symbol) const {
      if(on) {
        MK61DisplayUpdate update(main_lcd());
        main_lcd().setCursor(X, Y); main_lcd().print(symbol);
      }
    }

    void  print(int num) const {
      if(on) {
        MK61DisplayUpdate update(main_lcd());
        main_lcd().setCursor(X, Y); main_lcd().print(num);
      }
    }

    void  print_hex(int num) const {
      if(on) {
        MK61DisplayUpdate update(main_lcd());
        main_lcd().setCursor(X, Y);
        if(num < 10) main_lcd().print(' ');
        main_lcd().print(num, HEX);
      }
    }
};

class class_LCD_fonts {
  private:
   // One immutable, profile-specific CGRAM image.  Keeping glyphs as object
   // members used to make every short-lived loader object 96 bytes large; the
   // old common table also retained characters which A02/WS0010 never load.
#if defined(MK61_OLED1602_WS0010)
   inline static constexpr u8 fixed_glyphs[8][8] = {
    { // greater-or-equal
      0b00100,
      0b00010,
      0b00001,
      0b00010,
      0b00100,
      0b01001,
      0b00010,
      0b00100
    },
    { // y superscript
      0b10100,
      0b10100,
      0b01100,
      0b00100,
      0b11000,
      0b00000,
      0b00000,
      0b00000
    },
    { // xor
      0b01110,
      0b10101,
      0b10101,
      0b11111,
      0b10101,
      0b10101,
      0b01110,
      0b00000
    },
    { // not equal
      0b00001,
      0b00010,
      0b11111,
      0b00100,
      0b11111,
      0b01000,
      0b10000,
      0b00000
    },
    { // square root
      0b00001,
      0b00010,
      0b00010,
      0b10100,
      0b01000,
      0b00000,
      0b00000,
      0b00000
    },
    { // cycle arrow
      0b00110,
      0b01001,
      0b10000,
      0b10000,
      0b10001,
      0b01001,
      0b00111,
      0b00000
    },
    { // x superscript
      0b00000,
      0b00000,
      0b01010,
      0b00100,
      0b01010,
      0b00000,
      0b00000,
      0b00000
    },
    { // 2 superscript
      0b11100,
      0b00100,
      0b01100,
      0b10000,
      0b11100,
      0b00000,
      0b00000,
      0b00000
    }
   };
   static_assert(ws0010_charset::cgram::GREATER_OR_EQUAL == 0 &&
                 ws0010_charset::cgram::POWER_Y == 1 &&
                 ws0010_charset::cgram::XOR == 2 &&
                 ws0010_charset::cgram::NOT_EQUAL == 3 &&
                 ws0010_charset::cgram::SQUARE_ROOT == 4 &&
                 ws0010_charset::cgram::CYCLE_ARROW == 5 &&
                 ws0010_charset::cgram::POWER_X == 6 &&
                 ws0010_charset::cgram::POWER_2 == 7,
                 "WS0010 CGRAM image must follow the fixed slot policy");
#elif defined(MK61_LCD1602_A02)
   inline static constexpr u8 fixed_glyphs[7][8] = {
    {0b00100, 0b00010, 0b00001, 0b00010, 0b00100, 0b01001, 0b00010, 0b00100},
    {0b10100, 0b10100, 0b01100, 0b00100, 0b11000, 0b00000, 0b00000, 0b00000},
    {0b01110, 0b10101, 0b10101, 0b11111, 0b10101, 0b10101, 0b01110, 0b00000},
    {0b00001, 0b00010, 0b11111, 0b00100, 0b11111, 0b01000, 0b10000, 0b00000},
    {0b00001, 0b00010, 0b00010, 0b10100, 0b01000, 0b00000, 0b00000, 0b00000},
    {0b00110, 0b01001, 0b10000, 0b10000, 0b10001, 0b01001, 0b00111, 0b00000},
    {0b00000, 0b00000, 0b01010, 0b00100, 0b01010, 0b00000, 0b00000, 0b00000}
   };
#elif !defined(MK61_DISPLAY_UC1609)
   inline static constexpr u8 fixed_glyphs[9][8] = {
    {0b00100, 0b00010, 0b00001, 0b00010, 0b00100, 0b01001, 0b00010, 0b00100}, // greater-or-equal
    {0b11111, 0b10001, 0b10001, 0b10001, 0b10001, 0b10001, 0b10001, 0b00000}, // П
    {0b11111, 0b10000, 0b10000, 0b11110, 0b10001, 0b10001, 0b11110, 0b00000}, // Б
    {0b00110, 0b01010, 0b01010, 0b01010, 0b01010, 0b01010, 0b11111, 0b10001}, // Д
    {0b10001, 0b10001, 0b10001, 0b10011, 0b10101, 0b11001, 0b10001, 0b00000}, // И
    {0b11111, 0b10000, 0b10000, 0b10000, 0b10000, 0b10000, 0b00000, 0b00000}, // Г
    {
      0b11100,
      0b00100,
      0b01100,
      0b10000,
      0b11100,
      0b00000,
      0b00000,
      0b00000
    }, // 2 superscript
    {
      0b10100,
      0b10100,
      0b01100,
      0b00100,
      0b11000,
      0b00000,
      0b00000,
      0b00000
    }, // y superscript
    {
      0b01110,
      0b10101,
      0b10101,
      0b11111,
      0b10101,
      0b10101,
      0b01110,
      0b00000
    } // xor
   };
#endif
  public:
#if defined(MK61_OLED1602_WS0010)
    void loadWs0010Slot(u8 slot, MK61Display& display) const {
      if(slot < 8) display.createChar(slot, (uint8_t*) fixed_glyphs[slot]);
    }
    void loadWs0010Slot(u8 slot) const {
      loadWs0010Slot(slot, main_lcd());
    }
#endif

    void load(void) const {
      #if defined(MK61_DISPLAY_UC1609)
        main_lcd().clearCustomChars();
        return;
#else
      if(main_lcd().graphicsMode()) {
        main_lcd().clearCustomChars();
        return;
      }
      #if defined(MK61_LCD1602_A02) || defined(MK61_OLED1602_WS0010)
#if defined(MK61_OLED1602_WS0010)
        for(u8 slot = 0; slot < 8; slot++) loadWs0010Slot(slot);
#else
        for(u8 slot = 0; slot < 7; slot++) {
          main_lcd().createChar(slot, (uint8_t*) fixed_glyphs[slot]);
        }
#endif
        return;
      #else
      for(u8 slot = 0; slot < 9; slot++) {
        main_lcd().createChar(slot, (uint8_t*) fixed_glyphs[slot]);
      }
      #endif
#endif
    }

};

static_assert(sizeof(class_LCD_fonts) == 1,
              "LCD font loader must not own copies of glyph tables");

#endif

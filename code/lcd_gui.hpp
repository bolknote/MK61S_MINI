#ifndef LCD_FONT_PACK
#define LCD_FONT_PACK
#include  "config.h"
#include  "rust_types.h"
#include  "display.hpp"
#include  "display_symbols.hpp"
#include  "lcd_charset.hpp"
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

const u8 ROUND_ARROW_bit[8] = {
  0b11110,
  0b01101,
  0b10101,
  0b10001,
  0b10101,
  0b10110,
  0b01111,
  0b00000
};

const u8 Alpha[9] = {
  0b11111,
  0b11011,
  0b10101,
  0b11101,
  0b11001,
  0b10101,
  0b11001,
  0b11111
};

const u8 Symbol[9] = {
  0b11111,
  0b11111,
  0b11111,
  0b11011,
  0b11011,
  0b10101,
  0b10101,
  0b11111
};

class class_LCD_fonts {
  private:
   const u8 fonts[9 * 8] = {
    //const u8 GE_bit[8] = {
      0b00100,
      0b00010,
      0b00001,
      0b00010,
      0b00100,
      0b01001,
      0b00010,
      0b00100,
    //const u8 P_ru[8] = {
      0b11111,
      0b10001,
      0b10001,
      0b10001,
      0b10001,
      0b10001,
      0b10001,
      0b00000,
    //const u8 B_ru[8] = {
      0b11111,
      0b10000,
      0b10000,
      0b11110,
      0b10001,
      0b10001,
      0b11110,
      0b00000,
    //const u8 D_ru[8] = {
      0b00110,
      0b01010,
      0b01010,
      0b01010,
      0b01010,
      0b01010,
      0b11111,
      0b10001,
    //const u8 I_ru[8] = {
      0b10001,
      0b10001,
      0b10001,
      0b10011,
      0b10101,
      0b11001,
      0b10001,
      0b00000,
    //const u8 G_ru[8] = {
      0b11111,
      0b10000,
      0b10000,
      0b10000,
      0b10000,
      0b10000,
      0b00000,
      0b00000,
    //const u8 POWSQR_bit[8] = {
      0b11100,
      0b00100,
      0b01100,
      0b10000,
      0b11100,
      0b00000,
      0b00000,
      0b00000,
    //const u8 POWY_bit[8] = {
      0b10100,
      0b10100,
      0b01100,
      0b00100,
      0b11000,
      0b00000,
      0b00000,
      0b00000,
    //const u8 XOR_bit[8] = {
      0b01110,
      0b10101,
      0b10101,
      0b11111,
      0b10101,
      0b10101,
      0b01110,
      0b00000
};
    const u8 not_equal_bit[8] = {
      0b00001,
      0b00010,
      0b11111,
      0b00100,
      0b11111,
      0b01000,
      0b10000,
      0b00000
    };
    const u8 sqrt_bit[8] = {
      0b00001,
      0b00010,
      0b00010,
      0b10100,
      0b01000,
      0b00000,
      0b00000,
      0b00000
    };
    const u8 pow_x_bit[8] = {
      0b00000,
      0b00000,
      0b01010,
      0b00100,
      0b01010,
      0b00000,
      0b00000,
      0b00000
    };
//    const u8* fonts = {&GE_bit, &P_ru, &B_ru, &D_ru, &I_ru, &G_ru, POWSQR_bit, &POWY_bit, &XOR_bit};
  public:
    void load(void) const {
      #if defined(MK61_DISPLAY_UC1609)
        main_lcd().clearCustomChars();
        return;
      #endif
      u32 ascii=0;
      #if defined(MK61_LCD1602_A02)
        main_lcd().createChar(GE, (uint8_t*) &fonts[0]);
        main_lcd().createChar(LCD_CHAR_POWY, (uint8_t*) &fonts[7 * 8]);
        main_lcd().createChar(LCD_CHAR_XOR, (uint8_t*) &fonts[8 * 8]);
        main_lcd().createChar(LCD_NOT_EQU_CHAR, (uint8_t*) &not_equal_bit[0]);
        main_lcd().createChar(LCD_SQRT_CHAR, (uint8_t*) &sqrt_bit[0]);
        main_lcd().createChar(LCD_CYC_ARROW, (uint8_t*) &ROUND_ARROW_bit[0]);
        main_lcd().createChar(LCD_POW_X_CHAR, (uint8_t*) &pow_x_bit[0]);
        return;
      #endif
      for(int i=0; i < 9 * 8; i += 8) {
        main_lcd().createChar(ascii++, (uint8_t*) &fonts[i]);
      }
    }

    void load(int offset, int nChar) const {
      #if defined(MK61_DISPLAY_UC1609)
        main_lcd().clearCustomChars();
        return;
      #endif
      main_lcd().createChar(nChar, (uint8_t*) &fonts[offset]);
    }
};

#endif

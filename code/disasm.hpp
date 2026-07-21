#ifndef DISASSEMBLER
#define DISASSEMBLER

#include "config.h"
#include "lcd_gui.hpp"
#include "mk61emu_core.h"
#include "rust_types.h"
#include "tools.hpp"
#include "debug.h"

extern  class_calc_config   config;

const int LEN_DISASM_LINE = 5;

inline void disasm_store_u16_le(char* buffer, u16 value) {
  buffer[0] = (char) (value & 0xFFu);
  buffer[1] = (char) ((value >> 8) & 0xFFu);
}

inline void disasm_store_u32_le(char* buffer, u32 value) {
  buffer[0] = (char) (value & 0xFFu);
  buffer[1] = (char) ((value >> 8) & 0xFFu);
  buffer[2] = (char) ((value >> 16) & 0xFFu);
  buffer[3] = (char) ((value >> 24) & 0xFFu);
}

class class_disassm_mk61 {
  private:
    static constexpr u8 X = 0;
    static constexpr u8 Y = 0;

    bool  lcd_enable;        // Дизассемблер МК-61 в верхней строке ЖКИ: 1 — включён, 0 — выключен
    u8    cache_IP_mk61;

    const u32 mk61_disassm_50_60[15] = {
      ' ' << 24 | ' ' << 16   | P_RUS << 8 | 'C',
      ' ' << 24 | ' ' << 16   | P_RUS << 8 | B_RUS,
      ' ' << 24 | 'O' << 16   | '/' << 8   | 'B',
      ' ' << 24 | ' ' << 16   | P_RUS << 8 | P_RUS,
      ' ' << 24 | P_RUS << 16 | 'O' << 8   | 'H',
      ' ' << 24 | '?' << 16   | '?' << 8   | ' ',
      ' ' << 24 | '?' << 16   | '?' << 8   | ' ',
      ' ' << 24 | '0' << 16   | LCD_NOT_EQU_CHAR << 8  | 'x',
      ' ' << 24 | ' ' << 16   | '2' << 8   | 'L',
      ' ' << 24 | '0' << 16   | GE << 8    | 'x',
      ' ' << 24 | ' ' << 16   | '3' << 8   | 'L',
      ' ' << 24 | ' ' << 16   | '1' << 8   | 'L',
      ' ' << 24 | '0' << 16   | '<' << 8   | 'x',
      ' ' << 24 | ' ' << 16   | '0' << 8   | 'L',
      ' ' << 24 | '0' << 16   | '=' << 8   | 'x'
    };
    const u32 mk61_disassm_0A_1E[21] = {
      ' ' << 24 | ' ' << 16   | ' ' << 8 | '.',
      ' ' << 24 | '/' << 16   | '-' << 8 | '/',
      ' ' << 24 | ' ' << 16   | P_RUS << 8 | 'B',
      ' ' << 24 | ' ' << 16   | 'x' << 8 | 'C',
      ' ' << 24 | ' ' << 16   | LCD_UP_ARROW_CHAR << 8 | 'B',
      ' ' << 24 | 'x' << 16   | 'B' << 8 | 'F',
      ' ' << 24 | ' ' << 16   | ' ' << 8 | '+',
      ' ' << 24 | ' ' << 16   | ' ' << 8 | '-',
      ' ' << 24 | ' ' << 16   | ' ' << 8 | '*',
      ' ' << 24 | ' ' << 16   | ' ' << 8 | LCD_DIVIDE_CHAR,
      ' ' << 24 | ' ' << 16   | LCD_RT_ARROW_CHAR << 8 | LCD_LT_ARROW_CHAR,
      ' ' << 24 | LCD_POW_X_CHAR << 16   | '0' << 8 | '1',
      ' ' << 24 | ' ' << 16   | LCD_POW_X_CHAR << 8 | 'e',
      ' ' << 24 | ' ' << 16   | 'g' << 8 | 'l',
      ' ' << 24 | ' ' << 16   | 'n' << 8 | 'l',
      'n' << 24 | 'i' << 16   | 's' << 8 | 'a',
      's' << 24 | 'o' << 16   | 'c' << 8 | 'a',
      ' ' << 24 | 'g' << 16   | 't' << 8 | 'a',
      ' ' << 24 | 'n' << 16   | 'i' << 8 | 's',
      ' ' << 24 | 's' << 16   | 'o' << 8 | 'c',
      ' ' << 24 | ' ' << 16   | 'g' << 8 | 't'
    };
    const u32 mk61_disassm_20_2A[11] = {
      ' ' << 24 | ' ' << 16   | ' ' << 8 | LCD_PI_CHAR,
      ' ' << 24 | ' ' << 16   | ' ' << 8 | LCD_SQRT_CHAR,
      ' ' << 24 | ' ' << 16   | LCD_CHAR_POW2 << 8 | 'x',
      ' ' << 24 | 'x' << 16   | '/' << 8 | '1',
      ' ' << 24 | ' ' << 16   | LCD_CHAR_POWY << 8 | 'x',
      ' ' << 24 | ' ' << 16   | ' ' << 8 | LCD_CYC_ARROW,
      ' ' << 24 | LCD_QUOTE_CHAR << 16   | LCD_RT_ARROW_CHAR << 8 | LCD_GRAD_CHAR,
      ' ' << 24 | '?' << 16   | '?' << 8   | ' ',
      ' ' << 24 | '?' << 16   | '?' << 8   | ' ',
      ' ' << 24 | '?' << 16   | '?' << 8   | ' ',
      '"' << 24 | LCD_QUOTE_CHAR << 16   | LCD_RT_ARROW_CHAR << 8   | LCD_GRAD_CHAR
    };
    const u32 mk61_disassm_30_3E[15] = {
      '"' << 24 | LCD_QUOTE_CHAR << 16 | LCD_LT_ARROW_CHAR << 8 | LCD_GRAD_CHAR,      // 0x30  o<-'"
      ' ' << 24 | '|' << 16   | 'x' << 8 | '|',                                       // 0x31  |x|
      ' ' << 24 | ' ' << 16   | 'H' << 8 | '3',                                       // 0x32  ЗН
      ' ' << 24 | LCD_GRAD_CHAR << 16 | LCD_LT_ARROW_CHAR << 8 | LCD_QUOTE_CHAR,      // 0x33  '<-o
      ' ' << 24 | ']' << 16   | 'x' << 8 | '[',                                       // 0x34  [x]
      ' ' << 24 | '}' << 16   | 'x' << 8 | '{',                                       // 0x35  {x}
      ' ' << 24 | 'x' << 16   | 'a' << 8 | 'm',                                       // 0x36  max
      ' ' << 24 | ' ' << 16   | ' ' << 8 | '^',                                       // 0x37  ^
      ' ' << 24 | ' ' << 16   | ' ' << 8 | 'v',                                       // 0x38  v
      ' ' << 24 | ' ' << 16   | ' ' << 8 | LCD_CHAR_XOR,                              // 0x39  (+)
      ' ' << 24 | 'B' << 16   | 'H' << 8 | I_RUS,                                     // 0x3A  ИНВ
      ' ' << 24 | ' ' << 16   | CH_RUS << 8 | 'C',                                    // 0x3B  СЧ
      '-' << 24 | '-' << 16   | '-' << 8 | '-',                                       // 0x3C  ----
      '"' << 24 | LCD_QUOTE_CHAR << 16   | LCD_RT_ARROW_CHAR << 8   | LCD_GRAD_CHAR,  // 0x3D o->'" (повтор 2A)
      ' ' << 24 | 'y' << 16   | LCD_LT_ARROW_CHAR << 8  | 'x',                        // 0x3E x<-y (и еще x->x1)
    };

    u8   get_register_symbol(u8 code) {
      return (code < 0x3A)? code : (code == 0x3D)? D_RUS : code + 7;
    }

    inline bool is_update(char* buffer) {
      if(lcd_enable) {
        const u8 IP_mk61 = core_61::get_IP(); //MK61Emu_get_IP();

        if(IP_mk61 != cache_IP_mk61) { // счетчик команд изменился
          if(config.output_IP) {
            main_lcd().setCursor(14, 1); print_hex(IP_mk61);
          }

          cache_IP_mk61 = IP_mk61;

          /*memset(buffer, ' ', LEN_DISASM_LINE); buffer[LEN_DISASM_LINE] = 0;*/
          disasm_store_u32_le(buffer, 0);
          disasm_store_u16_le(buffer + 4, 0);
          // дизассемблируем с адреса IP_mk61     DISP [___ ___ ___]
          const u8 addr = IP_mk61 - 1;
          if(addr < core_61::program_steps()) {
            const u8 code = core_61::get_code(core_61::get_ring_address(addr));
            #ifdef DEBUG_DISASMBLER
              Serial.print("mk61 IP "); Serial.print(mk61s.get_IPH()); Serial.print(':'); Serial.print(mk61s.get_IPL());
              Serial.print(" linear address $"); Serial.print(addr); Serial.print(" code "); Serial.println(code, HEX);
            #endif
            if(code <= 9) {
                disasm_store_u32_le(buffer, (u32) ' ' << 24 | ' ' << 16| ((code + '0') << 8) | '#');
              } else if(code >= 0x0A && code < 0x1F) {
                disasm_store_u32_le(buffer, mk61_disassm_0A_1E[code - 0x0A]);
              } else if(code >= 0x20 && code < 0x2B) {
                disasm_store_u32_le(buffer, mk61_disassm_20_2A[code - 0x20]);
              }  else if(code >= 0x30 && code < 0x3F) {
                disasm_store_u32_le(buffer, mk61_disassm_30_3E[code - 0x30]);
              } else if(code >= 0x40 && code < 0x50) { // Пn либо x->П
                #ifdef B3_34
                  disasm_store_u16_le(buffer, (u16) (get_register_symbol(code - 0x10) << 8) | P_RUS);
                #endif
                #ifndef B3_34
                  disasm_store_u32_le(buffer, (u32) (get_register_symbol(code - 0x10) << 24 | P_RUS << 16 | LCD_RT_ARROW_CHAR << 8 | 'x'));  // MK61 мнемоника x->П
                #endif
              } else if(code >= 0x50 && code < 0x5F) { // СП,БП,В/О,ПП,NOP,?,?,x!=0,L2,x>=0,L3,L1,x<0,L0,x==0
                disasm_store_u32_le(buffer, mk61_disassm_50_60[code - 0x50]);
              } else if(code >= 0x60 && code < 0x70) { // ИПn
                #ifdef B3_34
                  disasm_store_u32_le(buffer, (u32) ' ' << 24 | (u32) get_register_symbol(code - 0x30) << 16 | (u32) P_RUS << 8 | I_RUS);
                #endif
                #ifndef B3_34
                  disasm_store_u32_le(buffer, (u32) (get_register_symbol(code - 0x30) << 24 | 'x' << 16 | LCD_RT_ARROW_CHAR << 8 | P_RUS)); //  MK61 мнемоника П->x
                #endif
              } else if(code >= 0x70 && code < 0x80) { // Кx#0n
                disasm_store_u32_le(buffer, (u32) '0' << 24 | (u32) LCD_NOT_EQU_CHAR << 16 | (u32) 'x' << 8 | 'K');
              } else if(code >= 0x80 && code < 0x90) { // КБПn
                disasm_store_u32_le(buffer, (u32) get_register_symbol(code - 0x50) << 24 | (u32)  P_RUS << 16 | (u32)  B_RUS << 8 | 'K');
              } else if(code >= 0x90 && code < 0xA0) { // Kx>=0n
                disasm_store_u32_le(buffer, (u32) '0' << 24 | (u32) GE << 16 | (u32)  'x' << 8 | 'K');
                 buffer[4] = get_register_symbol(code - 0x60);
              } else if(code >= 0xA0 && code < 0xB0) { // КППn
                disasm_store_u32_le(buffer, (u32) get_register_symbol(code - 0x70) << 24 | (u32)  P_RUS << 16 | (u32)  P_RUS << 8 | 'K');
              } else if(code >= 0xB0 && code < 0xC0) { // КПn
                #ifdef B3_34
                  disasm_store_u32_le(buffer, (u32) ' ' << 24 | (u32) get_register_symbol(code - 0x80) << 16 | (u32)  P_RUS << 8 | 'K');
                #endif
                #ifndef B3_34
                  disasm_store_u32_le(buffer, (u32) P_RUS << 24 | (u32) LCD_RT_ARROW_CHAR << 16 | (u32)  'x' << 8 | (u32) 'K'); //  MK61 мнемоника Kx->П
                   buffer[4] = get_register_symbol(code - 0x80);
                #endif
              } else if(code >= 0xC0 && code < 0xD0) { // Kx<0n
                disasm_store_u32_le(buffer, (u32) '0' << 24 | (u32) '<' << 16 | (u32)  'x' << 8 | 'K');
                 buffer[4] = get_register_symbol(code - 0x90);
              } else if(code >= 0xD0 && code < 0xE0) { // KИПn
                #ifdef B3_34
                  disasm_store_u32_le(buffer, (u32) get_register_symbol(code - 0xA0) << 24 | (u32) P_RUS << 16 | (u32)  I_RUS << 8 | 'K');
                #endif
                #ifndef B3_34
                  disasm_store_u32_le(buffer, (u32) 'x' << 24 | (u32) LCD_RT_ARROW_CHAR << 16 | (u32)  P_RUS << 8 | (u32) 'K'); //  MK61 мнемоника KП->x
                  buffer[4] = get_register_symbol(code - 0xA0);
                #endif
              } else if(code >= 0xE0) { // Kx=0n
                disasm_store_u32_le(buffer, (u32) '0' << 24 | (u32) '=' << 16 | (u32)  'x' << 8 | 'K');
                 buffer[4] = get_register_symbol(code - 0xB0);
              }
          }
          return true;
        }
      }
      return false;
    }

  public:
    constexpr class_disassm_mk61(void)
      : lcd_enable(false), cache_IP_mk61((u8) -1) {}
    inline void  print(void) {
      char disasm[LEN_DISASM_LINE+1];

      MK61DisplayUpdate update(main_lcd());
      if(is_update(&disasm[0])) { // Включен режим отображения дизассемблера МК61
        main_lcd().setCursor(X, Y); main_lcd().print(disasm);
      }
    }

    void  print(const char* text) {
      MK61DisplayUpdate update(main_lcd());
      main_lcd().setCursor(X, Y); main_lcd().print(text);
    }

    void  print_hex(int num) const {
      if(num < 10) main_lcd().print(' ');
      main_lcd().print(num, HEX);
    }

    void  enable(void) {
      dbgln(DISASM, "disassembler ON!");
      lcd_enable = true;
      cache_IP_mk61 = core_61::get_IP() + 1;
      print();
    }

    void  disable(void) {
      dbgln(DISASM, "disassembler OFF!");
      lcd_enable = false;
      MK61DisplayUpdate update(main_lcd());
      main_lcd().setCursor(X, Y); main_lcd().print("      ");
    }

    void  disable(const char* text) {
      dbgln(DISASM, "disassembler OFF!");
      lcd_enable = false;
      MK61DisplayUpdate update(main_lcd());
      main_lcd().setCursor(X, Y); main_lcd().print(text);
    }

    bool  turn_on_off(void) {
      if (lcd_enable)
        disable();
      else
        enable();
      return lcd_enable;
    }
};

#endif

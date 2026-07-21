#ifndef KEY_MNEMONICS_CLASS
#define KEY_MNEMONICS_CLASS

#include "tools.hpp"
#include "cross_hal.h"
#include <string.h>

extern void entry_programm_mode(void);
extern void exit_auto_mode(void);

class key_mnenonic {
  private:
    
    static constexpr u8 X = 10;
    static constexpr u8 Y = 0;
    
    char   mnemo_buffer[8];
    bool   on;
    usize  mnemo_pos;
    i32    last_key;

  public:

    constexpr key_mnenonic(void)
      : mnemo_buffer{}, on(true), mnemo_pos(0), last_key(0) {}

    void    clear_mnemo(void) {
      mnemo_pos = 0;
      memset(mnemo_buffer, 0, sizeof(mnemo_buffer));
    }

    int    next_mnemo_pos(const char* descriptor) {
      if(descriptor == NULL || mnemo_pos >= sizeof(mnemo_buffer) - 1) return 0;
      const i8 control = (i8) descriptor[0];
      usize len = (control < 0) ? ((u8) control & ~STORE_KEY) : (u8) control;
      const usize capacity = sizeof(mnemo_buffer) - 1 - mnemo_pos;
      if(len > capacity) len = capacity;
      if(control < 0) {
        for(usize i=0; i < len; i++) mnemo_buffer[mnemo_pos + i] = descriptor[i+1];
        return mnemo_pos + len;
      } else {
        for(usize i=0; i < len; i++) mnemo_buffer[mnemo_pos + i] = descriptor[i+1];
        return 0;
      }
    }

    void  build_mnemo(i32 keycode) {
      extern  void      edit_extend_program(void);

      if(keycode < 0 || keycode >= 40) {
        clear_mnemo();
        return;
      }

      if(mnemo_pos == 0 || keycode == KEY_K || keycode == KEY_F) { // Первый вход в построение мнемокода нажатой набираемой функции
        clear_mnemo();
        if(keycode == KEY_USER_PRESS && core_61::edit_program) {
          mnemo_pos = 0;
          mnemo_buffer[0] = 'E';
          mnemo_buffer[1] = 'X';
          mnemo_buffer[2] = 'T';
          edit_extend_program();
        } else {
          mnemo_pos = next_mnemo_pos(mnemo_code[keycode]);
        }
      } else {
        switch(last_key) {
          case  KEY_F:
              mnemo_pos = next_mnemo_pos(mnemo_code_F[keycode]);

              // Обратный вызов для смены режима
              if(keycode == KEY_EPOWER) 
                entry_programm_mode();
              else if (keycode == KEY_NEG)
                exit_auto_mode();
            break;
          case  KEY_K:
              mnemo_pos = next_mnemo_pos(mnemo_code_K[keycode]);
            break;
          // П->x, x->П (#N)
          case  KEY_Px:
          case  KEY_xP:
              if(mnemo_pos < sizeof(mnemo_buffer) - 1) mnemo_buffer[mnemo_pos] = mnemo_code_register[keycode];
              mnemo_pos = 0; // Завершить построение
            break;
          // ПП, БП, С/П, В/О, ШГ->, ШГ<- (#NN)
          case  KEY_PP:
          case  KEY_BP:
          case  KEY_RUN:
          case  KEY_RET:
          case  KEY_FRW:
          case  KEY_BKW:
              if(mnemo_pos < sizeof(mnemo_buffer) - 1) mnemo_buffer[mnemo_pos] = mnemo_code_register[keycode];
              if(mnemo_pos > 2) { 
                mnemo_pos = 0; // Завершить построение
              } else {
                mnemo_pos++;
                return;
              }
            break;
          default:
              mnemo_pos = 0;
        } 
      }
      #ifdef DEBUG
        Serial.print("mnemo_pos "); Serial.println(mnemo_pos);
      #endif
      last_key = keycode;
    }

    void  print(i32 keycode) {
      char mnemo[8];
      if(on) {
        build_mnemo(keycode);
        MK61DisplayUpdate update(main_lcd());
        pad_left_8_char(mnemo, mnemo_buffer);
        main_lcd().setCursor(X, Y); main_lcd().print(mnemo);
      }
    }

    void  disable(void) {
      MK61DisplayUpdate update(main_lcd());
      main_lcd().setCursor(X, Y); main_lcd().print("      "); // Очистить поле
      on = false;
    }

    void  enable(void) {
      on = true;
    }
};

#endif

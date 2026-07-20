#include  "library_pmk.hpp"
#include  "Arduino.h"
#include  "rust_types.h"
#include  "mk61emu_core.h"
#include  "lcd_gui.hpp"
#include  "keyboard.h"
#include  "cross_hal.h"
#include  "tools.hpp"
#include  "menu.hpp"
#include  "ledcontrol.h"
#include  "m61_text.hpp"
#include "debug.h"
#include <string.h>

static  i8          selProgram, selGame;

static const u32 Factorial_size       = 1 + 8 + 1;
static const u32 Double_interpol_size = 1 + 105 + 1;
static const u32 Simple_num_size      = 1 +  27 + 1;
static const u32 e_num_size           = 1 + (6 + 6 * 16) + 1;
static const u32 dec2nat              = 1 + (3 * 16 + 2) + 1;
static const u32 powerUR              = 1 + (2 * 16 + 14) + 1;
static const u32 Double_interpol_setup_size = 1 + 40 + 1;
static const u32 dec2nat_setup_size         = 1 + 6 + 1;
static constexpr usize Double_interpol_setup_offset = 0;
static constexpr usize dec2nat_setup_offset = Double_interpol_setup_offset + Double_interpol_setup_size;

static  TPunct programs[COUNT_PROGRAMS] = {
//          0123456789ABCDEF
  {.text = "Factorial      ", .offset = 0},
  {.text = "Double interpol", .offset = Factorial_size, .setup_offset = Double_interpol_setup_offset},
  {.text = "Simple number  ", .offset = Factorial_size + Double_interpol_size},
  {.text = "Compute e-num  ", .offset = Factorial_size + Double_interpol_size + Simple_num_size},
  {.text = "dec  => natural", .offset = Factorial_size + Double_interpol_size + Simple_num_size + e_num_size, .setup_offset = dec2nat_setup_offset},
  {.text = "Power for U & R", .offset = Factorial_size + Double_interpol_size + Simple_num_size + e_num_size + dec2nat}
};

static  u8          mk61_program_setups[] = {
// Настройка двойной интерполяции
  40,
  0x04, 0x00, 0x41,                   // 40 xP1
  0x08, 0x00, 0x00, 0x42,             // 800 xP2
  0x01, 0x00, 0x00, 0x00, 0x43,       // 1000 xP3
  0x02, 0x00, 0x44,                   // 20 xP4
  0x05, 0x00, 0x00, 0x45,             // 500 xP5
  0x06, 0x00, 0x00, 0x46,             // 600 xP6
  0x03, 0x00, 0x00, 0x48,             // 300 xP8
  0x01, 0x00, 0x00, 0x00, 0x49,       // 1000 xP9
  0x08, 0x00, 0x00, 0x4A,             // 800 xPA
  0x02, 0x02, 0x4B,                   // 22 xPB
  0x50,                               // S/P
  0xFF,
// Настройка перевода десятичной дроби в натуральное число
  6,
  0x01, 0x0C, 0x0B, 0x07, 0x49, 0x50, // 1 ВП /-/ 7 xP9; S/P
  0xFF
};

static  u8          mk61_lib[] = {
// Факториал
  8,
//  0     1     2     3     4     5     6     7     8     9     A     B     C     D     E     F
  0x34, 0x40, 0x01, 0x60, 0x12, 0x5D, 0x03, 0x50,
  //0x0C, 0x40, 0x01, 0x60, 0x12, 0x5D, 0x03, 0x50, 0x80,
  0xFF,
// Двойная интерполяция
  9 + 6 * 16,
//  0     1     2     3     4     5     6     7     8     9     A     B     C     D     E     F
  0x00, 0x47, 0x61, 0x0E, 0x64, 0x11, 0x0E, 0x69, 0x0E, 0x68, 0x11, 0x0E, 0x25, 0x25, 0x25, 0x12, 
  0x40, 0x69, 0x0E, 0x6A, 0x11, 0x0E, 0x61, 0x0E, 0x6B, 0x11, 0x0E, 0x25, 0x25, 0x25, 0x12, 0x0E, 
  0x65, 0x12, 0x0E, 0x67, 0x10, 0x47, 0x6A, 0x0E, 0x68, 0x11, 0x0E, 0x61, 0x0E, 0x6B, 0x11, 0x0E,
  0x25, 0x25, 0x25, 0x12, 0x0E, 0x66, 0x12, 0x0E, 0x67, 0x10, 0x47, 0x69, 0x0E, 0x6A, 0x11, 0x0E, 
  0x6B, 0x0E, 0x64, 0x11, 0x0E, 0x25, 0x25, 0x25, 0x12, 0x0E, 0x62, 0x12, 0x0E, 0x67, 0x10, 0x47, 
  0x6A, 0x0E, 0x68, 0x11, 0x0E, 0x6B, 0x0E, 0x64, 0x11, 0x0E, 0x25, 0x25, 0x25, 0x12, 0x0E, 0x63,
  0x12, 0x0E, 0x67, 0x10, 0x47, 0x0E, 0x60, 0x13, 0x50,
  0xFF,
// Простые числа
  27,
//  0     1     2     3     4     5     6     7     8     9     A     B     C     D     E     F
  0x44, 0xD4, 0x64, 0x21, 0x01, 0x10, 0x40, 0x47, 0xD7, 0x14, 0x67, 0x11, 0x5D, 0x18, 0x64, 0x50,
  0x51, 0x00, 0x5E, 0x22, 0x51, 0x01, 0x64, 0x60, 0x13, 0x51, 0x07,
  0xFF,
// Число e
  6 * 16 + 6,
//  0     1     2     3     4     5     6     7     8     9     A     B     C     D     E     F
  0x0D, 0x06, 0x05, 0x0E, 0x07, 0x15, 0x0E, 0x60, 0x53, 0x81, 0x40, 0x61, 0x53, 0x81, 0x41, 0x62, 
  0x53, 0x81, 0x42, 0x63, 0x53, 0x81, 0x43, 0x64, 0x53, 0x81, 0x44, 0x65, 0x53, 0x81, 0x45, 0x66, 
  0x53, 0x81, 0x46, 0x67, 0x53, 0x81, 0x47, 0x68, 0x53, 0x81, 0x48, 0x69, 0x53, 0x81, 0x49, 0x6A, 
  0x53, 0x81, 0x4A, 0x6B, 0x53, 0x81, 0x4B, 0x6C, 0x53, 0x81, 0x4C, 0x6D, 0x53, 0x81, 0x4D, 0x6E, 
  0x53, 0x81, 0x4E, 0x25, 0x25, 0x01, 0x11, 0x5E, 0x04, 0x60, 0x07, 0x15, 0x13, 0x01, 0x10, 0x40, 
  0x50, 0x14, 0x25, 0x10, 0x14, 0x0E, 0x0F, 0x14, 0x13, 0x34, 0x0E, 0x25, 0x14, 0x12, 0x0F, 0x25, 
  0x11, 0x06, 0x15, 0x12, 0x14, 0x52,
  0xFF,
// Десятичная дробь в натуральную
  3*16 + 2,
//  0     1     2     3     4     5     6     7     8     9     A     B     C     D     E     F
  0x40, 0x41, 0x34, 0x43, 0x01, 0x42, 0x46, 0x00, 0x45, 0x61, 0x35, 0x23, 0x41, 0x61, 0x34, 0x63, 
  0x12, 0x62, 0x10, 0x44, 0x61, 0x34, 0x66, 0x12, 0x65, 0x10, 0x47, 0x63, 0x42, 0x64, 0x43, 0x66,
  0x45, 0x67, 0x46, 0x64, 0x67, 0x13, 0x60, 0x11, 0x31, 0x69, 0x11, 0x5C, 0x09, 0x67, 0x64, 0x50,
  0x51, 0x00,
  0xFF,
// Подсчет мощности на резисторе U,R
  2*16 + 14,
  0x08, 0x0A, 0x05, 0x04, 0x04, 0x06, 0x06, 0x06, 0x03, 0x4E, 0x0D, 0x50, 0x22, 0x08, 0x0A, 0x02, 
  0x04, 0x04, 0x07, 0x09, 0x07, 0x07, 0x0C, 0x06, 0x03, 0x4E, 0x0D, 0x50, 0x14, 0x25, 0x13, 0x08, 
  0x0A, 0x07, 0x04, 0x04, 0x06, 0x06, 0x08, 0x04, 0x0C, 0x06, 0x01, 0x4E, 0x14, 0x50,
  0xFF
};

static constexpr usize SETUP_KEY_HOLD_STEPS = 4;
static constexpr usize SETUP_KEY_SETTLE_STEPS = 64;
static constexpr usize SETUP_RUN_STEPS = 50000;

void clear_registers(void) {
  core_61::clear_memory_registers();
}

bool code_needs_expanded(usize offs, const u8* data_stream) {
  const u32 code_len = data_stream[offs];
  return program_needs_expanded_memory(&data_stream[offs + 1], code_len);
}

usize load_code_only(usize offs, const u8* data_stream, bool force_expanded = false) {
  const u32 code_len = data_stream[offs++];
  apply_program_memory_auto(&data_stream[offs], code_len, false, force_expanded);

  const usize code_offs = offs;
  const u32 program_steps = core_61::program_steps();
  for(u32 addr=0; addr < program_steps; addr++) {
      const u8 store_data = (addr < code_len)? data_stream[code_offs + addr] : 0;
      MK61Emu_SetCode(core_61::get_ring_address(addr), store_data);
  }
  return code_offs + code_len;
}

void load_registers(usize offs, u8* data_stream) {
  const u8* pPack_number = &data_stream[offs];
  while(*pPack_number != 0xFF) {
    const u8 RegisterN = *pPack_number++;
    dbghexln(LIB61, "unpack reg: ", RegisterN);
    pPack_number = MK61Emu_UnpackRegster(RegisterN, pPack_number);
    if(pPack_number == NULL) return;
  }
}

void hidden_press_key(sw key) {
  const TMK61_cross_key cross_key = KeyPairs[(u8) key];
  core_61::clear_displayed();

  for(usize i = 0; i < SETUP_KEY_HOLD_STEPS; i++) {
    MK61Emu_SetKeyPress(cross_key.x, cross_key.y);
    core_61::step();
    if(core_61::is_RUN()) break;
  }

  for(usize i = 0; i < SETUP_KEY_SETTLE_STEPS; i++) {
    core_61::step();
    if(core_61::is_RUN() || core_61::is_displayed()) break;
  }

  core_61::clear_displayed();
}

void hidden_return_to_program_start(void) {
  hidden_press_key(sw::F);
  hidden_press_key(sw::NEG);
  hidden_press_key(sw::RET);
}

// F АВТ, В/О, С/П прямо на ядре, минуя буфер клавиатуры (его чистит выход из
// меню/проводника). Общий примитив терминала, m61-сценариев и библиотеки.
void hidden_start_loaded_program(void) {
  hidden_return_to_program_start();
  hidden_press_key(sw::RUN);
}

// Скан-код клавиши прямо на ядро, по той же причине.
bool hidden_press_scan_code(i32 keycode) {
  if(keycode == KEY_DEGREE) {
    MK61Emu_SetAngleUnit(DEGREE);
    return true;
  }
  if(keycode == KEY_GRADE) {
    MK61Emu_SetAngleUnit(GRADE);
    return true;
  }
  if(keycode == KEY_RADIAN) {
    MK61Emu_SetAngleUnit(RADIAN);
    return true;
  }
  if(keycode < 0 || keycode >= 40) return false;

  const TMK61_cross_key cross_key = KeyPairs[keycode];
  if(cross_key.as_u16() == NON.as_u16()) return false;

  hidden_press_key((sw) keycode);
  return true;
}

bool run_loaded_setup_program(void) {
  hidden_start_loaded_program();

  if(!core_61::is_RUN()) {
    return false;
  }

  for(usize i = 0; i < SETUP_RUN_STEPS; i++) {
    core_61::step();
    if(core_61::is_CALC()) {
      core_61::clear_displayed();
      return true;
    }
  }

  return false;
}

bool run_setup_from(usize setup_offs, u8* setup_stream, u8 setup_angle, bool force_expanded) {
  const usize register_offs = load_code_only(setup_offs, setup_stream, force_expanded);
  clear_registers();

  if(setup_angle == RADIAN || setup_angle == GRADE || setup_angle == DEGREE) {
    MK61Emu_SetAngleUnit((AngleUnit) setup_angle);
  }

  if(!run_loaded_setup_program()) return false;

  load_registers(register_offs, setup_stream);
  return true;
}

void  init_library(void) {
  selProgram = 0;
  selGame = 0;
}

typedef bool (*SelectTextProvider)(usize index, char* text, usize capacity);

static int select_texts(usize count, const char* text, usize stride, i8& selector,
                        SelectTextProvider provider = NULL) {
  do {
    const int display_rows = lcd.rows();
    const int visible_count = ((int) count < display_rows) ? (int) count : display_rows;
    const int max_up = (int) count - visible_count;
    const int delta = (selector + 1) - visible_count;
    int up = (delta <= 0)? 0 : delta;
    if(up > max_up) up = max_up;

    {
      MK61DisplayUpdate update(lcd);
      for(int i=0; i < visible_count; i++) {
        lcd.setCursor(0,i);
        const int real_index = i + up;
        if(selector == real_index) {
          lcd.print('>');
        } else {
          lcd.print(' ');
        }
        if(provider != NULL) {
          char generated_text[program_store::NAME_SIZE];
          generated_text[0] = 0;
          if(provider((usize) real_index, generated_text, sizeof(generated_text))) {
            lcd.print(generated_text);
          }
        } else {
          lcd.print(text + (usize) real_index * stride);
        }
      }
      for(int i=visible_count; i < display_rows; i++) {
        lcd.setCursor(0, i);
        for(int x=0; x < (int) lcd_display::COLS; x++) lcd.write((u8) ' ');
      }
    }

    const i32 last_key_code = kbd::get_key_wait();
    switch(last_key_code) {
      case KEY_RIGHT_PRESS:
          if((isize) selector < (isize) (count-1)) selector++;
        break;
      case KEY_LEFT_PRESS:
          if(selector > 0) selector--;
        break;
      case KEY_ESC_PRESS:
        return -1; // отмена
      case KEY_OK_PRESS:
        return selector;
    }

  } while(true);
}

int   select_from(usize COUNT, TPunct* list, i8& selector) {
  return select_texts(COUNT, list[0].text, sizeof(list[0]), selector);
}

void memory_mode_error(void) {
  {
    MK61DisplayUpdate update(lcd);
    lcd.clear();
    library_mk61::print_localized_at(0, 0, "Неверно выбран", "Wrong memory");
    library_mk61::print_localized_at(0, 1, "Режим памяти", "mode selected");
  }
  ErrorReaction();
  delay(1500);
}

void loaded_message(const TPunct& item) {
  if(library_mk61::speed_is_turbo()) {
    led::blink(2, 80, 80);
    return;
  }

  {
    MK61DisplayUpdate update(lcd);
    lcd.clear();
    lcd.setCursor(0, 0);
    lcd.print(item.text);
    library_mk61::print_localized_at(0, 1, "Загружено", "is loaded.");
  }
  delay(1500);
  library_mk61::restore_localized_font();
}

bool  load_from(usize offs, /*TPunct* list,*/ u8* data_stream, bool force_expanded = false) {
  offs = load_code_only(offs, data_stream, force_expanded);
  clear_registers();
  load_registers(offs, data_stream);
  return true;
}

bool load_item(const TPunct& item, u8* code_stream, u8* setup_stream) {
  const bool needs_expanded = code_needs_expanded((usize) item.offset, code_stream);
  if(!library_mk61::program_memory_mode_accepts(needs_expanded)) {
    memory_mode_error();
    return false;
  }
  const bool force_expanded = needs_expanded || library_mk61::program_memory_mode() == ProgramMemoryMode::EXPANDED_112;

  if(item.setup_offset != NO_SETUP) {
    if(run_setup_from((usize) item.setup_offset, setup_stream, item.setup_angle, force_expanded)) {
      load_code_only((usize) item.offset, code_stream, force_expanded);
      hidden_return_to_program_start();
      loaded_message(item);
      return true;
    } else {
      ErrorReaction();
      return false;
    }
  }

  if(!load_from((usize) item.offset, code_stream, force_expanded)) return false;
  hidden_return_to_program_start();
  loaded_message(item);
  return true;
}

int   select_program(void) {
  return select_from(COUNT_PROGRAMS, programs, selProgram);
}

static bool stored_m61_text(usize index, char* text, usize capacity) {
  if(capacity == 0) return false;
  program_store::Entry entry;
  if(!program_store::entry(program_store::ProgramType::MK61, (int) index, entry)) return false;

  memset(text, ' ', capacity - 1);
  text[capacity - 1] = 0;
  usize name_len = 0;
  while(name_len < capacity - 1 && entry.name[name_len] != 0) name_len++;
  memcpy(text, entry.name, name_len);
  return true;
}

int   select_game(void) {
  const usize count = (usize) program_store::count(program_store::ProgramType::MK61);
  if(count == 0) {
    {
      MK61DisplayUpdate update(lcd);
      lcd.clear();
      library_mk61::print_localized_at(0, 0, "Нет M61 файлов", "No M61 files");
    }
    ErrorReaction();
    delay(900);
    return -1;
  }
  if((int) selGame >= (int) count) selGame = (i8) (count - 1);
  return select_texts(count, NULL, 0, selGame, stored_m61_text);
}

bool  load_program(usize nProg_for_load) {
  return load_item(programs[nProg_for_load], mk61_lib, mk61_program_setups);
}

bool  load_game(usize nGame_for_load) {
  program_store::Entry entry;
  if(!program_store::entry(program_store::ProgramType::MK61, (int) nGame_for_load, entry)) return false;
  return m61_text::load_program(entry.id);
}

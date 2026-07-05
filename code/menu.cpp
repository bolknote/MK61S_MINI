#include <string.h>
#include "menu.hpp"
#include "cross_hal.h"
#include "lcd_ru.hpp"

extern MK61Display lcd;
extern t_time_ms runtime_ms;
extern void reset_ext_program_state(void);
extern isize mk61_quants_reload;

namespace library_mk61 {

static constexpr int MENU_DFU      = 0;
static constexpr int MENU_SOUND    = 1;
static constexpr int MENU_SPEED    = 2;
static constexpr int MENU_MEMORY   = 3;
static constexpr int MENU_LANGUAGE = 4;
static constexpr int MENU_LIBRARY  = 5;
static constexpr int MENU_GAMES    = 6;
static constexpr int MENU_RESET    = 7;
static constexpr int MENU_ERASE    = 8;
static constexpr int MENU_INFO     = 9;
static constexpr int MENU_HW       = 10;

static bool sound_enabled = true;
static SpeedMode speed_mode_state = SpeedMode::MAXIMUM;
static bool russian_language = false;
static bool expanded_program = false;
static ProgramMemoryMode memory_mode = ProgramMemoryMode::AUTO;

static void set_speed_mode_state(SpeedMode mode) {
  speed_mode_state = mode;
  ::mk61_quants_reload = (mode == SpeedMode::CLASSIC) ? cfg::CLASSIC_MK61_QUANTS : 1;
}

static void append_text(char*& out, char* end, const char* text) {
  while(*text != 0 && out < end) *out++ = *text++;
}

static void append_until_space(char*& out, char* end, const char* text) {
  while(*text != 0 && *text != ' ' && out < end) *out++ = *text++;
}

static void build_ru_memory_text(char* out, usize size) {
  char* cursor = out;
  char* end = out + size - 1;
  const char* ram = strstr(mem_text, "RAM:");
  const char* rom = strstr(mem_text, "ROM:");

  if(ram == NULL || rom == NULL) {
    append_text(cursor, end, mem_text);
    *cursor = 0;
    return;
  }

  append_text(cursor, end, "ОЗУ:");
  append_until_space(cursor, end, ram + 4);
  append_text(cursor, end, " ПЗУ:");
  append_until_space(cursor, end, rom + 4);
  *cursor = 0;
}

bool  HardwareInfo(void) {
  lcd.clear();
  if(language_is_ru()) {
    char chip_line[24] = "ЧИП:";
    char memory_line[32];
    char* cursor = &chip_line[sizeof("ЧИП:") - 1];
    append_text(cursor, chip_line + sizeof(chip_line) - 1, chip_name);
    *cursor = 0;
    build_ru_memory_text(memory_line, sizeof(memory_line));
    lcd_ru::print_lines(chip_line, memory_line);
  } else {
    lcd.setCursor(0, 0);
    lcd.print("Chip:");
    lcd.print(chip_name);
    lcd.setCursor(0,1);
    lcd.print(mem_text);
  }
  kbd::get_key_wait();
  return action::MENU_BACK;
}

bool  InfoData(void) {
  lcd.clear(); 
  lcd.setCursor(0,0); 
  lcd.print(text("cnt:", "N:")); lcd.print(read_counter_switch());
  lcd.print(text(" sw:", " P:")); lcd.print((u8) read_grade_switch());
  if(flash_is_ok) lcd.print(" W25"); 
  lcd.setCursor(0,1); 
  lcd.print(text("run ", "T:")); lcd.print(runtime_ms); lcd.print(" ms");
  kbd::get_key_wait();
  return false;
}

const t_punct DFU_mode_punct      = {.size = 15, .action = (menu_action) &DFU_enable,           .text = "DFU mode enable"};
const t_punct LIB_61_punct        = {.size = 12, .action = &mk61_library_select,                .text = "MK61 library"};
const t_punct GAME_61_punct       = {.size = 10, .action = &mk61_games_select,                  .text = "MK61 Games"};
const t_punct RESET_punct         = {.size = 12, .action = (menu_action) &NVIC_SystemReset,     .text = "Reset device"};
const t_punct ERASE_punct         = {.size = 12, .action = (menu_action) &EraseFlash,           .text = "Erase FLASH!"};
const t_punct SOUND_ON_punct      = {.size = 15, .action = (menu_action) &TurnSound,            .text = "Sound ON       "};
const t_punct SOUND_OFF_punct     = {.size = 15, .action = (menu_action) &TurnSound,            .text = "Sound OFF      "};
const t_punct SPEED_LOW_punct     = {.size = 15, .action = (menu_action) &TurnSpeed,            .text = "Speed CLASSIC  "};
const t_punct SPEED_HIGH_punct    = {.size = 15, .action = (menu_action) &TurnSpeed,            .text = "Speed MAXIMUM  "};
const t_punct SPEED_TURBO_punct   = {.size = 15, .action = (menu_action) &TurnSpeed,            .text = "Speed TURBO    "};
const t_punct MEMORY_105_punct    = {.size = 15, .action = (menu_action) &TurnProgramMemory,    .text = "Memory 105     "};
const t_punct MEMORY_112_punct    = {.size = 15, .action = (menu_action) &TurnProgramMemory,    .text = "Memory 112     "};
const t_punct MEMORY_AUTO_punct   = {.size = 15, .action = (menu_action) &TurnProgramMemory,    .text = "Memory AUTO    "};
const t_punct LANGUAGE_EN_punct   = {.size = 15, .action = (menu_action) &TurnLanguage,         .text = "Language EN    "};
const t_punct LANGUAGE_RU_punct   = {.size = 15, .action = (menu_action) &TurnLanguage,         .text = "ЯЗЫК РУС"};
const t_punct FLASH_punct         = {.size = 11, .action = (menu_action) &InfoData,             .text = "Information"};
const t_punct HARDWARE_punct      = {.size = 8,  .action = (menu_action) &HardwareInfo,         .text = "Hardware"};

const t_punct RU_DFU_mode_punct   = {.size = 15, .action = (menu_action) &DFU_enable,           .text = "DFU ПРОШИВКА"};
const t_punct RU_LIB_61_punct     = {.size = 15, .action = &mk61_library_select,                .text = "БИБЛИОТЕКА"};
const t_punct RU_GAME_61_punct    = {.size = 15, .action = &mk61_games_select,                  .text = "ИГРЫ MK61"};
const t_punct RU_RESET_punct      = {.size = 15, .action = (menu_action) &NVIC_SystemReset,     .text = "СБРОС"};
const t_punct RU_ERASE_punct      = {.size = 15, .action = (menu_action) &EraseFlash,           .text = "СТЕРЕТЬ FLASH"};
const t_punct RU_SOUND_ON_punct   = {.size = 15, .action = (menu_action) &TurnSound,            .text = "ЗВУК ВКЛ"};
const t_punct RU_SOUND_OFF_punct  = {.size = 15, .action = (menu_action) &TurnSound,            .text = "ЗВУК ВЫКЛ"};
const t_punct RU_SPEED_LOW_punct  = {.size = 15, .action = (menu_action) &TurnSpeed,            .text = "СКОРОСТЬ НОРМА"};
const t_punct RU_SPEED_HIGH_punct = {.size = 15, .action = (menu_action) &TurnSpeed,            .text = "СКОРОСТЬ МАКС"};
const t_punct RU_SPEED_TURBO_punct= {.size = 15, .action = (menu_action) &TurnSpeed,            .text = "СКОРОСТЬ ТУРБО"};
const t_punct RU_MEMORY_105_punct = {.size = 15, .action = (menu_action) &TurnProgramMemory,    .text = "ПАМЯТЬ 105"};
const t_punct RU_MEMORY_112_punct = {.size = 15, .action = (menu_action) &TurnProgramMemory,    .text = "ПАМЯТЬ 112"};
const t_punct RU_MEMORY_AUTO_punct= {.size = 15, .action = (menu_action) &TurnProgramMemory,    .text = "ПАМЯТЬ АВТО"};
const t_punct RU_FLASH_punct      = {.size = 15, .action = (menu_action) &InfoData,             .text = "ИНФОРМАЦИЯ"};
const t_punct RU_HARDWARE_punct   = {.size = 15, .action = (menu_action) &HardwareInfo,         .text = "ПЛАТА"};

t_punct* MENU[MENU_PUNCT] = {
      (t_punct*) &DFU_mode_punct,
      (t_punct*) &SOUND_ON_punct,
      (t_punct*) &SPEED_HIGH_punct,
      (t_punct*) &MEMORY_AUTO_punct,
      (t_punct*) &LANGUAGE_EN_punct,
      (t_punct*) &LIB_61_punct,
      (t_punct*) &GAME_61_punct,
      (t_punct*) &RESET_punct,
      (t_punct*) &ERASE_punct,
      (t_punct*) &FLASH_punct,
      (t_punct*) &HARDWARE_punct
};

bool  sound_is_on(void) {
  return sound_enabled;
}

void  set_sound_state(bool enable) {
  sound_enabled = enable;
}

bool  language_is_ru(void) {
  return russian_language;
}

void  set_language_state(bool enable) {
  russian_language = enable;
}

bool  expanded_program_is_on(void) {
  return expanded_program;
}

void  set_program_memory_state(bool enable) {
  expanded_program = enable;
  core_61::set_expanded_program_mode(enable);
}

ProgramMemoryMode program_memory_mode(void) {
  return memory_mode;
}

bool program_memory_mode_accepts(bool needs_expanded) {
  if(memory_mode == ProgramMemoryMode::AUTO) return true;
  return needs_expanded == (memory_mode == ProgramMemoryMode::EXPANDED_112);
}

void set_program_memory_mode(ProgramMemoryMode mode) {
  memory_mode = mode;
  if(memory_mode != ProgramMemoryMode::AUTO) {
    set_program_memory_state(memory_mode == ProgramMemoryMode::EXPANDED_112);
  }
}

static t_punct* memory_punct(void) {
  if(memory_mode == ProgramMemoryMode::AUTO) {
    return (t_punct*) (russian_language ? &RU_MEMORY_AUTO_punct : &MEMORY_AUTO_punct);
  }
  if(memory_mode == ProgramMemoryMode::EXPANDED_112) {
    return (t_punct*) (russian_language ? &RU_MEMORY_112_punct : &MEMORY_112_punct);
  }
  return (t_punct*) (russian_language ? &RU_MEMORY_105_punct : &MEMORY_105_punct);
}

static t_punct* speed_punct(void) {
  switch(speed_mode_state) {
    case SpeedMode::CLASSIC:
      return (t_punct*) (russian_language ? &RU_SPEED_LOW_punct : &SPEED_LOW_punct);
    case SpeedMode::TURBO:
      return (t_punct*) (russian_language ? &RU_SPEED_TURBO_punct : &SPEED_TURBO_punct);
    case SpeedMode::MAXIMUM:
    default:
      return (t_punct*) (russian_language ? &RU_SPEED_HIGH_punct : &SPEED_HIGH_punct);
  }
}

void refresh_menu_text(void) {
  MENU[MENU_DFU]      = (t_punct*) (russian_language ? &RU_DFU_mode_punct : &DFU_mode_punct);
  MENU[MENU_SOUND]    = (t_punct*) (russian_language ? (sound_enabled ? &RU_SOUND_ON_punct : &RU_SOUND_OFF_punct) : (sound_enabled ? &SOUND_ON_punct : &SOUND_OFF_punct));
  MENU[MENU_SPEED]    = speed_punct();
  MENU[MENU_MEMORY]   = memory_punct();
  MENU[MENU_LANGUAGE] = (t_punct*) (russian_language ? &LANGUAGE_RU_punct : &LANGUAGE_EN_punct);
  MENU[MENU_LIBRARY]  = (t_punct*) (russian_language ? &RU_LIB_61_punct : &LIB_61_punct);
  MENU[MENU_GAMES]    = (t_punct*) (russian_language ? &RU_GAME_61_punct : &GAME_61_punct);
  MENU[MENU_RESET]    = (t_punct*) (russian_language ? &RU_RESET_punct : &RESET_punct);
  MENU[MENU_ERASE]    = (t_punct*) (russian_language ? &RU_ERASE_punct : &ERASE_punct);
  MENU[MENU_INFO]     = (t_punct*) (russian_language ? &RU_FLASH_punct : &FLASH_punct);
  MENU[MENU_HW]       = (t_punct*) (russian_language ? &RU_HARDWARE_punct : &HARDWARE_punct);
}

void  store_settings_state(void) {
  SettingsFlags flags;
  flags.bits.sound_on = sound_enabled;
  flags.bits.language_ru = russian_language;
  flags.bits.expanded_program = expanded_program;
  flags.bits.program_memory_auto = (memory_mode == ProgramMemoryMode::AUTO);
  flags.bits.speed_mode = (u8) speed_mode_state;
  store_settings_flags(flags);
}

void  load_settings_state(void) {
  const SettingsFlags flags = read_settings_flags();
  set_sound_state(flags.bits.sound_on != 0);
  set_language_state(flags.bits.language_ru != 0);
  set_program_memory_state(flags.bits.expanded_program != 0);
  memory_mode = (flags.bits.program_memory_auto != 0)
    ? ProgramMemoryMode::AUTO
    : (expanded_program ? ProgramMemoryMode::EXPANDED_112 : ProgramMemoryMode::CLASSIC_105);
  const u8 stored_speed = flags.bits.speed_mode;
  set_speed_mode_state((stored_speed <= (u8) SpeedMode::TURBO) ? (SpeedMode) stored_speed : SpeedMode::MAXIMUM);
  refresh_menu_text();
}

SpeedMode speed_mode(void) {
  return speed_mode_state;
}

bool  speed_is_max(void) {
  return speed_mode_state != SpeedMode::CLASSIC;
}

bool  speed_is_turbo(void) {
  return speed_mode_state == SpeedMode::TURBO;
}

} // namespace library_mk61

bool   TurnSpeed(void) {
  switch(library_mk61::speed_mode()) {
    case SpeedMode::MAXIMUM:
      library_mk61::set_speed_mode_state(SpeedMode::CLASSIC);
      break;
    case SpeedMode::CLASSIC:
      library_mk61::set_speed_mode_state(SpeedMode::TURBO);
      break;
    case SpeedMode::TURBO:
      library_mk61::set_speed_mode_state(SpeedMode::MAXIMUM);
      break;
  }
  library_mk61::refresh_menu_text();
  library_mk61::store_settings_state();

  return action::MENU_BACK;
}

bool   TurnSound(void) {
  if(library_mk61::sound_is_on()) {
    library_mk61::set_sound_state(false);
  } else {
    library_mk61::set_sound_state(true);
  }
  library_mk61::refresh_menu_text();
  library_mk61::store_settings_state();

  return action::MENU_BACK;
}

bool   TurnLanguage(void) {
  library_mk61::set_language_state(!library_mk61::language_is_ru());
  library_mk61::refresh_menu_text();
  library_mk61::store_settings_state();

  return action::MENU_BACK;
}

bool   TurnProgramMemory(void) {
  const bool was_expanded = library_mk61::expanded_program_is_on();

  switch(library_mk61::program_memory_mode()) {
    case ProgramMemoryMode::CLASSIC_105:
      library_mk61::set_program_memory_mode(ProgramMemoryMode::EXPANDED_112);
      break;
    case ProgramMemoryMode::EXPANDED_112:
      library_mk61::set_program_memory_mode(ProgramMemoryMode::AUTO);
      break;
    case ProgramMemoryMode::AUTO:
      library_mk61::set_program_memory_mode(ProgramMemoryMode::CLASSIC_105);
      break;
  }

  library_mk61::refresh_menu_text();
  library_mk61::store_settings_state();

  if(was_expanded != library_mk61::expanded_program_is_on()) {
    reset_ext_program_state();
    core_61::enable();
  }

  return action::MENU_BACK;
}

bool  mk61_library_select(void) {
  const int n = select_program();
  if(n < 0) return action::MENU_BACK;

  if(!load_program(n)) return action::MENU_BACK;
  return action::MENU_EXIT;
}

bool  mk61_games_select(void) {
  const int n = select_game();
  if(n < 0) return action::MENU_BACK;

  if(!load_game(n)) return action::MENU_BACK;
  return action::MENU_EXIT;
}

void class_menu::draw(void) {
  const int visible_count = (MENU_PUNCT_COUNT < SIZE_MENU_WINDOW) ? MENU_PUNCT_COUNT : SIZE_MENU_WINDOW;
  const int max_up = MENU_PUNCT_COUNT - visible_count;
  const int delta = (active_punct + 1) - visible_count;
  int up = (delta <= 0)? 0 : delta;
  if(up > max_up) up = max_up;

  if(library_mk61::language_is_ru()) {
    if(visible_count == 2) {
      const int top_index = up;
      const int bottom_index = up + 1;
      lcd_ru::print_menu_window(
        (active_punct == top_index)? '>' : ' ', puncts[top_index]->text,
        (active_punct == bottom_index)? '>' : ' ', puncts[bottom_index]->text
      );
    } else {
      for(int i=0; i < visible_count; i++) {
        const int real_index = i + up;
        lcd_ru::print_menu_line(i, (active_punct == real_index)? '>' : ' ', puncts[real_index]->text);
      }
    }
    for(int i=visible_count; i < SIZE_MENU_WINDOW; i++) {
      lcd.setCursor(0, i);
      for(int x=0; x < lcd_display::COLS; x++) lcd.write((u8) ' ');
    }
    previous_up = up;
    return;
  }

  for(int i=0; i < visible_count; i++) {
    lcd.setCursor(0,  i);
    const int real_index = i + up;
    const int previous_real_index = i + previous_up;

    // формируем постоянную часть пункта меню
    lcd.print( (active_punct == real_index)?  '>'  :  ' ' );
    lcd.print(puncts[real_index]->text);

    int previous_punct_size = puncts[previous_real_index]->size;
    const int size = puncts[real_index]->size;
    // формируем переменную часть пункта меню
    while(previous_punct_size-- > size) {
      lcd.print(' ');
    }
  }
  for(int i=visible_count; i < SIZE_MENU_WINDOW; i++) {
    lcd.setCursor(0, i);
    for(int x=0; x < lcd_display::COLS; x++) lcd.write((u8) ' ');
  }
  previous_up = up;
}

void class_menu::select(void) {
  lcd.clear();
  do{
    draw();
    const i32 last_key_code = kbd::get_key_wait();
    switch(last_key_code) {
      case KEY_RIGHT_PRESS:
              if(active_punct < (MENU_PUNCT_COUNT-1)) active_punct++;
        break;
      case KEY_LEFT_PRESS:
              if(active_punct > 0) active_punct--;
        break;
      case KEY_OK_PRESS:
            dbgln(MENU, "Select menu: '", puncts[active_punct]->text, "\'");
            lcd_ru::restore_default_font();
            if(puncts[active_punct]->action() == action::MENU_EXIT) {
              return;
            } else {
              lcd.clear();
              break;
            }
      case KEY_ESC_PRESS:
            lcd_ru::restore_default_font();
            return; // отмена
    }
  } while(true);
}

i32 class_menu::select(i32 key) {
  lcd.clear();
  dbgln(MENU, "select entry");

    switch(key) {
      case KEY_RIGHT_PRESS:
              if(active_punct < (MENU_PUNCT_COUNT-1)) active_punct++;
        break;
      case KEY_LEFT_PRESS:
              if(active_punct > 0) active_punct--;
        break;
      case KEY_OK_PRESS:
            dbgln(MENU, "Select menu: '", puncts[active_punct]->text, "\'");
            lcd_ru::restore_default_font();
            if(puncts[active_punct]->action() == action::MENU_EXIT) {
              return -1;
            } else {
              lcd.clear();
              break;
            }
      case KEY_ESC_PRESS:
            lcd_ru::restore_default_font();
            return -1; // отмена
    }
  
  draw();
  dbgln(MENU, "select exit");
  return 0;
}

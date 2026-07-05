#include "LiquidCrystal.h"
#include "menu.hpp"    
#include "cross_hal.h"

extern LiquidCrystal lcd;
extern t_time_ms runtime_ms;
//extern isize mk61_quants_reload;

namespace library_mk61 {

static constexpr int MENU_DFU      = 0;
static constexpr int MENU_SOUND    = 1;
static constexpr int MENU_SPEED    = 2;
static constexpr int MENU_LANGUAGE = 3;
static constexpr int MENU_LIBRARY  = 4;
static constexpr int MENU_GAMES    = 5;
static constexpr int MENU_RESET    = 6;
static constexpr int MENU_ERASE    = 7;
static constexpr int MENU_INFO     = 8;
static constexpr int MENU_HW       = 9;

static bool sound_enabled = true;
static bool speed_max_enabled = true;
static bool russian_language = false;

bool  HardwareInfo(void) {
  lcd.clear(); 
  lcd.setCursor(0,0); lcd.print(text("Chip:", "\321\004\001:")); lcd.print(chip_name);
  lcd.setCursor(0,1); lcd.print(mem_text);
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
const t_punct LANGUAGE_EN_punct   = {.size = 15, .action = (menu_action) &TurnLanguage,         .text = "Language EN    "};
const t_punct LANGUAGE_RU_punct   = {.size = 15, .action = (menu_action) &TurnLanguage,         .text = "Language RU    "};
const t_punct FLASH_punct         = {.size = 11, .action = (menu_action) &InfoData,             .text = "Information"};
const t_punct HARDWARE_punct      = {.size = 8,  .action = (menu_action) &HardwareInfo,         .text = "Hardware"};

const t_punct RU_DFU_mode_punct   = {.size = 15, .action = (menu_action) &DFU_enable,           .text = "DFU FLASH      "};
const t_punct RU_LIB_61_punct     = {.size = 15, .action = &mk61_library_select,                .text = "\001P\005 MK61      "};
const t_punct RU_GAME_61_punct    = {.size = 15, .action = &mk61_games_select,                  .text = "MK61 \004\005P      "};
const t_punct RU_RESET_punct      = {.size = 15, .action = (menu_action) &NVIC_SystemReset,     .text = "C\002POC         "};
const t_punct RU_ERASE_punct      = {.size = 15, .action = (menu_action) &EraseFlash,           .text = "CTEP FLASH    "};
const t_punct RU_SOUND_ON_punct   = {.size = 15, .action = (menu_action) &TurnSound,            .text = "\002\004\001 \003" "A        "};
const t_punct RU_SOUND_OFF_punct  = {.size = 15, .action = (menu_action) &TurnSound,            .text = "\002\004\001 HET       "};
const t_punct RU_SPEED_LOW_punct  = {.size = 15, .action = (menu_action) &TurnSpeed,            .text = "CKOP HOPMA    "};
const t_punct RU_SPEED_HIGH_punct = {.size = 15, .action = (menu_action) &TurnSpeed,            .text = "CKOP MAX      "};
const t_punct RU_FLASH_punct      = {.size = 15, .action = (menu_action) &InfoData,             .text = "INFO          "};
const t_punct RU_HARDWARE_punct   = {.size = 15, .action = (menu_action) &HardwareInfo,         .text = "\321\004\001           "};

t_punct* MENU[MENU_PUNCT] = {
      (t_punct*) &DFU_mode_punct,
      (t_punct*) &SOUND_ON_punct,
      (t_punct*) &SPEED_HIGH_punct,
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

void refresh_menu_text(void) {
  MENU[MENU_DFU]      = (t_punct*) (russian_language ? &RU_DFU_mode_punct : &DFU_mode_punct);
  MENU[MENU_SOUND]    = (t_punct*) (russian_language ? (sound_enabled ? &RU_SOUND_ON_punct : &RU_SOUND_OFF_punct) : (sound_enabled ? &SOUND_ON_punct : &SOUND_OFF_punct));
  MENU[MENU_SPEED]    = (t_punct*) (russian_language ? (speed_max_enabled ? &RU_SPEED_HIGH_punct : &RU_SPEED_LOW_punct) : (speed_max_enabled ? &SPEED_HIGH_punct : &SPEED_LOW_punct));
  MENU[MENU_LANGUAGE] = (t_punct*) (russian_language ? &LANGUAGE_RU_punct : &LANGUAGE_EN_punct);
  MENU[MENU_LIBRARY]  = (t_punct*) (russian_language ? &RU_LIB_61_punct : &LIB_61_punct);
  MENU[MENU_GAMES]    = (t_punct*) (russian_language ? &RU_GAME_61_punct : &GAME_61_punct);
  MENU[MENU_RESET]    = (t_punct*) (russian_language ? &RU_RESET_punct : &RESET_punct);
  MENU[MENU_ERASE]    = (t_punct*) (russian_language ? &RU_ERASE_punct : &ERASE_punct);
  MENU[MENU_INFO]     = (t_punct*) (russian_language ? &RU_FLASH_punct : &FLASH_punct);
  MENU[MENU_HW]       = (t_punct*) (russian_language ? &RU_HARDWARE_punct : &HARDWARE_punct);
}

void  store_settings_state(void) {
  store_settings_flags((sound_enabled ? SETTINGS_SOUND_ON : 0) | (russian_language ? SETTINGS_LANGUAGE_RU : 0));
}

void  load_settings_state(void) {
  const u8 flags = read_settings_flags();
  set_sound_state((flags & SETTINGS_SOUND_ON) != 0);
  set_language_state((flags & SETTINGS_LANGUAGE_RU) != 0);
  refresh_menu_text();
}

bool  speed_is_max(void) {
  return speed_max_enabled;
}

} // namespace library_mk61

bool   TurnSpeed(void) {
  extern isize mk61_quants_reload;

  if(library_mk61::speed_is_max()) {
    library_mk61::speed_max_enabled = false;
    mk61_quants_reload = cfg::CLASSIC_MK61_QUANTS;
  } else {
    library_mk61::speed_max_enabled = true;
    mk61_quants_reload = 1;
  }
  library_mk61::refresh_menu_text();

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

bool  mk61_library_select(void) {
  const int n = select_program();
  if(n < 0) return action::MENU_BACK;

  load_program(n);
  return action::MENU_EXIT;
}

bool  mk61_games_select(void) {
  const int n = select_game();
  if(n < 0) return action::MENU_BACK;

  load_game(n);
  return action::MENU_EXIT;
}

void class_menu::draw(void) {
  const int delta = (active_punct + 1) - SIZE_MENU_WINDOW;
  const int up = (delta <= 0)? 0 : delta;

  for(int i=0; i < SIZE_MENU_WINDOW; i++) {
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
            if(puncts[active_punct]->action() == action::MENU_EXIT) {
              return; 
            } else { 
              lcd.clear();
              break;
            }
      case KEY_ESC_PRESS:
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
            if(puncts[active_punct]->action() == action::MENU_EXIT) {
              return -1; 
            } else { 
              lcd.clear();
              break;
            }
      case KEY_ESC_PRESS:
            return -1; // отмена
    }
  
  draw();
  dbgln(MENU, "select exit");
  return 0;
}

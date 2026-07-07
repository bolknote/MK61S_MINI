#ifndef MENU_CLASS
#define MENU_CLASS

#include  "keyboard.h"
#include  "tools.hpp"
#include  "library_pmk.hpp"
#include  "lcd_ru.hpp"

namespace action {
  static constexpr bool MENU_EXIT = true;
  static constexpr bool MENU_BACK = false;
}

typedef bool (*menu_action)(void);  // возвращает необходимость покинуть главное меню 

enum class ProgramMemoryMode : u8 {
  CLASSIC_105,
  EXPANDED_112,
  AUTO
};

enum class SpeedMode : u8 {
  CLASSIC,
  MAXIMUM,
  TURBO
};

struct  t_punct {
    u8            size;
    menu_action   action;
    char          text[];
};

extern bool mk61_library_select(void);
extern bool mk61_games_select(void);
extern bool settings_select(void);
extern bool TurnSoundVolume(void);
extern bool TurnSpeed(void);
extern bool TurnLanguage(void);
extern bool TurnProgramMemory(void);
extern bool TurnUsbDisk(void);
extern bool TurnIdleSignal(void);
extern bool TurnDisplayRows(void);
extern bool ResetDevice(void);

namespace library_mk61 {
  extern  const int       COUNT_PUNCTS;
  extern  t_punct*        MENU[];

  extern  bool  sound_is_on(void);
  extern  u8    sound_volume(void);
  extern  void  set_sound_volume(u8 volume);
  extern  bool  language_is_ru(void);
  extern  bool  expanded_program_is_on(void);
  extern  bool  usb_disk_is_on(void);
  extern  bool  idle_signal_is_on(void);
  extern  u8    display_rows(void);
  extern  ProgramMemoryMode program_memory_mode(void);
  extern  bool  program_memory_mode_accepts(bool needs_expanded);
  extern  void  set_program_memory_state(bool enable);
  extern  void  set_program_memory_mode(ProgramMemoryMode mode);
  extern  void  set_usb_disk_state(bool enable);
  extern  void  set_idle_signal_state(bool enable);
  extern  void  set_display_rows(u8 rows);
  extern  void  refresh_menu_text(void);
  extern  void  store_settings_state(void);
  extern  void  defer_settings_state_save(void);
  extern  void  flush_settings_state(void);
  extern  void  poll_settings_state_save(void);
  extern  void  load_settings_state(void);
  extern  SpeedMode speed_mode(void);
  extern  bool  speed_is_max(void);
  extern  bool  speed_is_turbo(void);

  inline const char* text(const char* en, const char* ru) {
    return language_is_ru() ? ru : en;
  }

  inline void print_localized_at(u8 x, u8 y, const char* ru, const char* en, u8 width = lcd_ru::LCD_WIDTH) {
    if(language_is_ru()) {
      lcd_ru::print_at(x, y, ru, width);
      return;
    }

    lcd.setCursor(x, y);
    u8 used = 0;
    while(en[used] != 0 && used < width) lcd.write((u8) en[used++]);
    while(used++ < width) lcd.write((u8) ' ');
  }

  inline void restore_localized_font(void) {
    if(language_is_ru()) lcd_ru::restore_default_font();
  }
}

class class_menu {
  private:
    int MENU_PUNCT_COUNT;
    u8 active_punct;
    u8 previous_up;
    t_punct** puncts;

    void draw(void);
    i32 wait_key(void);
    bool handle_settings_adjustment(i32 key);

  public:
    class_menu(t_punct** punts_of_menu, int count_of_puncts) : MENU_PUNCT_COUNT(count_of_puncts), active_punct(0), previous_up(0), puncts(punts_of_menu) {};
    bool select(void);
    i32  select(i32 key);
};

#endif

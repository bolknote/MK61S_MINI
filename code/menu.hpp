#ifndef MENU_CLASS
#define MENU_CLASS

#include  "keyboard.h"
#include  "tools.hpp"
#include  "library_pmk.hpp"

namespace action {
  static constexpr bool MENU_EXIT = true;
  static constexpr bool MENU_BACK = false;
}

typedef bool (*menu_action)(void);  // возвращает необходимость покинуть главное меню 

static constexpr int MENU_PUNCT = 11;

struct  t_punct {
    u8            size;
    menu_action   action;
    char          text[];
};

extern bool mk61_library_select(void);
extern bool mk61_games_select(void);
extern bool TurnSound(void);
extern bool TurnSpeed(void);
extern bool TurnLanguage(void);
extern bool TurnProgramMemory(void);

namespace library_mk61 {
  const   int             COUNT_PUNCTS = MENU_PUNCT;
  extern  t_punct*        MENU[MENU_PUNCT];

  extern  bool  sound_is_on(void);
  extern  bool  language_is_ru(void);
  extern  bool  expanded_program_is_on(void);
  extern  void  load_settings_state(void);
  extern  bool  speed_is_max(void);

  inline const char* text(const char* en, const char* ru) {
    return language_is_ru() ? ru : en;
  }
}

class class_menu {
  private:
    static constexpr int SIZE_MENU_WINDOW = 2;
    int MENU_PUNCT_COUNT;
    u8 active_punct;
    u8 previous_up;
    t_punct** puncts;

    void draw(void);

  public:
    class_menu(t_punct** punts_of_menu, int count_of_puncts) : MENU_PUNCT_COUNT(count_of_puncts), active_punct(0), previous_up(0), puncts(punts_of_menu) {};
    void select(void);
    i32  select(i32 key);
};

#endif

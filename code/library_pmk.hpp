#ifndef LIBRARY_PMK
#define LIBRARY_PMK

#include "keyboard.h"
#include "rust_types.h"

enum class sw : u32;

static  constexpr usize    COUNT_PROGRAMS = 6;
static  constexpr usize    COUNT_GAMES    = 6;
static  constexpr int      NO_SETUP       = -1;
struct  TPunct {
  char  text[16];
  int   offset;
  int   setup_offset = NO_SETUP;
  u8    setup_angle = 0;
};

int  select_program(void);
int  select_game(void);
bool load_program(usize nProg_for_load);
bool load_game(usize nGame_for_load);
void init_library(void);
void hidden_press_key(sw key);

#endif

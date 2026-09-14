#include "calculator_control.hpp"

#include "cross_hal.h"
#include "keyboard.h"
#include "mk61emu_core.h"

static constexpr usize HIDDEN_KEY_HOLD_STEPS = 4;
static constexpr usize HIDDEN_KEY_SETTLE_STEPS = 64;

void hidden_press_key(sw key) {
  const TMK61_cross_key cross_key = KeyPairs[(u8) key];
  core_61::clear_displayed();

  for(usize i = 0; i < HIDDEN_KEY_HOLD_STEPS; i++) {
    MK61Emu_SetKeyPress(cross_key.x, cross_key.y);
    core_61::step();
    if(core_61::is_RUN()) break;
  }

  for(usize i = 0; i < HIDDEN_KEY_SETTLE_STEPS; i++) {
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

void hidden_start_loaded_program(void) {
  hidden_return_to_program_start();
  hidden_press_key(sw::RUN);
}

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

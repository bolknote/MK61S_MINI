#include "run_measurement.hpp"

namespace run_measurement {

static u32 started_at_ms;
static State current_state = State::IDLE;

void arm_next(void) {
  current_state = State::ARMED;
}

void cancel(void) {
  current_state = State::IDLE;
  started_at_ms = 0;
}

State state(void) {
  return current_state;
}

bool program_started(u32 now_ms) {
  if(current_state != State::ARMED) return false;
  started_at_ms = now_ms;
  current_state = State::RUNNING;
  return true;
}

bool program_stopped(u32 now_ms, u32& elapsed_ms) {
  if(current_state != State::RUNNING) return false;
  elapsed_ms = now_ms - started_at_ms;
  cancel();
  return true;
}

} // namespace run_measurement

#ifndef RUN_MEASUREMENT_HOST_TEST

#include "keyboard.h"
#include "lcd_gui.hpp"
#include "menu.hpp"

#include <stdio.h>

extern void lcd_std_display_redraw(void);

namespace run_measurement {

void show_and_wait(u32 elapsed_ms) {
  {
    MK61DisplayTextScope text_scope(main_lcd());
    char line_ru[24];
    char line_en[24];
    snprintf(line_ru, sizeof(line_ru), "ВР:%lu МС",
             (unsigned long) elapsed_ms);
    snprintf(line_en, sizeof(line_en), "run %lu ms",
             (unsigned long) elapsed_ms);
    {
      MK61DisplayUpdate update(main_lcd());
      main_lcd().clear();
      library_mk61::print_localized_at(0, 0, line_ru, line_en);
    }
    (void) kbd::get_key_wait();
  }
  lcd_std_display_redraw();
}

} // namespace run_measurement

#endif

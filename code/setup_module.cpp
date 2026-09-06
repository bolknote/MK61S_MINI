#include "config.h"
#if MK61_SETUP_IS_LOADABLE
#include "setup_ui.hpp"
#include "loadable_module_runtime.hpp"
#include "lcd_ru.hpp"
#include "keyboard.h"
namespace setup_ui {
static bool invoke(loadable_module::Command command, u32 a = 0, u32 b = 0, u32 c = 0) {
  u32 result = 0;
  if(loadable_module::invoke(loadable_module::Kind::SETUP, command, a, b, c, 0, result)
      != loadable_module::RuntimeStatus::OK) {
    lcd_ru::print_lines("System/SETUP.APP", "unavailable");
    kbd::get_key_wait();
  }
  return false;
}
bool hardware() { return invoke(loadable_module::Command::SETUP_HARDWARE); }
bool date_time() { return invoke(loadable_module::Command::SETUP_DATE_TIME); }
bool calibration() { return invoke(loadable_module::Command::SETUP_CALIBRATION); }
bool font() { return invoke(loadable_module::Command::SETUP_FONT); }
void step_font(i8 delta) { invoke(loadable_module::Command::SETUP_FONT_STEP, (u32) (i32) delta); }
void preview(const char* name, const u8* data, u16 size) {
  invoke(loadable_module::Command::SETUP_PREVIEW,
         (u32) (usize) name, (u32) (usize) data, size);
}
}
#endif

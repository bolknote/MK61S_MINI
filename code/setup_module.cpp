#include "config.h"
#if MK61_SETUP_IS_LOADABLE
#include "setup_ui.hpp"
#include "loadable_module_runtime.hpp"
#include "loadable_app_services.h"
#include "lcd_ru.hpp"
#include "keyboard.h"
namespace setup_ui {
static bool invoke(loadable_module::Command command, u32 a = 0, u32 b = 0,
                   u32 c = 0, u32* command_result = nullptr,
                   bool report_error = true) {
  u32 result = 0;
  if(loadable_module::invoke(loadable_module::Kind::SETUP, command, a, b, c, 0, result)
      != loadable_module::RuntimeStatus::OK) {
    if(report_error) {
      lcd_ru::print_lines("System/SETUP.APP", "unavailable");
      kbd::get_key_wait();
    }
    return false;
  }
  if(command_result != nullptr) *command_result = result;
  return true;
}
bool hardware() { invoke(loadable_module::Command::SETUP_HARDWARE); return false; }
bool date_time() { invoke(loadable_module::Command::SETUP_DATE_TIME); return false; }
bool calibration() { invoke(loadable_module::Command::SETUP_CALIBRATION); return false; }
bool font() { invoke(loadable_module::Command::SETUP_FONT); return false; }
void step_font(i8 delta) { invoke(loadable_module::Command::SETUP_FONT_STEP, (u32) (i32) delta); }
void preview(const char* name, const u8* data, u16 size) {
  invoke(loadable_module::Command::SETUP_PREVIEW,
         (u32) (usize) name, (u32) (usize) data, size);
}
i32 compile_font(u16 id, u8 role, u8 expected_height,
                 u32 ui_key, u8 flags) {
  u32 result = (u32) (i32) MK61_TEXT_FONT_UNAVAILABLE;
  const u32 packed = (u32) role | ((u32) expected_height << 8) |
                     ((u32) flags << 16);
  if(!invoke(loadable_module::Command::SETUP_FONT_COMPILE,
             id, packed, ui_key, &result, false)) {
    return MK61_TEXT_FONT_UNAVAILABLE;
  }
  return (i32) result;
}
}
#endif

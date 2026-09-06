#if defined(MK61_BUILD_SETUP_MODULE)
#include "setup_ui.hpp"
#include "loadable_module_abi.hpp"
extern "C" __attribute__((used, section(".mk61_module_entry")))
u32 mk61_module_entry(u32 command, u32 a, u32 b, u32 c, u32) {
  using loadable_module::Command;
  switch((Command) command) {
    case Command::INITIALIZE:
      return portable_system::bind(a, b, c) &&
          portable_system::call(MK61_SYS_SETUP, MK61_SETUP_VERSION) == 1 ? 0 : 1;
    case Command::SETUP_HARDWARE: return setup_ui::hardware();
    case Command::SETUP_DATE_TIME: return setup_ui::date_time();
    case Command::SETUP_CALIBRATION: return setup_ui::calibration();
    case Command::SETUP_FONT_STEP: setup_ui::step_font((i8) a); return 0;
    case Command::SETUP_FONT: return setup_ui::font();
    case Command::SETUP_PREVIEW:
      setup_ui::preview((const char*) a, (const u8*) b, (u16) c); return 0;
    default: return 0;
  }
}
#endif

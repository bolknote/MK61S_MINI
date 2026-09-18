#if defined(MK61_BUILD_SETUP_MODULE)
#include "setup_ui.hpp"
#include "setup_font_compiler.hpp"
#include "loadable_module_abi.hpp"
extern "C" u32 mk61_app_initialize(const mk61_app_api* api,
                                    u32 image_crc, u32 kind) {
  return portable_system::bind(api, image_crc, kind) &&
      portable_system::call(MK61_SYS_SETUP, MK61_SETUP_VERSION) ==
          MK61_SETUP_API_VERSION ? 0 : 1;
}

extern "C" u32 mk61_app_command(u32 command, u32 a, u32 b, u32 c, u32) {
  using loadable_module::Command;
  switch((Command) command) {
    case Command::SETUP_HARDWARE: return setup_ui::hardware();
    case Command::SETUP_DATE_TIME: return setup_ui::date_time();
    case Command::SETUP_CALIBRATION: return setup_ui::calibration();
    case Command::SETUP_FONT_STEP: setup_ui::step_font((i8) a); return 0;
    case Command::SETUP_FONT: return setup_ui::font();
    case Command::SETUP_PREVIEW:
      setup_ui::preview((const char*) a, (const u8*) b, (u16) c); return 0;
    case Command::SETUP_FONT_COMPILE:
#if MK61_UI_FONT_CLIENT
      return (u32) setup_font_compiler::install(
          (u16) a, (u8) b, (u8) (b >> 8), c, (u8) (b >> 16));
#else
      return (u32) (i32) MK61_TEXT_FONT_UNSUPPORTED;
#endif
    default: return 0;
  }
}
#endif

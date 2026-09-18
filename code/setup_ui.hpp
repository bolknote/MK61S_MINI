#ifndef MK61_SETUP_UI_HPP
#define MK61_SETUP_UI_HPP
#include "rust_types.h"
#include "loadable_app_services.h"
namespace setup_ui {
bool hardware();
bool date_time();
bool calibration();
bool font();
void step_font(i8 delta);
// The caller retains the source buffer until preview returns.
void preview(const char* name, const u8* data, u16 size);
// FMK parsing belongs to SETUP.APP. The resident invokes this command with a
// stable C5 id and receives an mk61_service_text_font_result.
i32 compile_font(u16 id, u8 role, u8 expected_height = 0,
                 u32 ui_key = 0, u8 flags = 0);
}
#endif

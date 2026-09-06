#include "system_compat.hpp"
#include "setup_service.hpp"
namespace setup_ui {
u32 service(u32 operation, u32 a, u32 b, void* payload) {
  return portable_system::call(MK61_SYS_SETUP, operation, a, b, payload);
}
}
namespace lcd_ru {
void restore_default_font() { setup_ui::service(MK61_SETUP_FONT_RESTORE); }
void print_window(const char* const* rows, u8 count) { portable_system::text_rows(rows, count); }
void print_at(u8 col, u8 row, const char* text, u8) {
  setup_ui::service(MK61_SETUP_TEXT, row, col, (void*) text);
}
void print_menu_line(u8 row, char mark, const char* text) {
  setup_ui::service(MK61_SETUP_TEXT, row, 0x100U | (u8) mark, (void*) text);
}
}

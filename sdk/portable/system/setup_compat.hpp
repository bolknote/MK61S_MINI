#ifndef MK61_SETUP_COMPAT_HPP
#define MK61_SETUP_COMPAT_HPP
#define MK61_HAS_GRAPHICAL_TEXT_SETTINGS 1
#define MK61_ENABLE_EXTENDED_FONT_SETTINGS 1
#include "display_profile.hpp"
namespace lcd_display {
inline TextProfile normalizeSettingsTextProfile(TextProfile profile) {
  return portable_system::call(MK61_SYS_SETUP, MK61_SETUP_FEATURES) &
         MK61_SETUP_FEATURE_EXTENDED_TEXT_PROFILE
      ? normalizeGraphicalTextProfile(profile) : presetGraphicalTextProfile(profile);
}
}
#define KEY_NEG (keyboard_layout::active().neg)
namespace lcd_ru {
void restore_default_font();
void print_window(const char* const* rows, u8 count);
void print_at(u8 col, u8 row, const char* text, u8 width);
void print_menu_line(u8 row, char mark, const char* text);
}
#endif

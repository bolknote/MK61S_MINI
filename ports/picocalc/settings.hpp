#ifndef MK61_PICOCALC_SETTINGS_HPP
#define MK61_PICOCALC_SETTINGS_HPP
#include "rust_types.h"

namespace picocalc {
struct Settings {
    u8 volume = 10;
    u8 idle_signal = 1;
    u8 classic_speed = 0;
    u8 memory = 2; // 105, 112, AUTO, as on STM32.
    u8 random = 0;
    u8 russian = 1;
    u8 calculator_font = 0;
    u8 ui_font_size = 14;
    u8 lcd_backlight = 240;
    u8 key_backlight = 40;
    u8 sleep_minutes = 5;
    i16 rtc_ppm = 0;
    u32 alarm_epoch[2] = {};
    u8 alarm_flags = 0;
    u8 text_rows=8,text_width=5,text_height=8,text_gap=0;
    u8 ui_font_family=1;
    u32 ui_font_key=0;
};
bool valid_settings(const Settings& value);
constexpr unsigned SETTINGS_PAGE_BYTES = 256;
void encode_settings(const Settings& value, u32 sequence, u8 out[SETTINGS_PAGE_BYTES]);
bool decode_settings(const u8 page[SETTINGS_PAGE_BYTES], Settings& value, u32& sequence);
bool load_device_settings(Settings& value);
bool save_device_settings(const Settings& value);
} // namespace picocalc
#endif

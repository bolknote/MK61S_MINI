#include "settings.hpp"
#include <cstring>

namespace picocalc {
namespace {
u32 checksum(const u8 *data, unsigned size = 32) {
  u32 result = 2166136261U;
  for (unsigned i = 0; i < size; ++i)
    result = (result ^ data[i]) * 16777619U;
  return result;
}
void put32(u8 *p, u32 value) {
  for (unsigned i = 0; i < 4; ++i)
    p[i] = (u8)(value >> (8 * i));
}
u32 get32(const u8 *p) {
  return (u32)p[0] | (u32)p[1] << 8 | (u32)p[2] << 16 | (u32)p[3] << 24;
}
} // namespace
bool valid_settings(const Settings &s) {
  return s.volume <= 10 && s.idle_signal <= 1 && s.classic_speed <= 1 &&
         s.memory <= 2 && s.random <= 1 && s.russian <= 1 &&
         s.calculator_font <= 1 &&
         (((s.ui_font_family==0 || s.ui_font_family==1 || (s.ui_font_family==3 && s.ui_font_key!=0)) &&
           (s.ui_font_size==12 || s.ui_font_size==14 || s.ui_font_size==16)) ||
          (s.ui_font_family==4 && s.ui_font_size==16) ||
          (s.ui_font_family==5 && s.ui_font_size==5)) &&
         s.lcd_backlight >= 16 && s.lcd_backlight <= 240 &&
         s.lcd_backlight % 16 == 0 && s.key_backlight <= 240 &&
         (s.sleep_minutes == 0 || s.sleep_minutes == 1 ||
          s.sleep_minutes == 5 || s.sleep_minutes == 15 ||
          s.sleep_minutes == 30) &&
         s.rtc_ppm >= -500 && s.rtc_ppm <= 500 && s.alarm_flags < 16 &&
         s.alarm_epoch[0] < 3155760000UL && s.alarm_epoch[1] < 3155760000UL &&
         s.text_rows>=1 && s.text_rows<=10 && s.text_width>=3 && s.text_width<=10 &&
         s.text_height>=5 && s.text_height<=16 && s.text_gap<=4 &&
         s.text_rows*(s.text_height+s.text_gap)<=64;
}
void encode_settings(const Settings &s, u32 sequence,
                     u8 out[SETTINGS_PAGE_BYTES]) {
  std::memset(out, 0xFF, SETTINGS_PAGE_BYTES);
  std::memcpy(out, "M61P", 4);
  out[4] = 5;
  put32(out + 8, sequence);
  const u8 values[] = {s.volume,          s.idle_signal,  s.classic_speed,
                       s.memory,          s.random,       s.russian,
                       s.calculator_font, s.ui_font_size, s.lcd_backlight,
                       s.key_backlight};
  std::memcpy(out + 12, values, sizeof(values));
  out[22] = s.sleep_minutes;
  out[23] = (u8)s.rtc_ppm;
  out[24] = (u8)((u16)s.rtc_ppm >> 8);
  out[25] = s.alarm_flags;
  put32(out + 26, s.alarm_epoch[0]);
  put32(out + 30, s.alarm_epoch[1]);
  out[34]=s.text_rows;out[35]=s.text_width;out[36]=s.text_height;out[37]=s.text_gap;
  out[38]=s.ui_font_family;put32(out+40,s.ui_font_key);
  put32(out + 64, checksum(out, 64));
}
bool decode_settings(const u8 *page, Settings &value, u32 &sequence) {
  if (std::memcmp(page, "M61P", 4) || page[4] < 1 || page[4] > 5)
    return false;
  const unsigned crc_offset = page[4] >= 3 ? 64 : 32;
  if (get32(page + crc_offset) != checksum(page, crc_offset))
    return false;
  Settings next{page[12], page[13], page[14], page[15], page[16],
                page[17], page[18], page[19], page[20], page[21]};
  if (page[4] >= 2) {
    next.sleep_minutes = page[22];
    next.rtc_ppm = (i16)((u16)page[23] | (u16)page[24] << 8);
  }
  if (page[4] >= 3) {
    next.alarm_flags = page[25];
    next.alarm_epoch[0] = get32(page + 26);
    next.alarm_epoch[1] = get32(page + 30);
  }
  if(page[4]>=4) { next.text_rows=page[34];next.text_width=page[35];next.text_height=page[36];next.text_gap=page[37]; }
  if(page[4]>=5) { next.ui_font_family=page[38];next.ui_font_key=get32(page+40); }
  if (!valid_settings(next))
    return false;
  value = next;
  sequence = get32(page + 8);
  return true;
}
} // namespace picocalc

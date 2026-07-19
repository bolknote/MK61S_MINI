#ifndef MK61_RTC_SETTINGS_CORE_HPP
#define MK61_RTC_SETTINGS_CORE_HPP

#include "rtc_clock_core.hpp"

namespace rtc_settings {

static constexpr u8 EDITABLE_DIGIT_COUNT = 14;
static constexpr usize DIGIT_POSITIONS[EDITABLE_DIGIT_COUNT] = {
  0, 1, 2, 3, 5, 6, 8, 9, 11, 12, 14, 15, 17, 18
};

struct Editor {
  char text[rtc_clock::DATETIME_TEXT_SIZE];
  u8 active_digit;
};

inline bool begin(Editor& editor, const rtc_clock::DateTime& value) {
  if(!rtc_clock::format_datetime(value, editor.text)) return false;
  editor.active_digit = 0;
  return true;
}

inline usize active_text_position(const Editor& editor) {
  const u8 active = editor.active_digit < EDITABLE_DIGIT_COUNT
    ? editor.active_digit
    : (u8) (EDITABLE_DIGIT_COUNT - 1);
  return DIGIT_POSITIONS[active];
}

inline void move_left(Editor& editor) {
  if(editor.active_digit > 0) editor.active_digit--;
}

inline void move_right(Editor& editor) {
  if(editor.active_digit + 1 < EDITABLE_DIGIT_COUNT) editor.active_digit++;
}

inline bool enter_digit(Editor& editor, i32 digit) {
  if(digit < 0 || digit > 9) return false;
  editor.text[active_text_position(editor)] = (char) ('0' + digit);
  move_right(editor);
  return true;
}

inline bool value(const Editor& editor, rtc_clock::DateTime& out) {
  return rtc_clock::parse_datetime(editor.text, out);
}

} // namespace rtc_settings

#endif

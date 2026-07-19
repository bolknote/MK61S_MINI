#ifndef MK61_RTC_CLOCK_CORE_HPP
#define MK61_RTC_CLOCK_CORE_HPP

#include "rust_types.h"

namespace rtc_clock {

static constexpr usize DATETIME_TEXT_LENGTH = 19;
static constexpr usize DATETIME_TEXT_SIZE = DATETIME_TEXT_LENGTH + 1;

struct DateTime {
  u16 year;
  u8 month;
  u8 day;
  u8 hour;
  u8 minute;
  u8 second;
};

enum class TerminalAction : u8 {
  SHOW,
  SET,
  INVALID
};

struct TerminalRequest {
  TerminalAction action;
  DateTime date_time;
};

inline bool is_horizontal_space(char c) {
  return c == ' ' || c == '\t';
}

inline bool is_text_end(char c) {
  return c == 0 || c == '\r' || c == '\n';
}

inline const char* skip_horizontal_spaces(const char* text) {
  while(text != 0 && is_horizontal_space(*text)) text++;
  return text;
}

inline bool is_leap_year(u16 year) {
  return (year % 4 == 0) && ((year % 100 != 0) || (year % 400 == 0));
}

inline u8 days_in_month(u16 year, u8 month) {
  static constexpr u8 DAYS[] = {31, 28, 31, 30, 31, 30, 31, 31, 30, 31, 30, 31};
  if(month < 1 || month > 12) return 0;
  if(month == 2 && is_leap_year(year)) return 29;
  return DAYS[month - 1];
}

inline bool is_valid(const DateTime& value) {
  if(value.year < 2000 || value.year > 2099) return false;
  if(value.month < 1 || value.month > 12) return false;
  if(value.day < 1 || value.day > days_in_month(value.year, value.month)) return false;
  if(value.hour > 23 || value.minute > 59 || value.second > 59) return false;
  return true;
}

inline u16 parse_fixed_decimal(const char* text, usize count) {
  u16 value = 0;
  for(usize i = 0; i < count; i++) value = (u16) (value * 10 + (u16) (text[i] - '0'));
  return value;
}

// Strict human-readable terminal format: YYYY-MM-DD HH:MM:SS.
inline bool parse_datetime(const char* text, DateTime& out) {
  text = skip_horizontal_spaces(text);
  if(text == 0) return false;

  usize length = 0;
  while(!is_text_end(text[length])) length++;
  while(length > 0 && is_horizontal_space(text[length - 1])) length--;
  if(length != DATETIME_TEXT_LENGTH) return false;

  static constexpr usize DIGIT_POSITIONS[] = {
    0, 1, 2, 3, 5, 6, 8, 9, 11, 12, 14, 15, 17, 18
  };
  for(usize position : DIGIT_POSITIONS) {
    if(text[position] < '0' || text[position] > '9') return false;
  }
  if(text[4] != '-' || text[7] != '-' || text[10] != ' ' || text[13] != ':' || text[16] != ':') return false;

  const DateTime parsed = {
    parse_fixed_decimal(text, 4),
    (u8) parse_fixed_decimal(text + 5, 2),
    (u8) parse_fixed_decimal(text + 8, 2),
    (u8) parse_fixed_decimal(text + 11, 2),
    (u8) parse_fixed_decimal(text + 14, 2),
    (u8) parse_fixed_decimal(text + 17, 2)
  };
  if(!is_valid(parsed)) return false;
  out = parsed;
  return true;
}

inline void write_two_digits(char* out, u8 value) {
  out[0] = (char) ('0' + value / 10);
  out[1] = (char) ('0' + value % 10);
}

inline bool format_datetime(const DateTime& value, char out[DATETIME_TEXT_SIZE]) {
  if(out == 0 || !is_valid(value)) return false;
  out[0] = (char) ('0' + (value.year / 1000) % 10);
  out[1] = (char) ('0' + (value.year / 100) % 10);
  out[2] = (char) ('0' + (value.year / 10) % 10);
  out[3] = (char) ('0' + value.year % 10);
  out[4] = '-';
  write_two_digits(out + 5, value.month);
  out[7] = '-';
  write_two_digits(out + 8, value.day);
  out[10] = ' ';
  write_two_digits(out + 11, value.hour);
  out[13] = ':';
  write_two_digits(out + 14, value.minute);
  out[16] = ':';
  write_two_digits(out + 17, value.second);
  out[19] = 0;
  return true;
}

inline usize bounded_text_length(const char* text, usize limit) {
  if(text == 0) return 0;
  usize length = 0;
  while(length <= limit && text[length] != 0) length++;
  return length;
}

inline u8 build_month(const char* text) {
  static constexpr char MONTHS[] = "JanFebMarAprMayJunJulAugSepOctNovDec";
  if(text == 0) return 0;
  for(u8 month = 0; month < 12; month++) {
    const usize offset = (usize) month * 3;
    if(text[0] == MONTHS[offset] && text[1] == MONTHS[offset + 1] && text[2] == MONTHS[offset + 2]) {
      return (u8) (month + 1);
    }
  }
  return 0;
}

// Converts the standard compiler strings ("Mmm dd yyyy", "HH:MM:SS") into
// an editable initial value. This does not mark or set the hardware RTC.
inline bool parse_build_datetime(const char* date, const char* time, DateTime& out) {
  if(bounded_text_length(date, 11) != 11 || bounded_text_length(time, 8) != 8) return false;
  if(date[3] != ' ' || date[6] != ' ' || time[2] != ':' || time[5] != ':') return false;

  const u8 month = build_month(date);
  if(month == 0 || date[5] < '0' || date[5] > '9') return false;
  if(date[4] != ' ' && (date[4] < '0' || date[4] > '9')) return false;

  for(usize position = 7; position < 11; position++) {
    if(date[position] < '0' || date[position] > '9') return false;
  }
  static constexpr usize TIME_DIGITS[] = {0, 1, 3, 4, 6, 7};
  for(usize position : TIME_DIGITS) {
    if(time[position] < '0' || time[position] > '9') return false;
  }

  const DateTime parsed = {
    parse_fixed_decimal(date + 7, 4),
    month,
    (u8) ((date[4] == ' ')
      ? (date[5] - '0')
      : parse_fixed_decimal(date + 4, 2)),
    (u8) parse_fixed_decimal(time, 2),
    (u8) parse_fixed_decimal(time + 3, 2),
    (u8) parse_fixed_decimal(time + 6, 2)
  };
  if(!is_valid(parsed)) return false;
  out = parsed;
  return true;
}

// STM32 calendar weekday: Monday=1 ... Sunday=7.
inline u8 weekday(const DateTime& value) {
  static constexpr u8 MONTH_OFFSETS[] = {0, 3, 2, 5, 0, 3, 5, 1, 4, 6, 2, 4};
  u32 year = value.year;
  if(value.month < 3) year--;
  const u8 sunday_zero = (u8) ((year + year / 4 - year / 100 + year / 400
      + MONTH_OFFSETS[value.month - 1] + value.day) % 7);
  return sunday_zero == 0 ? 7 : sunday_zero;
}

inline TerminalRequest parse_terminal_request(const char* args) {
  TerminalRequest result = {TerminalAction::INVALID, {0, 0, 0, 0, 0, 0}};
  const char* text = skip_horizontal_spaces(args);
  if(text == 0 || is_text_end(*text)) {
    result.action = TerminalAction::SHOW;
    return result;
  }

  if(text[0] == 's' && text[1] == 'e' && text[2] == 't' && is_horizontal_space(text[3])) {
    text = skip_horizontal_spaces(text + 3);
    if(parse_datetime(text, result.date_time)) result.action = TerminalAction::SET;
  }
  return result;
}

} // namespace rtc_clock

#endif

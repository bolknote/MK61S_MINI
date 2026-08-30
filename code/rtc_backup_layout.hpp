#ifndef MK61_RTC_BACKUP_LAYOUT_HPP
#define MK61_RTC_BACKUP_LAYOUT_HPP

#include "rtc_clock_core.hpp"

namespace rtc_backup_layout {

// F401/F411 expose DR0..DR19. The project deliberately uses only the high
// window DR11..DR19: DR1 is the STM32 core convention, DR2/DR3 belong to the
// existing RTC marker/calibration, and DR4/DR10 are current/legacy HID-loader
// magic registers. DR6/DR7 are used by STM32RTC only on STM32F1.
static constexpr u8 FIRST_REGISTER = 11;
static constexpr usize WORD_COUNT = 9;
static constexpr u8 LAST_REGISTER = FIRST_REGISTER + WORD_COUNT - 1;
static constexpr u32 HEADER = 0x4D4B0109UL; // "MK", version 1, 9 words

enum Word : u8 {
  WORD_HEADER = 0,
  WORD_BOOT_COUNT,
  WORD_RESET_FLAGS,
  WORD_STATUS,
  WORD_ALARM_A_DATE,
  WORD_ALARM_A_TIME,
  WORD_ALARM_B_DATE,
  WORD_ALARM_B_TIME,
  WORD_CHECKSUM
};

enum class AlarmId : u8 { A = 0, B = 1 };
enum class Repeat : u8 { ONE_SHOT = 0, DAILY = 1 };
enum class WakeReason : u8 {
  UNKNOWN = 0,
  RESET = 1,
  ALARM_A = 2,
  ALARM_B = 3,
  MISSED_A = 4,
  MISSED_B = 5,
  MISSED_BOTH = 6
};

struct Alarm {
  bool enabled;
  Repeat repeat;
  rtc_clock::DateTime when;
  // 0..999 requests a subsecond comparison; 1000 keeps the traditional
  // whole-second alarm whose subsecond field is masked in hardware.
  u16 millisecond;
};

struct Metadata {
  u32 boot_count;
  u32 reset_flags;
  WakeReason last_wake;
  bool previous_power_unstable;
  Alarm alarms[2];
};

struct Words { u32 value[WORD_COUNT]; };

static constexpr u32 STATUS_WAKE_MASK = 0x00000007UL;
static constexpr u32 STATUS_POWER_UNSTABLE = 0x00000100UL;
static constexpr u32 STATUS_ALLOWED_MASK =
    STATUS_WAKE_MASK | STATUS_POWER_UNSTABLE;
static constexpr u32 DATE_ALLOWED_MASK = 0x0000FFFFUL;
static constexpr u16 MILLISECOND_IGNORED = 1000;
static constexpr u8 TIME_MILLISECOND_SHIFT = 19;
static constexpr u32 TIME_MILLISECOND_MASK =
    0x000003FFUL << TIME_MILLISECOND_SHIFT;
static constexpr u32 TIME_ALLOWED_MASK =
    0x0007FFFFUL | TIME_MILLISECOND_MASK;
static constexpr u32 TIME_REPEAT_BIT = 1UL << 17;
static constexpr u32 TIME_ENABLED_BIT = 1UL << 18;

inline Alarm disabled_alarm(void) {
  return {false, Repeat::ONE_SHOT, {0, 0, 0, 0, 0, 0},
          MILLISECOND_IGNORED};
}

inline Metadata empty_metadata(void) {
  return {0, 0, WakeReason::UNKNOWN, false,
          {disabled_alarm(), disabled_alarm()}};
}

inline u32 increment_saturated(u32 value) {
  return value == 0xFFFFFFFFUL ? value : value + 1U;
}

// A compact integrity checksum, not an authentication primitive. The header
// is committed last by the hardware adapter; this catches torn body writes
// and accidental corruption without a software CRC table.
inline u32 checksum(const u32* words, usize count) {
  u32 value = 2166136261UL;
  for(usize index = 0; index < count; index++) {
    value ^= words[index];
    value *= 16777619UL;
    value ^= value >> 16;
  }
  return value ^ 0xA5C35A3CUL;
}

inline bool valid_time(const rtc_clock::DateTime& value) {
  return value.hour < 24 && value.minute < 60 && value.second < 60;
}

inline bool valid_alarm(const Alarm& alarm) {
  if(!alarm.enabled) return true;
  if(alarm.repeat != Repeat::ONE_SHOT && alarm.repeat != Repeat::DAILY) {
    return false;
  }
  if(alarm.millisecond > MILLISECOND_IGNORED) return false;
  return alarm.repeat == Repeat::DAILY
      ? valid_time(alarm.when)
      : rtc_clock::is_valid(alarm.when);
}

inline u32 encode_alarm_date(const Alarm& alarm) {
  if(!alarm.enabled || alarm.repeat == Repeat::DAILY) return 0;
  return (u32) (alarm.when.year - 2000U) |
      ((u32) alarm.when.month << 7) |
      ((u32) alarm.when.day << 11);
}

inline u32 encode_alarm_time(const Alarm& alarm) {
  if(!alarm.enabled) return 0;
  const u32 encoded_millisecond =
      alarm.millisecond == MILLISECOND_IGNORED
          ? 0U : (u32) alarm.millisecond + 1U;
  return (u32) alarm.when.second |
      ((u32) alarm.when.minute << 6) |
      ((u32) alarm.when.hour << 12) |
      (alarm.repeat == Repeat::DAILY ? TIME_REPEAT_BIT : 0U) |
      TIME_ENABLED_BIT |
      (encoded_millisecond << TIME_MILLISECOND_SHIFT);
}

inline bool decode_alarm(u32 date_word, u32 time_word, Alarm& out) {
  if((date_word & ~DATE_ALLOWED_MASK) != 0 ||
     (time_word & ~TIME_ALLOWED_MASK) != 0) {
    return false;
  }
  if((time_word & TIME_ENABLED_BIT) == 0) {
    if(date_word != 0 || time_word != 0) return false;
    out = disabled_alarm();
    return true;
  }

  const Repeat repeat = (time_word & TIME_REPEAT_BIT) != 0
      ? Repeat::DAILY : Repeat::ONE_SHOT;
  const u16 encoded_millisecond = (u16)
      ((time_word & TIME_MILLISECOND_MASK) >> TIME_MILLISECOND_SHIFT);
  const u16 millisecond = encoded_millisecond == 0
      ? MILLISECOND_IGNORED : (u16) (encoded_millisecond - 1U);
  const rtc_clock::DateTime when = {
    repeat == Repeat::DAILY ? (u16) 2000 :
      (u16) (2000U + (date_word & 0x7FU)),
    repeat == Repeat::DAILY ? (u8) 1 :
      (u8) ((date_word >> 7) & 0x0FU),
    repeat == Repeat::DAILY ? (u8) 1 :
      (u8) ((date_word >> 11) & 0x1FU),
    (u8) ((time_word >> 12) & 0x1FU),
    (u8) ((time_word >> 6) & 0x3FU),
    (u8) (time_word & 0x3FU)
  };
  const Alarm decoded = {true, repeat, when, millisecond};
  if(!valid_alarm(decoded)) return false;
  out = decoded;
  return true;
}

inline bool encode(const Metadata& metadata, Words& out) {
  if((u8) metadata.last_wake > (u8) WakeReason::MISSED_BOTH ||
     !valid_alarm(metadata.alarms[0]) ||
     !valid_alarm(metadata.alarms[1])) {
    return false;
  }

  out.value[WORD_HEADER] = HEADER;
  out.value[WORD_BOOT_COUNT] = metadata.boot_count;
  out.value[WORD_RESET_FLAGS] = metadata.reset_flags;
  out.value[WORD_STATUS] = (u32) metadata.last_wake |
      (metadata.previous_power_unstable ? STATUS_POWER_UNSTABLE : 0U);
  out.value[WORD_ALARM_A_DATE] = encode_alarm_date(metadata.alarms[0]);
  out.value[WORD_ALARM_A_TIME] = encode_alarm_time(metadata.alarms[0]);
  out.value[WORD_ALARM_B_DATE] = encode_alarm_date(metadata.alarms[1]);
  out.value[WORD_ALARM_B_TIME] = encode_alarm_time(metadata.alarms[1]);
  out.value[WORD_CHECKSUM] = checksum(out.value, WORD_CHECKSUM);
  return true;
}

inline bool decode(const Words& words, Metadata& out) {
  if(words.value[WORD_HEADER] != HEADER ||
     words.value[WORD_CHECKSUM] != checksum(words.value, WORD_CHECKSUM) ||
     (words.value[WORD_STATUS] & ~STATUS_ALLOWED_MASK) != 0) {
    return false;
  }
  const u32 wake = words.value[WORD_STATUS] & STATUS_WAKE_MASK;
  if(wake > (u32) WakeReason::MISSED_BOTH) return false;

  Metadata decoded = empty_metadata();
  decoded.boot_count = words.value[WORD_BOOT_COUNT];
  decoded.reset_flags = words.value[WORD_RESET_FLAGS];
  decoded.last_wake = (WakeReason) wake;
  decoded.previous_power_unstable =
      (words.value[WORD_STATUS] & STATUS_POWER_UNSTABLE) != 0;
  if(!decode_alarm(words.value[WORD_ALARM_A_DATE],
                   words.value[WORD_ALARM_A_TIME], decoded.alarms[0]) ||
     !decode_alarm(words.value[WORD_ALARM_B_DATE],
                   words.value[WORD_ALARM_B_TIME], decoded.alarms[1])) {
    return false;
  }
  out = decoded;
  return true;
}

inline i8 compare(const rtc_clock::DateTime& left,
                  const rtc_clock::DateTime& right) {
  if(left.year != right.year) return left.year < right.year ? -1 : 1;
  if(left.month != right.month) return left.month < right.month ? -1 : 1;
  if(left.day != right.day) return left.day < right.day ? -1 : 1;
  if(left.hour != right.hour) return left.hour < right.hour ? -1 : 1;
  if(left.minute != right.minute) return left.minute < right.minute ? -1 : 1;
  if(left.second != right.second) return left.second < right.second ? -1 : 1;
  return 0;
}

// An IRQ means the hardware calendar and its quantized subsecond comparator
// matched. The retained millisecond is intentionally not compared again:
// milliseconds cannot represent every ck_apre phase, and the HAL's inverse
// conversion can place the comparison up to one RTC tick before the rounded
// value. Month and year still need this software check because STM32 alarms do
// not compare them.
inline bool hardware_candidate_is_due(const rtc_clock::StartupSnapshot& now,
                                      const Alarm& alarm) {
  return alarm.enabled && alarm.repeat == Repeat::ONE_SHOT &&
      compare(now.date_time, alarm.when) >= 0;
}

inline bool add_seconds(const rtc_clock::DateTime& base, u32 seconds,
                        rtc_clock::DateTime& out) {
  if(!rtc_clock::is_valid(base)) return false;
  rtc_clock::DateTime value = base;
  const u32 current = (u32) value.hour * 3600U +
      (u32) value.minute * 60U + value.second;
  const u32 remainder = seconds % 86400U;
  u32 days = seconds / 86400U;
  const u32 next = current + remainder;
  if(next >= 86400U) days++;
  const u32 day_second = next % 86400U;
  value.hour = (u8) (day_second / 3600U);
  value.minute = (u8) ((day_second / 60U) % 60U);
  value.second = (u8) (day_second % 60U);

  while(days-- != 0) {
    const u8 last = rtc_clock::days_in_month(value.year, value.month);
    if(value.day < last) {
      value.day++;
    } else {
      value.day = 1;
      if(value.month < 12) {
        value.month++;
      } else {
        if(value.year >= 2099) return false;
        value.year++;
        value.month = 1;
      }
    }
  }
  out = value;
  return true;
}

inline const char* repeat_name(Repeat repeat) {
  return repeat == Repeat::DAILY ? "daily" : "one-shot";
}

inline const char* wake_reason_name(WakeReason reason) {
  switch(reason) {
    case WakeReason::RESET: return "reset";
    case WakeReason::ALARM_A: return "alarm-a";
    case WakeReason::ALARM_B: return "alarm-b";
    case WakeReason::MISSED_A: return "missed-a";
    case WakeReason::MISSED_B: return "missed-b";
    case WakeReason::MISSED_BOTH: return "missed-a+b";
    default: return "unknown";
  }
}

} // namespace rtc_backup_layout

#endif

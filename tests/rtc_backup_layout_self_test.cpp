#include <cassert>
#include <cstring>

#include "../code/rtc_backup_layout.hpp"

using namespace rtc_backup_layout;

static bool same_datetime(const rtc_clock::DateTime& left,
                          const rtc_clock::DateTime& right) {
  return left.year == right.year && left.month == right.month &&
      left.day == right.day && left.hour == right.hour &&
      left.minute == right.minute && left.second == right.second;
}

static void test_empty_and_counter(void) {
  Metadata metadata = empty_metadata();
  Words words = {};
  assert(encode(metadata, words));
  Metadata decoded = {};
  assert(decode(words, decoded));
  assert(decoded.boot_count == 0);
  assert(!decoded.alarms[0].enabled && !decoded.alarms[1].enabled);

  for(unsigned index = 0; index < 10000; index++) {
    decoded.boot_count = increment_saturated(decoded.boot_count);
  }
  assert(decoded.boot_count == 10000);
  assert(increment_saturated(0xFFFFFFFEUL) == 0xFFFFFFFFUL);
  assert(increment_saturated(0xFFFFFFFFUL) == 0xFFFFFFFFUL);
}

static void test_alarm_round_trip(void) {
  Metadata metadata = empty_metadata();
  metadata.boot_count = 123;
  metadata.reset_flags = 0xA55A00FFUL;
  metadata.last_wake = WakeReason::ALARM_B;
  metadata.previous_power_unstable = true;
  metadata.alarms[0] = {
    true, Repeat::ONE_SHOT, {2099, 12, 31, 23, 59, 59}, 937
  };
  metadata.alarms[1] = {
    true, Repeat::DAILY, {2000, 1, 1, 7, 5, 9}, MILLISECOND_IGNORED
  };

  Words words = {};
  assert(encode(metadata, words));
  Metadata decoded = {};
  assert(decode(words, decoded));
  assert(decoded.boot_count == metadata.boot_count);
  assert(decoded.reset_flags == metadata.reset_flags);
  assert(decoded.last_wake == metadata.last_wake);
  assert(decoded.previous_power_unstable);
  assert(decoded.alarms[0].enabled);
  assert(decoded.alarms[0].repeat == Repeat::ONE_SHOT);
  assert(same_datetime(decoded.alarms[0].when, metadata.alarms[0].when));
  assert(decoded.alarms[0].millisecond == 937);
  assert(decoded.alarms[1].enabled);
  assert(decoded.alarms[1].repeat == Repeat::DAILY);
  assert(decoded.alarms[1].when.hour == 7);
  assert(decoded.alarms[1].when.minute == 5);
  assert(decoded.alarms[1].when.second == 9);

  metadata.last_wake = WakeReason::MISSED_BOTH;
  assert(encode(metadata, words));
  assert(decode(words, decoded));
  assert(decoded.last_wake == WakeReason::MISSED_BOTH);
}

static void test_integrity_and_canonical_encoding(void) {
  Metadata metadata = empty_metadata();
  metadata.alarms[0] = {
    true, Repeat::ONE_SHOT, {2028, 2, 29, 0, 0, 1}, 0
  };
  Words valid = {};
  assert(encode(metadata, valid));

  for(usize word = 0; word < WORD_COUNT; word++) {
    for(u8 bit = 0; bit < 32; bit++) {
      Words damaged = valid;
      damaged.value[word] ^= 1UL << bit;
      Metadata decoded = {};
      assert(!decode(damaged, decoded));
    }
  }

  Words torn = valid;
  torn.value[WORD_HEADER] = 0;
  assert(!decode(torn, metadata));
  torn = valid;
  torn.value[WORD_ALARM_A_TIME] = 0;
  assert(!decode(torn, metadata));

  Alarm alarm = disabled_alarm();
  assert(!decode_alarm(1, 0, alarm));
  assert(!decode_alarm(0, 1, alarm));
  assert(!decode_alarm(1UL << 20, TIME_ENABLED_BIT, alarm));
}

static void test_validation_and_calendar_math(void) {
  Metadata invalid = empty_metadata();
  invalid.alarms[0] = {
    true, Repeat::ONE_SHOT, {2027, 2, 29, 1, 2, 3},
    MILLISECOND_IGNORED
  };
  Words words = {};
  assert(!encode(invalid, words));

  rtc_clock::DateTime value = {};
  assert(add_seconds({2028, 2, 28, 23, 59, 59}, 1, value));
  assert(same_datetime(value, {2028, 2, 29, 0, 0, 0}));
  assert(add_seconds(value, 86400, value));
  assert(same_datetime(value, {2028, 3, 1, 0, 0, 0}));
  assert(add_seconds({2026, 12, 31, 23, 59, 30}, 90, value));
  assert(same_datetime(value, {2027, 1, 1, 0, 1, 0}));
  assert(!add_seconds({2099, 12, 31, 23, 59, 59}, 1, value));

  assert(rtc_clock::snapshot_milliseconds(
      {{2026, 1, 1, 0, 0, 0}, 255, 255, true}) == 0);
  assert(rtc_clock::snapshot_milliseconds(
      {{2026, 1, 1, 0, 0, 0}, 127, 255, true}) == 500);
  assert(rtc_clock::snapshot_milliseconds(
      {{2026, 1, 1, 0, 0, 0}, 0, 255, true}) == 996);

  u64 projected = 0;
  assert(rtc_clock::snapshot_milliseconds_since_2000(
      {{2000, 1, 1, 0, 0, 0}, 255, 255, false}, projected));
  assert(projected == 0);
  assert(rtc_clock::snapshot_milliseconds_since_2000(
      {{2000, 1, 2, 0, 0, 0}, 127, 255, true}, projected));
  assert(projected == 86400500ULL);

  u32 elapsed_ms = 0;
  assert(rtc_clock::elapsed_snapshot_milliseconds(
      {{2028, 2, 29, 23, 59, 59}, 127, 255, true},
      {{2028, 3, 1, 0, 0, 1}, 63, 255, true}, elapsed_ms));
  assert(elapsed_ms == 2250);
  assert(!rtc_clock::elapsed_snapshot_milliseconds(
      {{2028, 3, 1, 0, 0, 1}, 63, 255, true},
      {{2028, 2, 29, 23, 59, 59}, 127, 255, true}, elapsed_ms));

  u16 wakeup_counter = 0;
  assert(rtc_clock::stop_wakeup_counter(127, 255, 1, wakeup_counter));
  assert(wakeup_counter == 2047); // 32768 / 16 * 1 - 1
  assert(rtc_clock::stop_wakeup_counter(127, 255, 5, wakeup_counter));
  assert(wakeup_counter == 10239);
  assert(rtc_clock::stop_wakeup_counter(127, 249, 1, wakeup_counter));
  assert(wakeup_counter == 1999); // 32000 / 16 * 1 - 1
  assert(rtc_clock::stop_wakeup_counter(127, 249, 5, wakeup_counter));
  assert(wakeup_counter == 9999);
  assert(!rtc_clock::stop_wakeup_counter(127, 255, 0, wakeup_counter));
  assert(!rtc_clock::stop_wakeup_counter(127, 255, 6, wakeup_counter));
  assert(!rtc_clock::stop_wakeup_counter(128, 255, 1, wakeup_counter));
  assert(!rtc_clock::stop_wakeup_counter(127, 32768, 1, wakeup_counter));

  // Regression: 507 ms maps back to SSR=126 with PREDIV_S=255, whose readable
  // phase is 503 ms. The IRQ is nevertheless the intended candidate for this
  // exact calendar second and must not be discarded as "early".
  const Alarm quantized = {
    true, Repeat::ONE_SHOT, {2026, 1, 1, 0, 0, 3}, 507
  };
  const rtc_clock::StartupSnapshot quantized_irq = {
    {2026, 1, 1, 0, 0, 3}, 126, 255, true
  };
  assert(rtc_clock::snapshot_milliseconds(quantized_irq) == 503);
  assert(hardware_candidate_is_due(quantized_irq, quantized));
  assert(!hardware_candidate_is_due(
      {{2025, 12, 1, 0, 0, 3}, 126, 255, true}, quantized));
  assert(!hardware_candidate_is_due(
      {{2026, 1, 1, 0, 0, 2}, 0, 255, true}, quantized));

  assert(compare({2026, 1, 1, 0, 0, 0},
                 {2026, 1, 1, 0, 0, 0}) == 0);
  assert(compare({2026, 1, 1, 0, 0, 0},
                 {2026, 1, 1, 0, 0, 1}) < 0);
  assert(compare({2027, 1, 1, 0, 0, 0},
                 {2026, 12, 31, 23, 59, 59}) > 0);
}

int main(void) {
  static_assert(FIRST_REGISTER == 11 && LAST_REGISTER == 19,
                "RTC backup window changed");
  static_assert(WORD_COUNT == 9, "RTC backup format changed");
  test_empty_and_counter();
  test_alarm_round_trip();
  test_integrity_and_canonical_encoding();
  test_validation_and_calendar_math();
  return 0;
}

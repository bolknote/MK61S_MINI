#ifndef MK61_PICOCALC_CLOCK_HPP
#define MK61_PICOCALC_CLOCK_HPP
#include "rust_types.h"
namespace picocalc {
namespace clock {
struct DateTime {
  int year = 2026, month = 1, day = 1, hour = 0, minute = 0, second = 0;
};
struct Alarm {
  DateTime when;
  bool enabled = false, daily = false;
};
bool schedule(unsigned id, const Alarm &alarm);
bool after(unsigned id, u32 seconds);
Alarm alarm(unsigned id);
bool take_alarm(unsigned &id);
void restore_alarms(const u32 epochs[2], u8 flags);
void save_alarms(u32 epochs[2], u8 &flags);
bool valid(const DateTime &date);
unsigned month_days(int year, int month);
u32 epoch(const DateTime &date);
DateTime from_epoch(u32 seconds);
void init();
bool set(const DateTime &date);
DateTime get();
bool configured();
void service();
void calibrate(int ppm);
int calibration();
u32 fat_time();
bool command(u8 id, const char *arguments);
} // namespace clock
} // namespace picocalc
#endif

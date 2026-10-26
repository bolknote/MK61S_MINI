#ifndef MK61_RTC_CLOCK_HPP
#define MK61_RTC_CLOCK_HPP

#include "rtc_backup_layout.hpp"
#include "rtc_clock_core.hpp"

namespace rtc_clock {

bool prepare_display_gpio(void);
void init(void);
bool is_set(void);
bool read_clock_source(ClockSource& out);
i16 calibration_ppm(void);
bool set_calibration_ppm(i16 ppm);
bool startup_snapshot(StartupSnapshot& out);
bool read(DateTime& out);
bool set(const DateTime& value);

using AlarmId = rtc_backup_layout::AlarmId;
using Alarm = rtc_backup_layout::Alarm;
using Repeat = rtc_backup_layout::Repeat;
using WakeReason = rtc_backup_layout::WakeReason;

struct BackupStatus {
  bool valid;
  bool valid_at_boot;
  u8 alarm_arm_failures;
  u32 boot_count;
  u32 reset_flags;
  WakeReason last_wake;
  bool previous_power_unstable;
};

struct AlarmEvent {
  AlarmId id;
  bool missed;
  DateTime observed;
};

bool schedule_alarm(AlarmId id, const Alarm& alarm);
bool schedule_after(AlarmId id, u32 seconds);
bool cancel_alarm(AlarmId id);
bool read_alarm(AlarmId id, Alarm& out);
bool backup_status(BackupStatus& out);

// Exclusive RTC wakeup-timer lease for bounded STOP qualification. Alarm A/B
// remain independent and may wake the same STOP interval. The call refuses an
// already active wakeup timer instead of stealing it from another owner.
bool arm_stop_wakeup(u8 seconds);
bool stop_wakeup_pending(void);
bool alarm_wakeup_pending(void);
bool disarm_stop_wakeup(void);

// IRQ callbacks only publish a bit. Validation of month/year, one-shot
// cancellation, metadata update and all user-visible work happen here.
void poll(void);
bool take_alarm_event(AlarmEvent& out);

} // пространство имён rtc_clock

#endif

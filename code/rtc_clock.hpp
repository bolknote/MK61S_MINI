#ifndef MK61_RTC_CLOCK_HPP
#define MK61_RTC_CLOCK_HPP

#include "rtc_clock_core.hpp"

namespace rtc_clock {

enum class PoweroffLseResult : u8 {
  READY,
  UNSUPPORTED,
  NOT_INITIALIZED,
  TIME_NOT_SET,
  LSE_START_FAILED,
  SOURCE_SWITCH_FAILED,
  GPIO_RELEASE_FAILED
};

bool prepare_display_gpio(void);
void init(void);
bool is_set(void);
bool read_clock_source(ClockSource& out);
i16 calibration_ppm(void);
bool set_calibration_ppm(i16 ppm);
PoweroffLseResult switch_to_lse_for_poweroff(void);
bool startup_snapshot(StartupSnapshot& out);
bool read(DateTime& out);
bool set(const DateTime& value);

} // пространство имён rtc_clock

#endif

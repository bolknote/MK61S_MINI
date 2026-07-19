#ifndef MK61_RTC_CLOCK_HPP
#define MK61_RTC_CLOCK_HPP

#include "rtc_clock_core.hpp"

namespace rtc_clock {

void init(void);
bool is_set(void);
bool startup_snapshot(StartupSnapshot& out);
bool read(DateTime& out);
bool set(const DateTime& value);

} // namespace rtc_clock

#endif

#ifndef MK61_RTC_IDLE_CLOCK_HPP
#define MK61_RTC_IDLE_CLOCK_HPP

class MK61Display;

namespace rtc_idle_clock {

void poll(MK61Display& display, bool calculator_context, bool calculator_idle);
void hide(MK61Display& display);

} // пространство имён rtc_idle_clock

#endif

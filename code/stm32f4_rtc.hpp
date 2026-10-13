#ifndef MK61_STM32F4_RTC_HPP
#define MK61_STM32F4_RTC_HPP
#include <Arduino.h>
#include "rtc_clock_core.hpp"
#if defined(ARDUINO_ARCH_STM32) &&                                                     \
    (defined(STM32F401xC) || defined(STM32F401xE) || defined(STM32F411xE))
#define MK61_STM32F4_RTC_SUPPORTED 1
#else
#define MK61_STM32F4_RTC_SUPPORTED 0
#endif
#if MK61_STM32F4_RTC_SUPPORTED
namespace stm32f4_rtc {
bool begin(rtc_clock::ClockSource source, const rtc_clock::Prescalers *prescalers);
u32 backup_read(u32 index);
void backup_write(u32 index, u32 value);
bool prescalers(u32 asynchronous, u32 synchronous);
bool snapshot(RTC_TimeTypeDef &time, RTC_DateTypeDef &date);
bool set_calendar(const RTC_TimeTypeDef &time, const RTC_DateTypeDef &date);
bool smooth_calibration(u32 value);
bool deactivate_alarm(u32 id);
bool set_alarm(const RTC_AlarmTypeDef &alarm);
u32 alarm_irq();
bool arm_wakeup(u16 counter);
bool disarm_wakeup();
bool wakeup_pending();
void wakeup_irq();
} // namespace stm32f4_rtc
#endif
#endif

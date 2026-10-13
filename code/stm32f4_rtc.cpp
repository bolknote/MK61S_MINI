#include "stm32f4_rtc.hpp"
#if MK61_STM32F4_RTC_SUPPORTED
#include <stddef.h>
namespace stm32f4_rtc {
namespace {
static volatile bool timer_pending;
static void unlock() {
  RTC->WPR = 0xCA;
  RTC->WPR = 0x53;
}
static void lock() {
  RTC->WPR = 0xFF;
}
static bool wait(u32 mask, bool set) {
  const u32 started = millis();
  while (((RTC->ISR & mask) != 0) != set) {
    if ((u32)(millis() - started) >= 1000U)
      return false;
    yield();
  }
  return true;
}
static void clear_flags(u32 flags) {
  // W0C: preserve other IRQ flags even if hardware sets one concurrently.
  RTC->ISR = ~(flags | RTC_ISR_INIT) | (RTC->ISR & RTC_ISR_INIT);
}
static bool enter_init() {
  if ((RTC->ISR & RTC_ISR_INIT) == 0 && !wait(RTC_ISR_INITF, false))
    return false;
  RTC->ISR = 0xFFFFFFFFUL; // INIT=1; W0C interrupt flags remain untouched.
  return wait(RTC_ISR_INITF, true);
}
static bool exit_init() {
  RTC->ISR = ~RTC_ISR_INIT;
  if (!wait(RTC_ISR_INITF, false))
    return false;
  // ES0287 2.8.4 requires shadow synchronization after INIT exit, even when
  // ordinary calendar reads use BYPSHAD. A second INIT must not race RTCCLK.
  const u32 bypass = RTC->CR & RTC_CR_BYPSHAD;
  RTC->CR &= ~RTC_CR_BYPSHAD;
  clear_flags(RTC_ISR_RSF);
  const bool synchronized = wait(RTC_ISR_RSF, true);
  RTC->CR |= bypass;
  return synchronized;
}
static u8 bcd(u8 value) {
  return (u8)(((value / 10U) << 4) | (value % 10U));
}
static u8 binary(u32 value) {
  return (u8)(((value >> 4) & 15U) * 10U + (value & 15U));
}
static volatile u32 &backup(u32 index) {
  return *reinterpret_cast<volatile u32 *>(RTC_BASE + offsetof(RTC_TypeDef, BKP0R) +
                                           index * sizeof(u32));
}
static void backup_access() {
  RCC->APB1ENR |= RCC_APB1ENR_PWREN;
  (void)RCC->APB1ENR;
  PWR->CR |= PWR_CR_DBP;
  // ES0287 2.2.9: perform the DBP read-back before backup-domain writes.
  while ((PWR->CR & PWR_CR_DBP) == 0) {
  }
}
} // namespace
u32 backup_read(u32 index) {
  backup_access();
  return index < 20 ? backup(index) : 0;
}
void backup_write(u32 index, u32 value) {
  backup_access();
  if (index < 20)
    backup(index) = value;
}
bool snapshot(RTC_TimeTypeDef &time, RTC_DateTypeDef &date) {
  // Bypass shadow mode avoids ES0287 2.8.2. Re-read the calendar and downcounter
  // across rollover so TR/DR/SSR describe one instant, including at midnight.
  for (u8 retry = 0; retry < 8; ++retry) {
    const u32 first = RTC->SSR;
    const u32 tr = RTC->TR;
    const u32 dr = RTC->DR;
    const u32 last = RTC->SSR;
    const u32 verify_tr = RTC->TR;
    const u32 verify_dr = RTC->DR;
    if (last > first || tr != verify_tr || dr != verify_dr)
      continue;
    time.Hours = binary((tr >> 16) & 0x3FU);
    time.Minutes = binary((tr >> 8) & 0x7FU);
    time.Seconds = binary(tr & 0x7FU);
    time.SubSeconds = last;
    time.SecondFraction = RTC->PRER & RTC_PRER_PREDIV_S;
    date.Year = binary((dr >> 16) & 0xFFU);
    date.Month = binary((dr >> 8) & 0x1FU);
    date.Date = binary(dr & 0x3FU);
    date.WeekDay = (u8)((dr >> 13) & 7U);
    return true;
  }
  return false;
}
bool set_calendar(const RTC_TimeTypeDef &time, const RTC_DateTypeDef &date) {
  unlock();
  bool ok = enter_init();
  if (ok) {
    RTC->TR = ((u32)bcd(time.Hours) << 16) | ((u32)bcd(time.Minutes) << 8) |
              bcd(time.Seconds);
    RTC->DR = ((u32)bcd(date.Year) << 16) | ((u32)date.WeekDay << 13) |
              ((u32)bcd(date.Month) << 8) | bcd(date.Date);
  }
  const bool exited = exit_init();
  lock();
  return ok && exited;
}
bool prescalers(u32 asynchronous, u32 synchronous) {
  const u32 value = (asynchronous << RTC_PRER_PREDIV_A_Pos) | synchronous;
  if (RTC->PRER == value)
    return true;
  unlock();
  bool ok = enter_init();
  if (ok)
    RTC->PRER = value;
  const bool exited = exit_init();
  lock();
  return ok && exited && RTC->PRER == value;
}
bool begin(rtc_clock::ClockSource source, const rtc_clock::Prescalers *measured) {
  backup_access();
  const bool lse = source == rtc_clock::ClockSource::LSE;
  const u32 selected = lse ? RCC_BDCR_RTCSEL_0 : RCC_BDCR_RTCSEL_1;
  const bool was_initialized = (RTC->ISR & RTC_ISR_INITS) != 0;
  const bool changed = (RCC->BDCR & RCC_BDCR_RTCSEL) != selected;
  RTC_TimeTypeDef retained_time = {};
  RTC_DateTypeDef retained_date = {};
  const bool retain_calendar =
      was_initialized && snapshot(retained_time, retained_date);
  u32 retained_backup[20];
  if (changed) {
    for (u8 i = 0; i < 20; ++i)
      retained_backup[i] = backup(i);
    const u32 lse_config = RCC->BDCR & (RCC_BDCR_LSEON | RCC_BDCR_LSEBYP);
    RCC->BDCR |= RCC_BDCR_BDRST;
    RCC->BDCR &= ~RCC_BDCR_BDRST;
    RCC->BDCR = lse_config | selected;
  }
  if (lse)
    RCC->BDCR |= RCC_BDCR_LSEON;
  else
    RCC->CSR |= RCC_CSR_LSION;
  const u32 started = millis();
  while (lse ? (RCC->BDCR & RCC_BDCR_LSERDY) == 0 : (RCC->CSR & RCC_CSR_LSIRDY) == 0) {
    if ((u32)(millis() - started) >= 5000U)
      return false;
    yield();
  }
  RCC->BDCR |= selected | RCC_BDCR_RTCEN;
  if (changed)
    for (u8 i = 0; i < 20; ++i)
      backup(i) = retained_backup[i];
  rtc_clock::Prescalers dividers = {};
  if (measured)
    dividers = *measured;
  else if (!rtc_clock::prescalers_for_frequency(lse ? 32768U : LSI_VALUE, dividers))
    return false;
  unlock();
  bool ok = true;
  if (changed || !was_initialized) {
    ok = enter_init();
    if (ok) {
      RTC->CR = RTC_CR_BYPSHAD; // 24h, no RTC pin output or callback machinery.
      RTC->PRER =
          ((u32)dividers.asynchronous << RTC_PRER_PREDIV_A_Pos) | dividers.synchronous;
      RTC->TR = retain_calendar ? ((u32)bcd(retained_time.Hours) << 16) |
                                      ((u32)bcd(retained_time.Minutes) << 8) |
                                      bcd(retained_time.Seconds)
                                : 0;
      RTC->DR = retain_calendar
                    ? ((u32)bcd(retained_date.Year) << 16) |
                          ((u32)retained_date.WeekDay << 13) |
                          ((u32)bcd(retained_date.Month) << 8) | bcd(retained_date.Date)
                    : 0x0001C101U; // Same unset 2001-01-01 calendar.
    }
    const bool exited = exit_init();
    ok = ok && exited;
  } else
    RTC->CR |= RTC_CR_BYPSHAD;
  lock();
  return ok && (!measured || prescalers(dividers.asynchronous, dividers.synchronous));
}
bool smooth_calibration(u32 value) {
  unlock();
  const bool ok = wait(RTC_ISR_RECALPF, false);
  if (ok)
    RTC->CALR = value;
  lock();
  return ok;
}
bool deactivate_alarm(u32 id) {
  const bool b = id == RTC_ALARM_B;
  const u32 enable = b ? RTC_CR_ALRBE : RTC_CR_ALRAE;
  const u32 interrupt = b ? RTC_CR_ALRBIE : RTC_CR_ALRAIE;
  unlock();
  RTC->CR &= ~(enable | interrupt);
  const bool ok = wait(b ? RTC_ISR_ALRBWF : RTC_ISR_ALRAWF, true);
  clear_flags(b ? RTC_ISR_ALRBF : RTC_ISR_ALRAF);
  lock();
  return ok;
}
bool set_alarm(const RTC_AlarmTypeDef &alarm) {
  if (!deactivate_alarm(alarm.Alarm))
    return false;
  const bool b = alarm.Alarm == RTC_ALARM_B;
  unlock();
  const u32 ar = ((u32)bcd(alarm.AlarmDateWeekDay) << 24) |
                 ((u32)bcd(alarm.AlarmTime.Hours) << 16) |
                 ((u32)bcd(alarm.AlarmTime.Minutes) << 8) |
                 bcd(alarm.AlarmTime.Seconds) | alarm.AlarmMask;
  const u32 ss = alarm.AlarmTime.SubSeconds | alarm.AlarmSubSecondMask;
  if (b) {
    RTC->ALRMBR = ar;
    RTC->ALRMBSSR = ss;
  } else {
    RTC->ALRMAR = ar;
    RTC->ALRMASSR = ss;
  }
  EXTI->IMR |= (1UL << 17);
  EXTI->RTSR |= (1UL << 17);
  RTC->CR |= b ? (RTC_CR_ALRBE | RTC_CR_ALRBIE) : (RTC_CR_ALRAE | RTC_CR_ALRAIE);
  lock();
  NVIC_SetPriority(RTC_Alarm_IRQn, 2);
  NVIC_EnableIRQ(RTC_Alarm_IRQn);
  return true;
}
u32 alarm_irq() {
  // ES0287 2.8.3: clear EXTI first, drain the APB write, then inspect both
  // alarm sources. Clearing EXTI at the end can lose the other alarm edge.
  EXTI->PR = (1UL << 17);
  (void)EXTI->PR;
  __DSB();
  u32 events = 0;
  // Reinspect A after clearing B: an A edge while the shared line is already
  // high does not generate another EXTI rising edge (same erratum).
  for (u8 pass = 0; pass < 3; ++pass) {
    const u32 status = RTC->ISR, control = RTC->CR;
    u32 current = 0;
    if ((status & RTC_ISR_ALRAF) && (control & RTC_CR_ALRAIE))
      current |= 1;
    if ((status & RTC_ISR_ALRBF) && (control & RTC_CR_ALRBIE))
      current |= 2;
    if (current == 0)
      return events;
    events |= current;
    clear_flags((current & 1 ? RTC_ISR_ALRAF : 0) | (current & 2 ? RTC_ISR_ALRBF : 0));
    __DSB();
  }
  NVIC_SetPendingIRQ(RTC_Alarm_IRQn);
  return events;
}
bool arm_wakeup(u16 counter) {
  if ((RTC->CR & RTC_CR_WUTE) != 0)
    return false;
  unlock();
  bool ok = wait(RTC_ISR_WUTWF, true);
  if (ok) {
    timer_pending = false;
    clear_flags(RTC_ISR_WUTF);
    RTC->CR &= ~RTC_CR_WUCKSEL; // RTCCLK/16.
    RTC->WUTR = counter;
    EXTI->PR = (1UL << 22);
    EXTI->IMR |= (1UL << 22);
    EXTI->RTSR |= (1UL << 22);
    NVIC_ClearPendingIRQ(RTC_WKUP_IRQn);
    RTC->CR |= RTC_CR_WUTE | RTC_CR_WUTIE;
    NVIC_SetPriority(RTC_WKUP_IRQn, 3);
    NVIC_EnableIRQ(RTC_WKUP_IRQn);
  }
  lock();
  return ok;
}
bool disarm_wakeup() {
  unlock();
  RTC->CR &= ~(RTC_CR_WUTE | RTC_CR_WUTIE);
  const bool ok = wait(RTC_ISR_WUTWF, true);
  clear_flags(RTC_ISR_WUTF);
  lock();
  timer_pending = false;
  EXTI->PR = (1UL << 22);
  NVIC_ClearPendingIRQ(RTC_WKUP_IRQn);
  return ok;
}
bool wakeup_pending() {
  return timer_pending || (RTC->ISR & RTC_ISR_WUTF) != 0;
}
void wakeup_irq() {
  EXTI->PR = (1UL << 22);
  (void)EXTI->PR;
  __DSB();
  if ((RTC->ISR & RTC_ISR_WUTF) && (RTC->CR & RTC_CR_WUTIE))
    timer_pending = true;
  clear_flags(RTC_ISR_WUTF);
}
} // namespace stm32f4_rtc
extern "C" void RTC_WKUP_IRQHandler() {
  stm32f4_rtc::wakeup_irq();
}
#endif

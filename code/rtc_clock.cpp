#include "rtc_clock.hpp"

#include <STM32RTC.h>
#include <backup.h>

#include "config.h"
#include "debug.h"

namespace rtc_clock {
namespace {

// DR1 is reserved by the STM32 core RTC convention and DR4 by its HID
// bootloader. DR2 is free on STM32F401/F411 and survives on VBAT.
static constexpr u32 TIME_SET_MARKER = 0x4D4B5254UL; // "MKRT"
static bool initialized = false;

#if defined(LSE_STARTUP_TIMEOUT)
static constexpr u32 LSE_TIMEOUT_MS = LSE_STARTUP_TIMEOUT;
#else
static constexpr u32 LSE_TIMEOUT_MS = 5000;
#endif
static constexpr u32 LSE_STOP_TIMEOUT_MS = 100;

STM32RTC& hardware_rtc(void) {
  return STM32RTC::getInstance();
}

RTC_HandleTypeDef* rtc_handle(void) {
  return hardware_rtc().getHandle();
}

bool marker_is_set(void) {
  return HAL_RTCEx_BKUPRead(rtc_handle(), RTC_BKP_DR2) == TIME_SET_MARKER;
}

void write_marker(u32 value) {
  // The duplicate call follows the STM32 core backup-domain helper and makes
  // sure the DBP write has crossed the APB/AHB bridge before the backup write.
  HAL_PWR_EnableBkUpAccess();
  HAL_PWR_EnableBkUpAccess();
  HAL_RTCEx_BKUPWrite(rtc_handle(), RTC_BKP_DR2, value);
}

bool wait_for_lse_flag(bool ready, u32 timeout_ms) {
  const u32 started_ms = millis();
  while((__HAL_RCC_GET_FLAG(RCC_FLAG_LSERDY) != RESET) != ready) {
    if((u32) (millis() - started_ms) >= timeout_ms) return false;
    yield();
  }
  return true;
}

bool lse_gpio_is_released(void) {
  return (RCC->BDCR & RCC_BDCR_LSEON) == 0 &&
         __HAL_RCC_GET_FLAG(RCC_FLAG_LSERDY) == RESET;
}

bool disable_retained_lse_for_gpio(void) {
  if(MK61_RTC_LSE_AVAILABLE) return true;

  enableBackupDomain();
  const bool was_enabled = (RCC->BDCR & RCC_BDCR_LSEON) != 0;
  if(retained_lse_must_be_disabled(MK61_RTC_LSE_AVAILABLE, was_enabled)) {
    dbgln(SPIROM, "RTC init: disabling retained LSE to release PC15");
  }

  // LSEON is in the backup domain and survives an ordinary MCU reset and
  // reflashing. STM32F4 HAL even preserves it while changing RTCSEL to LSI,
  // which leaves OSC32_OUT unavailable as LCD DB7 unless we clear it first.
  __HAL_RCC_LSE_CONFIG(RCC_LSE_OFF);
  if(wait_for_lse_flag(false, LSE_STOP_TIMEOUT_MS)) {
    dbgln(SPIROM, "RTC init: LSE off, PC15 released");
    return true;
  }

  // A stuck backup-domain configuration must not permanently sacrifice the
  // display. This recovery is reached only when a normal LSE stop failed; the
  // RTC calendar is necessarily unusable while its clock cannot be stopped.
  dbgln(SPIROM, "RTC init: LSE stop timed out, resetting backup domain");
  __HAL_RCC_BACKUPRESET_FORCE();
  __HAL_RCC_BACKUPRESET_RELEASE();
  const bool stopped = wait_for_lse_flag(false, LSE_STOP_TIMEOUT_MS);
  if(stopped) dbgln(SPIROM, "RTC init: LSE off after backup reset");
  return stopped;
}

bool start_lse_without_fatal_handler(void) {
  if(!MK61_RTC_LSE_AVAILABLE) return false;

  // STM32duino's enableClock(LSE_CLOCK) calls Error_Handler() when the crystal
  // does not start. Preflight the oscillator ourselves, with a wrap-safe
  // deadline, and call STM32RTC only after LSERDY is known to be asserted.
  enableBackupDomain();
  if(__HAL_RCC_GET_FLAG(RCC_FLAG_LSERDY) != RESET) return true;

#if defined(__HAL_RCC_LSEDRIVE_CONFIG) && defined(RCC_LSEDRIVE_LOW)
  __HAL_RCC_LSEDRIVE_CONFIG(RCC_LSEDRIVE_LOW);
#endif
  __HAL_RCC_LSE_CONFIG(RCC_LSE_ON);
  if(!wait_for_lse_flag(true, LSE_TIMEOUT_MS)) {
    __HAL_RCC_LSE_CONFIG(RCC_LSE_OFF);
    return false;
  }
  return true;
}

} // namespace

void init(void) {
  if(initialized) return;
  dbgln(SPIROM, "RTC init: start");

  const bool lse_released = disable_retained_lse_for_gpio();
  if(!lse_released) {
    dbgln(SPIROM, "RTC init: WARNING, PC15 may remain owned by LSE");
  }
  const bool lse_ready = start_lse_without_fatal_handler();
  const ClockSource source =
      select_clock_source(MK61_RTC_LSE_AVAILABLE, lse_ready);
  STM32RTC& rtc = hardware_rtc();
  rtc.setClockSource(source == ClockSource::LSE
      ? STM32RTC::LSE_CLOCK
      : STM32RTC::LSI_CLOCK);
  rtc.begin(); // Preserve an already configured calendar and backup registers.
  if(!MK61_RTC_LSE_AVAILABLE && !lse_gpio_is_released() &&
     !disable_retained_lse_for_gpio()) {
    dbgln(SPIROM, "RTC init: WARNING, LSE returned after selecting LSI");
  }
  initialized = true;
  dbgln(SPIROM, "RTC init: ready, clock ",
        source == ClockSource::LSE ? "LSE" : "LSI");
}

bool is_set(void) {
  return initialized && marker_is_set();
}

bool startup_snapshot(StartupSnapshot& out) {
  if(!initialized) return false;

  RTC_TimeTypeDef time = {};
  RTC_DateTypeDef date = {};
  RTC_HandleTypeDef* handle = rtc_handle();

  // STM32 requires GetTime followed by GetDate to unlock the shadow registers;
  // this order also gives a coherent calendar snapshot across midnight.
  const HAL_StatusTypeDef time_status = HAL_RTC_GetTime(handle, &time, RTC_FORMAT_BIN);
  const HAL_StatusTypeDef date_status = HAL_RTC_GetDate(handle, &date, RTC_FORMAT_BIN);
  if(time_status != HAL_OK || date_status != HAL_OK) return false;

  const StartupSnapshot current = {
    {
      (u16) (2000 + date.Year),
      date.Month,
      date.Date,
      time.Hours,
      time.Minutes,
      time.Seconds
    },
    time.SubSeconds,
    time.SecondFraction,
    marker_is_set()
  };
  if(!is_valid(current)) return false;
  out = current;
  return true;
}

bool read(DateTime& out) {
  StartupSnapshot snapshot = {};
  if(!startup_snapshot(snapshot) || !snapshot.time_set) return false;
  out = snapshot.date_time;
  return true;
}

bool set(const DateTime& value) {
  if(!initialized || !is_valid(value)) return false;

  RTC_DateTypeDef date = {};
  date.Year = (u8) (value.year - 2000);
  date.Month = value.month;
  date.Date = value.day;
  date.WeekDay = weekday(value);

  RTC_TimeTypeDef time = {};
  time.Hours = value.hour;
  time.Minutes = value.minute;
  time.Seconds = value.second;
  time.TimeFormat = RTC_HOURFORMAT12_AM;
  time.DayLightSaving = RTC_DAYLIGHTSAVING_NONE;
  time.StoreOperation = RTC_STOREOPERATION_RESET;

  RTC_HandleTypeDef* handle = rtc_handle();
  write_marker(0);
  if(HAL_RTC_SetDate(handle, &date, RTC_FORMAT_BIN) != HAL_OK) return false;
  if(HAL_RTC_SetTime(handle, &time, RTC_FORMAT_BIN) != HAL_OK) return false;
  write_marker(TIME_SET_MARKER);
  return marker_is_set();
}

} // namespace rtc_clock

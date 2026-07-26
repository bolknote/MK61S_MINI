#include "rtc_clock.hpp"

#include <STM32RTC.h>
#include <backup.h>

#include "config.h"
#include "debug.h"

namespace rtc_clock {
namespace {

// DR1 зарезервирован соглашениями RTC ядра STM32, а DR4 — его HID-загрузчиком.
// DR2 хранит признак установленного времени, DR3 — пользовательскую поправку
// хода. Оба регистра сохраняются при питании от VBAT.
static constexpr u32 TIME_SET_MARKER = 0x4D4B5254UL; // "MKRT"
static bool initialized = false;

struct PreservedBackupState {
  bool time_was_set;
  bool calibration_was_set;
  u32 calibration_record;
};

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

u32 backup_register_before_rtc_begin(u32 index) {
  // Обычная переменная RAM переживёт сброс только резервного домена, который
  // STM32RTC выполняет внутри begin() при смене источника LSE/LSI.
  enableBackupDomain();
  return getBackupRegister(index);
}

void write_backup_register(u32 index, u32 value) {
  // Повторный вызов соответствует вспомогательной функции домена резервного
  // питания ядра STM32 и гарантирует, что запись DBP прошла через мост APB/AHB
  // до записи в резервный регистр.
  HAL_PWR_EnableBkUpAccess();
  HAL_PWR_EnableBkUpAccess();
  HAL_RTCEx_BKUPWrite(rtc_handle(), index, value);
}

void write_marker(u32 value) {
  write_backup_register(RTC_BKP_DR2, value);
}

PreservedBackupState preserve_backup_state(void) {
  const bool time_was_set =
      backup_register_before_rtc_begin(LL_RTC_BKP_DR2) == TIME_SET_MARKER;
  const u32 calibration_record =
      backup_register_before_rtc_begin(LL_RTC_BKP_DR3);
  i16 calibration = 0;
  const bool calibration_was_set =
      decode_calibration_record(calibration_record, calibration);
  return {time_was_set, calibration_was_set, calibration_record};
}

void restore_backup_state(const PreservedBackupState& state) {
  if(state.time_was_set && !marker_is_set()) {
    // При смене RTCSEL библиотека возвращает календарь после сброса резервного
    // домена, но пользовательские backup-регистры не восстанавливает.
    write_marker(TIME_SET_MARKER);
    dbgln(SPIROM, "RTC init: restored time-set marker after source change");
  }

  if(state.calibration_was_set &&
     HAL_RTCEx_BKUPRead(rtc_handle(), RTC_BKP_DR3) !=
       state.calibration_record) {
    write_backup_register(RTC_BKP_DR3, state.calibration_record);
    dbgln(SPIROM, "RTC init: restored calibration after source change");
  }
}

i16 stored_calibration_ppm(void) {
  i16 ppm = 0;
  const u32 record = HAL_RTCEx_BKUPRead(rtc_handle(), RTC_BKP_DR3);
  return decode_calibration_record(record, ppm) ? ppm : 0;
}

bool apply_smooth_calibration(i16 ppm) {
  SmoothCalibration calibration = {};
  if(!smooth_calibration_for_ppm(ppm, calibration)) return false;

  const u32 plus = calibration.plus_512_pulses
      ? RTC_SMOOTHCALIB_PLUSPULSES_SET
      : RTC_SMOOTHCALIB_PLUSPULSES_RESET;
  const u32 desired = plus | calibration.minus_pulses;
  const u32 mask = RTC_CALR_CALP | RTC_CALR_CALW8 |
                   RTC_CALR_CALW16 | RTC_CALR_CALM;
  if((rtc_handle()->Instance->CALR & mask) == desired) return true;

  return HAL_RTCEx_SetSmoothCalib(
      rtc_handle(), RTC_SMOOTHCALIB_PERIOD_32SEC, plus,
      calibration.minus_pulses) == HAL_OK;
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

bool hardware_uses_clock_source(ClockSource source) {
  const u32 selected = __HAL_RCC_GET_RTC_SOURCE();
  return selected == (source == ClockSource::LSE
      ? RCC_RTCCLKSOURCE_LSE
      : RCC_RTCCLKSOURCE_LSI);
}

bool disable_retained_lse_for_gpio(void) {
  if(MK61_RTC_LSE_AVAILABLE) return true;

  enableBackupDomain();
  const bool was_enabled = (RCC->BDCR & RCC_BDCR_LSEON) != 0;
  if(retained_lse_must_be_disabled(MK61_RTC_LSE_AVAILABLE, was_enabled)) {
    dbgln(SPIROM, "RTC init: disabling retained LSE to release PC15");
  }

  // LSEON находится в домене резервного питания и сохраняется при обычном
  // сбросе МК и перепрошивке. HAL STM32F4 сохраняет его даже при переключении
  // RTCSEL на LSI, поэтому OSC32_OUT остаётся недоступным как DB7 ЖКИ, пока мы
  // явно не сбросим этот бит.
  __HAL_RCC_LSE_CONFIG(RCC_LSE_OFF);
  if(wait_for_lse_flag(false, LSE_STOP_TIMEOUT_MS)) {
    dbgln(SPIROM, "RTC init: LSE off, PC15 released");
    return true;
  }

  // Зависшая конфигурация домена резервного питания не должна навсегда лишать
  // устройство дисплея. Это восстановление выполняется только после неудачной
  // штатной остановки LSE; календарь RTC всё равно непригоден, пока его тактовый
  // генератор невозможно остановить.
  dbgln(SPIROM, "RTC init: LSE stop timed out, resetting backup domain");
  __HAL_RCC_BACKUPRESET_FORCE();
  __HAL_RCC_BACKUPRESET_RELEASE();
  const bool stopped = wait_for_lse_flag(false, LSE_STOP_TIMEOUT_MS);
  if(stopped) dbgln(SPIROM, "RTC init: LSE off after backup reset");
  return stopped;
}

bool start_lse_without_fatal_handler(bool allow_shared_lcd_pin = false) {
  bool allowed = MK61_RTC_LSE_AVAILABLE;
#if MK61_V2_RTC_POWEROFF_HANDOFF
  allowed = allowed || allow_shared_lcd_pin;
#else
  (void) allow_shared_lcd_pin;
#endif
  if(!allowed) return false;

  // enableClock(LSE_CLOCK) из STM32duino вызывает Error_Handler(), если кварц
  // не запускается. Поэтому предварительно проверяем генератор сами, используя
  // устойчивый к переполнению тайм-аут, и обращаемся к STM32RTC лишь после того,
  // как LSERDY гарантированно установился.
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

void begin_with_clock_source(ClockSource source,
                             const PreservedBackupState& backup) {
  STM32RTC& rtc = hardware_rtc();
  rtc.setClockSource(source == ClockSource::LSE
      ? STM32RTC::LSE_CLOCK
      : STM32RTC::LSI_CLOCK);
  rtc.begin();
  restore_backup_state(backup);
}

#if MK61_V2_RTC_POWEROFF_HANDOFF
bool restore_lsi_after_failed_poweroff(
    const PreservedBackupState& backup) {
  begin_with_clock_source(ClockSource::LSI, backup);
  const bool source_restored =
      hardware_uses_clock_source(ClockSource::LSI);
  const bool calibration_restored =
      apply_smooth_calibration(stored_calibration_ppm());
  const bool gpio_released = disable_retained_lse_for_gpio();
  return source_restored && calibration_restored && gpio_released;
}
#endif

} // анонимное пространство имён

bool prepare_display_gpio(void) {
  const bool released = disable_retained_lse_for_gpio();
  if(!released) {
    dbgln(SPIROM, "RTC init: WARNING, PC15 may remain owned by LSE");
  }
  return released;
}

void init(void) {
  if(initialized) return;
  dbgln(SPIROM, "RTC init: start");

  prepare_display_gpio();
  const bool lse_ready = start_lse_without_fatal_handler();
  const ClockSource source =
      select_clock_source(MK61_RTC_LSE_AVAILABLE, lse_ready);
  const PreservedBackupState backup = preserve_backup_state();
  begin_with_clock_source(source, backup);
  if(!MK61_RTC_LSE_AVAILABLE && !lse_gpio_is_released() &&
     !disable_retained_lse_for_gpio()) {
    dbgln(SPIROM, "RTC init: WARNING, LSE returned after selecting LSI");
  }
  if(!apply_smooth_calibration(stored_calibration_ppm())) {
    dbgln(SPIROM, "RTC init: WARNING, calibration was not applied");
  }
  initialized = true;
  dbgln(SPIROM, "RTC init: ready, clock ",
        source == ClockSource::LSE ? "LSE" : "LSI");
}

bool is_set(void) {
  return initialized && marker_is_set();
}

bool read_clock_source(ClockSource& out) {
  if(!initialized) return false;
  if(hardware_uses_clock_source(ClockSource::LSE)) {
    out = ClockSource::LSE;
    return true;
  }
  if(hardware_uses_clock_source(ClockSource::LSI)) {
    out = ClockSource::LSI;
    return true;
  }
  return false;
}

i16 calibration_ppm(void) {
  return initialized ? stored_calibration_ppm() : 0;
}

bool set_calibration_ppm(i16 ppm) {
  if(!initialized || !calibration_ppm_is_valid(ppm)) return false;

  const u32 old_record =
      HAL_RTCEx_BKUPRead(rtc_handle(), RTC_BKP_DR3);
  const i16 old_ppm = stored_calibration_ppm();
  if(!apply_smooth_calibration(ppm)) return false;

  const u32 new_record = encode_calibration_record(ppm);
  write_backup_register(RTC_BKP_DR3, new_record);
  if(HAL_RTCEx_BKUPRead(rtc_handle(), RTC_BKP_DR3) == new_record) {
    return true;
  }

  write_backup_register(RTC_BKP_DR3, old_record);
  (void) apply_smooth_calibration(old_ppm);
  return false;
}

PoweroffLseResult switch_to_lse_for_poweroff(void) {
#if !MK61_V2_RTC_POWEROFF_HANDOFF
  return PoweroffLseResult::UNSUPPORTED;
#else
  if(!initialized) return PoweroffLseResult::NOT_INITIALIZED;

  DateTime before = {};
  if(!marker_is_set() || !read(before)) {
    return PoweroffLseResult::TIME_NOT_SET;
  }

  const PreservedBackupState backup = preserve_backup_state();
  dbgln(SPIROM, "RTC poweroff: starting LSE on shared PC15");
  if(!start_lse_without_fatal_handler(true)) {
    dbgln(SPIROM, "RTC poweroff: LSE failed to start");
    return disable_retained_lse_for_gpio()
        ? PoweroffLseResult::LSE_START_FAILED
        : PoweroffLseResult::GPIO_RELEASE_FAILED;
  }

  // STM32duino переносит календарь при смене RTCSEL. Пользовательская поправка
  // V2 относится к неточному LSI, поэтому для резервного хода от кварца LSE
  // сбрасываем аппаратную smooth calibration, но сохраняем её запись для
  // возврата на LSI при следующем включении.
  begin_with_clock_source(ClockSource::LSE, backup);
  DateTime after = {};
  const bool switched =
      __HAL_RCC_GET_FLAG(RCC_FLAG_LSERDY) != RESET &&
      hardware_uses_clock_source(ClockSource::LSE) &&
      read(after) &&
      apply_smooth_calibration(0);
  if(switched) {
    dbgln(SPIROM, "RTC poweroff: LSE ready");
    return PoweroffLseResult::READY;
  }

  dbgln(SPIROM, "RTC poweroff: source switch failed, restoring LSI");
  if(!restore_lsi_after_failed_poweroff(backup) &&
     !lse_gpio_is_released()) {
    return PoweroffLseResult::GPIO_RELEASE_FAILED;
  }
  return PoweroffLseResult::SOURCE_SWITCH_FAILED;
#endif
}

bool startup_snapshot(StartupSnapshot& out) {
  if(!initialized) return false;

  RTC_TimeTypeDef time = {};
  RTC_DateTypeDef date = {};
  RTC_HandleTypeDef* handle = rtc_handle();

  // STM32 требует вызвать GetTime, а затем GetDate для разблокировки теневых
  // регистров; такой порядок также даёт согласованный снимок календаря при
  // переходе через полночь.
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

} // пространство имён rtc_clock

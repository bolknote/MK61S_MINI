#include "rtc_clock.hpp"

#include <STM32RTC.h>
#include <backup.h>

#include "config.h"
#include "crash_dump.hpp"
#include "debug.h"
#include "power_monitor.hpp"

namespace rtc_clock {
namespace {

// DR1 зарезервирован соглашениями RTC ядра STM32, DR4/DR10 — текущим и старым
// HID-загрузчиком. DR2 хранит признак установленного времени, DR3 — поправку
// хода. Версионированная запись проекта занимает только DR11..DR19.
static constexpr u32 TIME_SET_MARKER = 0x4D4B5254UL; // "MKRT"
static bool initialized = false;
static bool metadata_valid_at_boot = false;
static volatile u32 pending_alarm_irqs = 0;
static u8 pending_alarm_events = 0;
static u8 missed_alarm_events = 0;
static u8 alarm_arm_failures = 0;

#if defined(RTC_BKP_NUMBER)
static_assert(RTC_BKP_NUMBER >= 20,
              "F401/F411 RTC metadata requires DR0..DR19");
#endif
static_assert(rtc_backup_layout::FIRST_REGISTER == 11 &&
              rtc_backup_layout::LAST_REGISTER == 19,
              "RTC backup window must remain DR11..DR19");

struct PreservedBackupState {
  bool time_was_set;
  bool calibration_was_set;
  u32 calibration_record;
  bool metadata_was_valid;
  rtc_backup_layout::Words metadata_words;
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

rtc_backup_layout::Words read_metadata_words(void) {
  rtc_backup_layout::Words words = {};
  for(u8 index = 0; index < rtc_backup_layout::WORD_COUNT; index++) {
    words.value[index] = HAL_RTCEx_BKUPRead(
        rtc_handle(), rtc_backup_layout::FIRST_REGISTER + index);
  }
  return words;
}

rtc_backup_layout::Words read_metadata_words_before_rtc_begin(void) {
  rtc_backup_layout::Words words = {};
  for(u8 index = 0; index < rtc_backup_layout::WORD_COUNT; index++) {
    words.value[index] = backup_register_before_rtc_begin(
        rtc_backup_layout::FIRST_REGISTER + index);
  }
  return words;
}

bool read_metadata(rtc_backup_layout::Metadata& out) {
  return rtc_backup_layout::decode(read_metadata_words(), out);
}

bool write_metadata(const rtc_backup_layout::Metadata& metadata) {
  rtc_backup_layout::Words words = {};
  if(!rtc_backup_layout::encode(metadata, words)) return false;

  // Transactional commit in retention registers: invalidate first, write the
  // whole body/checksum, then publish the versioned header last. A reset or
  // power loss at any intermediate point leaves a record that decode rejects.
  write_backup_register(rtc_backup_layout::FIRST_REGISTER +
                        rtc_backup_layout::WORD_HEADER, 0);
  for(u8 index = 1; index < rtc_backup_layout::WORD_COUNT; index++) {
    write_backup_register(rtc_backup_layout::FIRST_REGISTER + index,
                          words.value[index]);
  }
  write_backup_register(rtc_backup_layout::FIRST_REGISTER +
                        rtc_backup_layout::WORD_HEADER,
                        words.value[rtc_backup_layout::WORD_HEADER]);

  const rtc_backup_layout::Words verified = read_metadata_words();
  for(u8 index = 0; index < rtc_backup_layout::WORD_COUNT; index++) {
    if(verified.value[index] != words.value[index]) return false;
  }
  return true;
}

void restore_metadata_words(const rtc_backup_layout::Words& words) {
  write_backup_register(rtc_backup_layout::FIRST_REGISTER +
                        rtc_backup_layout::WORD_HEADER, 0);
  for(u8 index = 1; index < rtc_backup_layout::WORD_COUNT; index++) {
    write_backup_register(rtc_backup_layout::FIRST_REGISTER + index,
                          words.value[index]);
  }
  write_backup_register(rtc_backup_layout::FIRST_REGISTER +
                        rtc_backup_layout::WORD_HEADER,
                        words.value[rtc_backup_layout::WORD_HEADER]);
}

PreservedBackupState preserve_backup_state(void) {
  const bool time_was_set =
      backup_register_before_rtc_begin(LL_RTC_BKP_DR2) == TIME_SET_MARKER;
  const u32 calibration_record =
      backup_register_before_rtc_begin(LL_RTC_BKP_DR3);
  i16 calibration = 0;
  const bool calibration_was_set =
      decode_calibration_record(calibration_record, calibration);
  const rtc_backup_layout::Words metadata_words =
      read_metadata_words_before_rtc_begin();
  rtc_backup_layout::Metadata metadata = {};
  const bool metadata_was_valid =
      rtc_backup_layout::decode(metadata_words, metadata);
  return {time_was_set, calibration_was_set, calibration_record,
          metadata_was_valid, metadata_words};
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

  rtc_backup_layout::Metadata current = {};
  if(state.metadata_was_valid && !read_metadata(current)) {
    restore_metadata_words(state.metadata_words);
    dbgln(SPIROM, "RTC init: restored metadata after source change");
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

u8 alarm_index(rtc_backup_layout::AlarmId id) {
  return id == rtc_backup_layout::AlarmId::B ? 1 : 0;
}

u32 alarm_event_bit(rtc_backup_layout::AlarmId id) {
  return 1UL << alarm_index(id);
}

u32 hardware_alarm_id(rtc_backup_layout::AlarmId id) {
#if defined(RTC_ALARM_B)
  return id == rtc_backup_layout::AlarmId::B ? RTC_ALARM_B : RTC_ALARM_A;
#else
  return id == rtc_backup_layout::AlarmId::A ? RTC_ALARM_A : 0xFFFFFFFFUL;
#endif
}

void alarm_a_callback(void*) {
  __atomic_fetch_or(&pending_alarm_irqs,
                    alarm_event_bit(rtc_backup_layout::AlarmId::A),
                    __ATOMIC_RELEASE);
}

#if defined(RTC_ALARM_B)
void alarm_b_callback(void*) {
  __atomic_fetch_or(&pending_alarm_irqs,
                    alarm_event_bit(rtc_backup_layout::AlarmId::B),
                    __ATOMIC_RELEASE);
}
#endif

void increment_alarm_arm_failures(void) {
  if(alarm_arm_failures != 0xFFU) alarm_arm_failures++;
}

bool disable_hardware_alarm(rtc_backup_layout::AlarmId id) {
  const u32 hardware_id = hardware_alarm_id(id);
  if(hardware_id == 0xFFFFFFFFUL) return false;
  return HAL_RTC_DeactivateAlarm(rtc_handle(), hardware_id) == HAL_OK;
}

bool arm_hardware_alarm(rtc_backup_layout::AlarmId id,
                        const rtc_backup_layout::Alarm& alarm) {
  if(!rtc_backup_layout::valid_alarm(alarm)) return false;
  if(!alarm.enabled) return disable_hardware_alarm(id);
  const u32 hardware_id = hardware_alarm_id(id);
  if(hardware_id == 0xFFFFFFFFUL) return false;

  (void) HAL_RTC_DeactivateAlarm(rtc_handle(), hardware_id);
  RTC_AlarmTypeDef value = {};
  value.AlarmTime.Hours = alarm.when.hour;
  value.AlarmTime.Minutes = alarm.when.minute;
  value.AlarmTime.Seconds = alarm.when.second;
  value.AlarmTime.TimeFormat = RTC_HOURFORMAT12_AM;
  value.AlarmTime.DayLightSaving = RTC_DAYLIGHTSAVING_NONE;
  value.AlarmTime.StoreOperation = RTC_STOREOPERATION_RESET;
  value.AlarmMask = alarm.repeat == rtc_backup_layout::Repeat::DAILY
      ? RTC_ALARMMASK_DATEWEEKDAY : RTC_ALARMMASK_NONE;
  if(alarm.millisecond == rtc_backup_layout::MILLISECOND_IGNORED) {
    value.AlarmTime.SubSeconds = 0;
    value.AlarmSubSecondMask = RTC_ALARMSUBSECONDMASK_ALL;
  } else {
    const u32 fraction = rtc_handle()->Instance->PRER & RTC_PRER_PREDIV_S;
    u32 significant_bits = 0;
    for(u32 bits = fraction; bits != 0; bits >>= 1) significant_bits++;
    if(significant_bits == 0 || significant_bits > 15) return false;
    value.AlarmTime.SubSeconds = fraction -
        ((u32) alarm.millisecond * (fraction + 1U)) / 1000U;
    value.AlarmSubSecondMask =
        significant_bits << RTC_ALRMASSR_MASKSS_Pos;
  }
  value.AlarmDateWeekDay = alarm.repeat == rtc_backup_layout::Repeat::DAILY
      ? 1 : alarm.when.day;
  value.AlarmDateWeekDaySel = RTC_ALARMDATEWEEKDAYSEL_DATE;
  value.Alarm = hardware_id;
  if(HAL_RTC_SetAlarm_IT(rtc_handle(), &value, RTC_FORMAT_BIN) != HAL_OK) {
    return false;
  }
  HAL_NVIC_SetPriority(RTC_Alarm_IRQn, RTC_IRQ_PRIO, RTC_IRQ_SUBPRIO);
  HAL_NVIC_EnableIRQ(RTC_Alarm_IRQn);
  return true;
}

void attach_alarm_callbacks(void) {
  STM32RTC& rtc = hardware_rtc();
  rtc.attachInterrupt(alarm_a_callback, nullptr, STM32RTC::ALARM_A);
#if defined(RTC_ALARM_B)
  rtc.attachInterrupt(alarm_b_callback, nullptr, STM32RTC::ALARM_B);
#endif
}

i8 compare_snapshot_to_alarm(const StartupSnapshot& snapshot,
                             const rtc_backup_layout::Alarm& alarm) {
  const i8 calendar = rtc_backup_layout::compare(
      snapshot.date_time, alarm.when);
  if(calendar != 0 ||
     alarm.millisecond == rtc_backup_layout::MILLISECOND_IGNORED) {
    return calendar;
  }
  const u16 current = snapshot_milliseconds(snapshot);
  if(current == alarm.millisecond) return 0;
  return current < alarm.millisecond ? -1 : 1;
}

bool restore_scheduled_alarms(rtc_backup_layout::Metadata& metadata,
                              bool report_missed) {
  StartupSnapshot snapshot = {};
  if(!marker_is_set() || !startup_snapshot(snapshot) || !snapshot.time_set) {
    (void) disable_hardware_alarm(rtc_backup_layout::AlarmId::A);
    (void) disable_hardware_alarm(rtc_backup_layout::AlarmId::B);
    return true;
  }

  bool metadata_changed = false;
  bool hardware_ok = true;
  u8 restored_missed = 0;
  for(u8 index = 0; index < 2; index++) {
    const rtc_backup_layout::AlarmId id = index == 0
        ? rtc_backup_layout::AlarmId::A : rtc_backup_layout::AlarmId::B;
    rtc_backup_layout::Alarm& alarm = metadata.alarms[index];
    if(!alarm.enabled) {
      (void) disable_hardware_alarm(id);
      continue;
    }
    if(alarm.repeat == rtc_backup_layout::Repeat::ONE_SHOT &&
       compare_snapshot_to_alarm(snapshot, alarm) >= 0) {
      (void) disable_hardware_alarm(id);
      alarm = rtc_backup_layout::disabled_alarm();
      metadata_changed = true;
      if(report_missed) {
        const u8 bit = (u8) alarm_event_bit(id);
        pending_alarm_events |= bit;
        missed_alarm_events |= bit;
        restored_missed |= bit;
      }
      continue;
    }
    if(!arm_hardware_alarm(id, alarm)) {
      increment_alarm_arm_failures();
      hardware_ok = false;
    }
  }
  if(restored_missed != 0) {
    metadata.last_wake = restored_missed == 1
        ? rtc_backup_layout::WakeReason::MISSED_A
        : (restored_missed == 2
            ? rtc_backup_layout::WakeReason::MISSED_B
            : rtc_backup_layout::WakeReason::MISSED_BOTH);
  }
  const bool metadata_ok = !metadata_changed || write_metadata(metadata);
  return hardware_ok && metadata_ok;
}

void initialize_metadata(const PreservedBackupState& preserved) {
  metadata_valid_at_boot = preserved.metadata_was_valid;
  rtc_backup_layout::Metadata metadata = {};
  if(!read_metadata(metadata)) metadata = rtc_backup_layout::empty_metadata();
  metadata.boot_count = rtc_backup_layout::increment_saturated(
      metadata.boot_count);
  metadata.reset_flags = crash_dump::boot_reset_flags();
  metadata.last_wake = rtc_backup_layout::WakeReason::RESET;
  metadata.previous_power_unstable =
      power_monitor::snapshot().previous_unstable;
  if(!write_metadata(metadata)) {
    dbgln(SPIROM, "RTC metadata: write verification failed");
  }
  attach_alarm_callbacks();
  if(!restore_scheduled_alarms(metadata, true)) {
    dbgln(SPIROM, "RTC metadata: alarm restore failed");
  }
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

bool start_lse_without_fatal_handler(void) {
  if(!MK61_RTC_LSE_AVAILABLE) return false;

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
  initialize_metadata(backup);
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
  if(!marker_is_set()) return false;
  rtc_backup_layout::Metadata metadata = {};
  if(!read_metadata(metadata)) {
    metadata = rtc_backup_layout::empty_metadata();
    metadata.boot_count = 1;
    metadata.reset_flags = crash_dump::boot_reset_flags();
    metadata.last_wake = rtc_backup_layout::WakeReason::RESET;
    metadata.previous_power_unstable =
        power_monitor::snapshot().previous_unstable;
    if(!write_metadata(metadata)) {
      dbgln(SPIROM, "RTC metadata: repair after date set failed");
    }
    return true;
  }
  if(!restore_scheduled_alarms(metadata, true)) {
    // Setting the calendar succeeded. A separately reported alarm-arm error
    // must not make the Date UI claim that the clock itself was rejected.
    dbgln(SPIROM, "RTC metadata: re-arm after date set failed");
  }
  return true;
}

bool schedule_alarm(AlarmId id, const Alarm& requested) {
  if(!initialized || !marker_is_set() ||
     !rtc_backup_layout::valid_alarm(requested) || !requested.enabled) {
    return false;
  }
  Alarm alarm = requested;
  if(alarm.repeat == Repeat::DAILY) {
    alarm.when.year = 2000;
    alarm.when.month = 1;
    alarm.when.day = 1;
  } else {
    StartupSnapshot now = {};
    if(!startup_snapshot(now) || !now.time_set ||
       compare_snapshot_to_alarm(now, alarm) >= 0) {
      return false;
    }
  }

  rtc_backup_layout::Metadata metadata = {};
  if(!read_metadata(metadata)) return false;
  const u8 index = alarm_index(id);
  const Alarm previous = metadata.alarms[index];
  metadata.alarms[index] = alarm;
  if(!write_metadata(metadata)) return false;
  if(arm_hardware_alarm(id, alarm)) return true;

  increment_alarm_arm_failures();
  metadata.alarms[index] = previous;
  (void) write_metadata(metadata);
  (void) arm_hardware_alarm(id, previous);
  return false;
}

bool schedule_after(AlarmId id, u32 seconds) {
  if(seconds == 0) return false;
  StartupSnapshot now = {};
  DateTime target = {};
  if(!startup_snapshot(now) || !now.time_set ||
     !rtc_backup_layout::add_seconds(now.date_time, seconds, target)) {
    return false;
  }
  return schedule_alarm(id, {true, Repeat::ONE_SHOT, target,
                              snapshot_milliseconds(now)});
}

bool cancel_alarm(AlarmId id) {
  if(!initialized) return false;
  rtc_backup_layout::Metadata metadata = {};
  if(!read_metadata(metadata)) return false;
  const u8 index = alarm_index(id);
  const Alarm previous = metadata.alarms[index];
  metadata.alarms[index] = rtc_backup_layout::disabled_alarm();
  if(!write_metadata(metadata)) return false;
  if(disable_hardware_alarm(id)) return true;

  increment_alarm_arm_failures();
  metadata.alarms[index] = previous;
  (void) write_metadata(metadata);
  (void) arm_hardware_alarm(id, previous);
  return false;
}

bool read_alarm(AlarmId id, Alarm& out) {
  if(!initialized) return false;
  rtc_backup_layout::Metadata metadata = {};
  if(!read_metadata(metadata)) return false;
  out = metadata.alarms[alarm_index(id)];
  return true;
}

bool backup_status(BackupStatus& out) {
  rtc_backup_layout::Metadata metadata = {};
  const bool valid = initialized && read_metadata(metadata);
  out.valid = valid;
  out.valid_at_boot = metadata_valid_at_boot;
  out.alarm_arm_failures = alarm_arm_failures;
  out.boot_count = valid ? metadata.boot_count : 0;
  out.reset_flags = valid ? metadata.reset_flags : 0;
  out.last_wake = valid ? metadata.last_wake : WakeReason::UNKNOWN;
  out.previous_power_unstable =
      valid && metadata.previous_power_unstable;
  return valid;
}

bool arm_stop_wakeup(u8 seconds) {
#if defined(RTC_CR_WUTE) && defined(RTC_WAKEUPCLOCK_RTCCLK_DIV16) && \
    defined(RTC_PRER_PREDIV_A) && defined(RTC_PRER_PREDIV_S)
  if(!initialized || seconds == 0 || seconds > 5) return false;
  RTC_HandleTypeDef* const handle = rtc_handle();
  if((handle->Instance->CR & RTC_CR_WUTE) != 0) return false;

  const u32 prescalers = handle->Instance->PRER;
  const u32 prediv_async =
      (prescalers & RTC_PRER_PREDIV_A) >> RTC_PRER_PREDIV_A_Pos;
  const u32 prediv_sync = prescalers & RTC_PRER_PREDIV_S;
  u16 counter = 0;
  if(!rtc_clock::stop_wakeup_counter(
       prediv_async, prediv_sync, seconds, counter)) {
    return false;
  }

  __HAL_RTC_WAKEUPTIMER_CLEAR_FLAG(handle, RTC_FLAG_WUTF);
  __HAL_RTC_WAKEUPTIMER_EXTI_CLEAR_FLAG();
  HAL_NVIC_ClearPendingIRQ(RTC_WKUP_IRQn);
  if(HAL_RTCEx_SetWakeUpTimer_IT(
       handle, counter, RTC_WAKEUPCLOCK_RTCCLK_DIV16) != HAL_OK) {
    return false;
  }
  HAL_NVIC_SetPriority(RTC_WKUP_IRQn, 3, 0);
  HAL_NVIC_EnableIRQ(RTC_WKUP_IRQn);
  return true;
#else
  (void) seconds;
  return false;
#endif
}

bool stop_wakeup_pending(void) {
#if defined(RTC_FLAG_WUTF)
  return __HAL_RTC_WAKEUPTIMER_GET_FLAG(
      rtc_handle(), RTC_FLAG_WUTF) != RESET;
#else
  return false;
#endif
}

bool alarm_wakeup_pending(void) {
#if defined(RTC_FLAG_ALRAF)
  RTC_HandleTypeDef* const handle = rtc_handle();
  if(__HAL_RTC_ALARM_GET_FLAG(handle, RTC_FLAG_ALRAF) != RESET) return true;
  #if defined(RTC_FLAG_ALRBF)
  if(__HAL_RTC_ALARM_GET_FLAG(handle, RTC_FLAG_ALRBF) != RESET) return true;
  #endif
#endif
  return false;
}

bool disarm_stop_wakeup(void) {
#if defined(RTC_CR_WUTE)
  RTC_HandleTypeDef* const handle = rtc_handle();
  const bool ok = (handle->Instance->CR & RTC_CR_WUTE) == 0 ||
      HAL_RTCEx_DeactivateWakeUpTimer(handle) == HAL_OK;
  __HAL_RTC_WAKEUPTIMER_CLEAR_FLAG(handle, RTC_FLAG_WUTF);
  __HAL_RTC_WAKEUPTIMER_EXTI_CLEAR_FLAG();
  HAL_NVIC_ClearPendingIRQ(RTC_WKUP_IRQn);
  return ok;
#else
  return false;
#endif
}

void poll(void) {
  const u32 irq_events = __atomic_exchange_n(
      &pending_alarm_irqs, 0, __ATOMIC_ACQ_REL);
  if(irq_events == 0) return;

  rtc_backup_layout::Metadata metadata = {};
  if(!read_metadata(metadata)) return;
  StartupSnapshot snapshot = {};
  const bool have_time = startup_snapshot(snapshot) && snapshot.time_set;
  bool metadata_changed = false;

  for(u8 index = 0; index < 2; index++) {
    const AlarmId id = index == 0 ? AlarmId::A : AlarmId::B;
    const u8 bit = (u8) alarm_event_bit(id);
    if((irq_events & bit) == 0) continue;
    Alarm& alarm = metadata.alarms[index];
    if(!alarm.enabled) continue;

    if(alarm.repeat == Repeat::ONE_SHOT) {
      if(!have_time) {
        __atomic_fetch_or(&pending_alarm_irqs, bit, __ATOMIC_RELEASE);
        continue;
      }
      // STM32 hardware compares only day-of-month and time. An absolute alarm
      // for a future month/year may therefore wake early; metadata filters that
      // monthly candidate without exposing a false event.
      if(!rtc_backup_layout::hardware_candidate_is_due(snapshot, alarm)) {
        continue;
      }
      (void) disable_hardware_alarm(id);
      alarm = rtc_backup_layout::disabled_alarm();
    }

    pending_alarm_events |= bit;
    metadata.last_wake = id == AlarmId::A
        ? WakeReason::ALARM_A : WakeReason::ALARM_B;
    metadata_changed = true;
  }
  if(metadata_changed && !write_metadata(metadata)) {
    dbgln(SPIROM, "RTC metadata: event commit failed");
  }
}

bool take_alarm_event(AlarmEvent& out) {
  if(pending_alarm_events == 0) return false;
  const u8 bit = (pending_alarm_events & 1U) != 0 ? 1U : 2U;
  pending_alarm_events &= (u8) ~bit;
  out.id = bit == 1 ? AlarmId::A : AlarmId::B;
  out.missed = (missed_alarm_events & bit) != 0;
  missed_alarm_events &= (u8) ~bit;
  out.observed = {0, 0, 0, 0, 0, 0};
  (void) read(out.observed);
  return true;
}

} // пространство имён rtc_clock

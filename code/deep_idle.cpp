#include "deep_idle.hpp"

#if MK61_DEEP_IDLE_SUPPORTED
  #include <Arduino.h>
  #include <stm32f4xx.h>

  #include "display.hpp"
  #include "independent_watchdog.hpp"
  #include "keyboard.h"
  #include "rtc_clock.hpp"
  #include "usb_mass_storage.hpp"
  #include "usb_power.hpp"
#endif

namespace deep_idle {
namespace {

#if MK61_DEEP_IDLE_SUPPORTED

static deep_idle_policy::Controller controller;
static u32 not_before_ms;

static constexpr u32 START_DELAY_MS = 750;
static constexpr u32 MAX_ELAPSED_MARGIN_MS = 2000;

extern "C" void SystemClock_Config(void);

static bool time_reached(u32 now, u32 target) {
  return (i32) (now - target) >= 0;
}

static deep_idle_policy::WakeReason classify_wake(bool keyboard,
                                                   bool usb_host,
                                                   bool rtc_timer,
                                                   bool rtc_alarm) {
  if(keyboard) return deep_idle_policy::WakeReason::KEYBOARD;
  if(usb_host) return deep_idle_policy::WakeReason::USB_HOST;
  if(rtc_timer) return deep_idle_policy::WakeReason::RTC_TIMER;
  if(rtc_alarm) return deep_idle_policy::WakeReason::RTC_ALARM;
  return deep_idle_policy::WakeReason::OTHER;
}

static bool restore_tick_from_rtc(
    u32 tick_before, const rtc_clock::StartupSnapshot& before,
    u32 maximum_elapsed_ms, u32& elapsed_ms) {
  rtc_clock::StartupSnapshot after = {};
  if(!rtc_clock::startup_snapshot(after) ||
     !rtc_clock::elapsed_snapshot_milliseconds(before, after, elapsed_ms) ||
     elapsed_ms > maximum_elapsed_ms) {
    return false;
  }

  const u32 primask = __get_PRIMASK();
  __disable_irq();
  HAL_SuspendTick();
  uwTick = tick_before + elapsed_ms;
  HAL_ResumeTick();
  __set_PRIMASK(primask);
  return true;
}

static bool run_cycle(u8 seconds,
                      bool usb_application_idle,
                      deep_idle_policy::WakeReason& wake_reason,
                      u32& elapsed_ms,
                      deep_idle_policy::FailureReason& failure) {
  if(!kbd::prepare_stop_wake()) {
    failure = deep_idle_policy::FailureReason::KEYBOARD_ARM;
    return false;
  }
  if(!rtc_clock::arm_stop_wakeup(seconds)) {
    failure = deep_idle_policy::FailureReason::RTC_ARM;
    kbd::cancel_stop_wake();
    return false;
  }

  rtc_clock::StartupSnapshot before = {};
  if(!rtc_clock::startup_snapshot(before)) {
    failure = deep_idle_policy::FailureReason::RTC_SNAPSHOT;
    (void) rtc_clock::disarm_stop_wakeup();
    kbd::cancel_stop_wake();
    return false;
  }

  // This is still a completed foreground epoch. The 5 s maximum cycle remains
  // far below the IWDG's 13.6 s worst-case minimum timeout even if its normal
  // 250 ms rate gate decides that an immediate extra reload is unnecessary.
  independent_watchdog::foreground_epoch(millis());
  const u32 tick_before = uwTick;
  const u32 saved_primask = __get_PRIMASK();

  HAL_SuspendTick();
  __disable_irq();
#if MK61_USB_SUSPEND_SUPPORTED
  if(!usb_power::prepare_stop(usb_application_idle, tick_before)) {
    HAL_ResumeTick();
    __set_PRIMASK(saved_primask);
    (void) rtc_clock::disarm_stop_wakeup();
    kbd::cancel_stop_wake();
    failure = deep_idle_policy::FailureReason::USB_ARM;
    return false;
  }
#else
  (void) usb_application_idle;
#endif
  const bool key_before_stop = kbd::stop_wake_pending();
  const bool timer_before_stop = rtc_clock::stop_wakeup_pending();
  const bool alarm_before_stop = rtc_clock::alarm_wakeup_pending();
  const bool usb_before_stop = usb_power::stop_wake_pending();
  if(key_before_stop || timer_before_stop || alarm_before_stop ||
     usb_before_stop) {
    HAL_ResumeTick();
    __set_PRIMASK(saved_primask);
    const u8 captured = kbd::resume_from_stop();
    (void) rtc_clock::disarm_stop_wakeup();
    (void) usb_power::finish_stop(
        usb_before_stop, key_before_stop || captured != 0);
    wake_reason = classify_wake(
        key_before_stop || captured != 0,
        usb_before_stop,
        timer_before_stop, alarm_before_stop);
    elapsed_ms = 0;
    return true;
  }

  __HAL_PWR_CLEAR_FLAG(PWR_FLAG_WU);
  controller.note_stopped();
  __DSB();
  HAL_PWR_EnterSTOPMode(PWR_LOWPOWERREGULATOR_ON, PWR_STOPENTRY_WFI);
  __ISB();

  // Interrupts remain masked across the first flag snapshot, so the wake
  // source cannot disappear in its handler before it is classified.
  const bool key_wake = kbd::stop_wake_pending();
  const bool timer_wake = rtc_clock::stop_wakeup_pending();
  const bool alarm_wake = rtc_clock::alarm_wakeup_pending();
  const bool usb_wake = usb_power::stop_wake_pending();

  // STOP returns on HSI. Let the minimal pending ISR run and let SysTick supply
  // bounded HAL timeouts while the board's weak variant function restores the
  // exact HSE/PLL/APB/48 MHz USB clock tree. The RTC correction below replaces
  // any interim, deliberately imprecise ticks.
  HAL_ResumeTick();
  __set_PRIMASK(saved_primask);
  SystemClock_Config();
  SystemCoreClockUpdate();

  const bool clock_ok = SystemCoreClock == (u32) F_CPU;

  const bool tick_ok = restore_tick_from_rtc(
      tick_before, before,
      (u32) seconds * 1000U + MAX_ELAPSED_MARGIN_MS, elapsed_ms);
  const u8 captured = kbd::resume_from_stop();
  const bool timer_ok = rtc_clock::disarm_stop_wakeup();
  const bool usb_ok =
      !MK61_USB_SUSPEND_SUPPORTED ||
      usb_power::finish_stop(usb_wake, key_wake || captured != 0);
  wake_reason = classify_wake(
      key_wake || captured != 0, usb_wake, timer_wake, alarm_wake);
  if(!clock_ok) failure = deep_idle_policy::FailureReason::CLOCK_RESTORE;
  else if(!tick_ok) failure = deep_idle_policy::FailureReason::TICK_RESTORE;
  else if(!timer_ok) failure = deep_idle_policy::FailureReason::RTC_DISARM;
  else if(!usb_ok) failure = deep_idle_policy::FailureReason::USB_RESUME;
  return clock_ok && tick_ok && timer_ok && usb_ok;
}

static bool execute_request(void) {
  bool serial_stopped = false;
  bool display_suspended = false;
  bool ok = true;
  const bool preserve_usb =
      MK61_USB_SUSPEND_SUPPORTED && usb_power::suspended();
  const bool usb_application_idle =
      usb_mass_storage::deep_idle_quiescent();
  deep_idle_policy::FailureReason failure =
      deep_idle_policy::FailureReason::NONE;

#if defined(SERIAL_OUTPUT) && defined(USBCON) && defined(USBD_USE_CDC)
  if(!preserve_usb) {
    Serial.flush();
    Serial.end();
    serial_stopped = true;
  }
#endif

  main_lcd().flush();
  display_suspended = main_lcd().prepareDeepIdle();
  if(!display_suspended) {
    failure = deep_idle_policy::FailureReason::DISPLAY_SUSPEND;
    ok = false;
  }

  while(ok) {
    deep_idle_policy::WakeReason wake = deep_idle_policy::WakeReason::ERROR;
    u32 elapsed_ms = 0;
    if(!run_cycle(controller.seconds(), usb_application_idle,
                  wake, elapsed_ms, failure)) {
      ok = false;
      break;
    }

    // A setup-time keyboard edge can abort before WFI and therefore has no
    // STOP entry to account. All real STOP exits transition STOPPED->RESUMING.
    const deep_idle_policy::Snapshot state = controller.snapshot();
    if(state.state == deep_idle_policy::State::STOPPED) {
      controller.note_wake(wake, elapsed_ms);
    } else {
      controller.finish();
      break;
    }

    if(!controller.continue_cycles()) break;
    independent_watchdog::foreground_epoch(millis());
    controller.prepare_next_cycle();
  }

  if(display_suspended && !main_lcd().resumeDeepIdle()) {
    if(failure == deep_idle_policy::FailureReason::NONE) {
      failure = deep_idle_policy::FailureReason::DISPLAY_RESUME;
    }
    ok = false;
  }

#if defined(SERIAL_OUTPUT) && defined(USBCON) && defined(USBD_USE_CDC)
  if(serial_stopped) Serial.begin(115200);
#else
  (void) serial_stopped;
#endif

  if(ok) {
    controller.finish();
  } else {
    // Every partial owner is released before returning to LIGHT_IDLE. The
    // failure remains visible in counters/last_wake without stranding the UI.
    kbd::cancel_stop_wake();
    (void) rtc_clock::disarm_stop_wakeup();
    usb_power::cancel_stop();
    controller.note_failure(
        failure == deep_idle_policy::FailureReason::NONE
          ? deep_idle_policy::FailureReason::STATE : failure);
    controller.recover();
  }
  return ok;
}

#endif

} // namespace

bool request(u8 seconds, u16 cycles, u32 now_ms) {
#if MK61_DEEP_IDLE_SUPPORTED
  if(!controller.request(seconds, cycles)) return false;
  not_before_ms = now_ms + START_DELAY_MS;
  return true;
#else
  (void) seconds;
  (void) cycles;
  (void) now_ms;
  return false;
#endif
}

bool cancel(void) {
#if MK61_DEEP_IDLE_SUPPORTED
  return controller.cancel();
#else
  return false;
#endif
}

bool pending(void) {
#if MK61_DEEP_IDLE_SUPPORTED
  return controller.pending();
#else
  return false;
#endif
}

bool service(const deep_idle_policy::Conditions& conditions, u32 now_ms) {
#if MK61_DEEP_IDLE_SUPPORTED
  if(!controller.pending() || !time_reached(now_ms, not_before_ms)) return false;
  u32 mask = deep_idle_policy::blockers(conditions);
  if(__get_PRIMASK() != 0 || __get_IPSR() != 0) {
    mask |= deep_idle_policy::BLOCK_IRQ;
  }
  if(!controller.prepare(mask)) return false;
  return execute_request();
#else
  (void) conditions;
  (void) now_ms;
  return false;
#endif
}

void reset_statistics(void) {
#if MK61_DEEP_IDLE_SUPPORTED
  controller.reset_statistics();
#endif
}

deep_idle_policy::Snapshot statistics(void) {
#if MK61_DEEP_IDLE_SUPPORTED
  return controller.snapshot();
#else
  const deep_idle_policy::Snapshot result = {
    deep_idle_policy::State::LIGHT_IDLE,
    deep_idle_policy::WakeReason::NONE,
    deep_idle_policy::FailureReason::NONE,
    0, 0, 0, 0, 0, 0, 0, 0, 0, 0, 0, 0, 0, 0, {}
  };
  return result;
#endif
}

const char* backend_name(void) {
#if MK61_DEEP_IDLE_SUPPORTED
  return "STOP-RTC+KBD";
#else
  return "disabled";
#endif
}

bool enabled(void) {
  return MK61_DEEP_IDLE_SUPPORTED != 0;
}

} // namespace deep_idle

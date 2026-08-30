#ifndef MK61_DEEP_IDLE_POLICY_HPP
#define MK61_DEEP_IDLE_POLICY_HPP

#include "rust_types.h"

namespace deep_idle_policy {

static constexpr u8 MIN_SECONDS = 1;
static constexpr u8 MAX_SECONDS = 5;
static constexpr u16 MIN_CYCLES = 1;
static constexpr u16 MAX_CYCLES = 120;

enum class State : u8 {
  ACTIVE,
  LIGHT_IDLE,
  DEEP_IDLE_PENDING,
  STOP_ENTERING,
  STOPPED,
  RESUMING,
  RECOVERY,
};

enum class WakeReason : u8 {
  NONE,
  RTC_TIMER,
  KEYBOARD,
  RTC_ALARM,
  USB_HOST,
  OTHER,
  ERROR,
};

enum class FailureReason : u8 {
  NONE,
  STATE,
  DISPLAY_SUSPEND,
  KEYBOARD_ARM,
  RTC_ARM,
  RTC_SNAPSHOT,
  CLOCK_RESTORE,
  TICK_RESTORE,
  RTC_DISARM,
  DISPLAY_RESUME,
  USB_ARM,
  USB_RESUME,
};

enum Blocker : u32 {
  BLOCK_FOREGROUND = 1UL << 0,
  BLOCK_CALCULATOR = 1UL << 1,
  BLOCK_MSC = 1UL << 2,
  BLOCK_USB_SCREEN = 1UL << 3,
  BLOCK_TERMINAL = 1UL << 4,
  BLOCK_SOUND = 1UL << 5,
  BLOCK_KEYBOARD = 1UL << 6,
  BLOCK_CLASSIC = 1UL << 7,
  BLOCK_SCHEDULED = 1UL << 8,
  BLOCK_SPI = 1UL << 9,
  BLOCK_DISPLAY = 1UL << 10,
  BLOCK_RTC = 1UL << 11,
  BLOCK_WATCHDOG = 1UL << 12,
  BLOCK_IRQ = 1UL << 13,
  BLOCK_USB = 1UL << 14,
};

static constexpr usize BLOCKER_COUNT = 15;

struct Conditions {
  bool foreground_context;
  bool calculator_idle;
  bool msc_active;
  bool usb_screen_active;
  bool terminal_pending;
  bool sound_active;
  bool keyboard_active;
  bool classic_active;
  bool scheduled_work;
  bool spi_idle;
  bool display_ready;
  bool rtc_ready;
  bool watchdog_safe;
  bool irq_context;
  bool usb_stop_ready;
};

constexpr u32 blocker_if(bool condition, Blocker blocker) {
  return condition ? static_cast<u32>(blocker) : 0U;
}

constexpr u32 blockers(const Conditions& value) {
  return blocker_if(!value.foreground_context, BLOCK_FOREGROUND) |
         blocker_if(!value.calculator_idle, BLOCK_CALCULATOR) |
         blocker_if(value.msc_active, BLOCK_MSC) |
         blocker_if(value.usb_screen_active, BLOCK_USB_SCREEN) |
         blocker_if(value.terminal_pending, BLOCK_TERMINAL) |
         blocker_if(value.sound_active, BLOCK_SOUND) |
         blocker_if(value.keyboard_active, BLOCK_KEYBOARD) |
         blocker_if(value.classic_active, BLOCK_CLASSIC) |
         blocker_if(value.scheduled_work, BLOCK_SCHEDULED) |
         blocker_if(!value.spi_idle, BLOCK_SPI) |
         blocker_if(!value.display_ready, BLOCK_DISPLAY) |
         blocker_if(!value.rtc_ready, BLOCK_RTC) |
         blocker_if(!value.watchdog_safe, BLOCK_WATCHDOG) |
         blocker_if(value.irq_context, BLOCK_IRQ) |
         blocker_if(!value.usb_stop_ready, BLOCK_USB);
}

constexpr bool valid_request(u8 seconds, u16 cycles) {
  return seconds >= MIN_SECONDS && seconds <= MAX_SECONDS &&
         cycles >= MIN_CYCLES && cycles <= MAX_CYCLES;
}

constexpr u32 saturating_increment(u32 value) {
  return value == 0xFFFFFFFFUL ? value : value + 1U;
}

constexpr u64 saturating_add(u64 left, u64 right) {
  return left > ~((u64) 0) - right ? ~((u64) 0) : left + right;
}

struct Snapshot {
  State state;
  WakeReason last_wake;
  FailureReason last_failure;
  u8 seconds;
  u16 requested_cycles;
  u16 completed_cycles;
  u32 requests;
  u32 attempts;
  u32 entries;
  u32 rtc_timer_wakes;
  u32 keyboard_wakes;
  u32 rtc_alarm_wakes;
  u32 other_wakes;
  u32 failures;
  u32 last_elapsed_ms;
  u64 total_elapsed_ms;
  u32 last_blockers;
  u32 rejected[BLOCKER_COUNT];
};

class Controller {
  public:
    constexpr Controller(void)
      : state_(State::LIGHT_IDLE), last_wake_(WakeReason::NONE),
        last_failure_(FailureReason::NONE), seconds_(0),
        requested_cycles_(0), completed_cycles_(0), requests_(0), attempts_(0),
        entries_(0), rtc_timer_wakes_(0), keyboard_wakes_(0),
        rtc_alarm_wakes_(0), other_wakes_(0), failures_(0),
        last_elapsed_ms_(0), total_elapsed_ms_(0), last_blockers_(0),
        rejected_{} {}

    bool request(u8 seconds, u16 cycles) {
      if(!valid_request(seconds, cycles) || pending_or_running()) return false;
      seconds_ = seconds;
      requested_cycles_ = cycles;
      completed_cycles_ = 0;
      last_wake_ = WakeReason::NONE;
      last_failure_ = FailureReason::NONE;
      last_blockers_ = 0;
      requests_ = saturating_increment(requests_);
      state_ = State::DEEP_IDLE_PENDING;
      return true;
    }

    bool cancel(void) {
      if(state_ != State::DEEP_IDLE_PENDING) return false;
      state_ = State::LIGHT_IDLE;
      seconds_ = 0;
      requested_cycles_ = 0;
      completed_cycles_ = 0;
      last_blockers_ = 0;
      return true;
    }

    bool prepare(u32 mask) {
      if(state_ != State::DEEP_IDLE_PENDING) return false;
      attempts_ = saturating_increment(attempts_);
      last_blockers_ = mask;
      if(mask != 0) {
        for(usize index = 0; index < BLOCKER_COUNT; index++) {
          if((mask & ((u32) 1U << index)) != 0) {
            rejected_[index] = saturating_increment(rejected_[index]);
          }
        }
        return false;
      }
      state_ = State::STOP_ENTERING;
      return true;
    }

    void note_stopped(void) {
      if(state_ != State::STOP_ENTERING && state_ != State::RESUMING) {
        note_failure(FailureReason::STATE);
        return;
      }
      state_ = State::STOPPED;
      entries_ = saturating_increment(entries_);
    }

    void note_wake(WakeReason reason, u32 elapsed_ms) {
      if(state_ != State::STOPPED) {
        note_failure(FailureReason::STATE);
        return;
      }
      state_ = State::RESUMING;
      last_wake_ = reason;
      last_elapsed_ms_ = elapsed_ms;
      total_elapsed_ms_ = saturating_add(total_elapsed_ms_, elapsed_ms);
      if(completed_cycles_ != 0xFFFFU) completed_cycles_++;
      switch(reason) {
        case WakeReason::RTC_TIMER:
          rtc_timer_wakes_ = saturating_increment(rtc_timer_wakes_);
          break;
        case WakeReason::KEYBOARD:
          keyboard_wakes_ = saturating_increment(keyboard_wakes_);
          break;
        case WakeReason::RTC_ALARM:
          rtc_alarm_wakes_ = saturating_increment(rtc_alarm_wakes_);
          break;
        case WakeReason::USB_HOST:
        case WakeReason::OTHER:
          other_wakes_ = saturating_increment(other_wakes_);
          break;
        case WakeReason::NONE:
        case WakeReason::ERROR:
          break;
      }
    }

    bool continue_cycles(void) const {
      return state_ == State::RESUMING &&
             last_wake_ == WakeReason::RTC_TIMER &&
             completed_cycles_ < requested_cycles_;
    }

    void prepare_next_cycle(void) {
      if(state_ == State::RESUMING) state_ = State::STOP_ENTERING;
    }

    void finish(void) {
      if(state_ == State::RESUMING || state_ == State::STOP_ENTERING) {
        state_ = State::LIGHT_IDLE;
      }
    }

    void note_failure(FailureReason reason) {
      failures_ = saturating_increment(failures_);
      last_wake_ = WakeReason::ERROR;
      last_failure_ = reason;
      state_ = State::RECOVERY;
    }

    void recover(void) {
      if(state_ == State::RECOVERY) state_ = State::LIGHT_IDLE;
    }

    bool pending(void) const { return state_ == State::DEEP_IDLE_PENDING; }

    bool pending_or_running(void) const {
      return state_ == State::DEEP_IDLE_PENDING ||
             state_ == State::STOP_ENTERING || state_ == State::STOPPED ||
             state_ == State::RESUMING;
    }

    u8 seconds(void) const { return seconds_; }
    u16 requested_cycles(void) const { return requested_cycles_; }

    void reset_statistics(void) {
      if(pending_or_running()) return;
      const State retained_state = state_;
      *this = Controller();
      state_ = retained_state == State::ACTIVE
          ? State::ACTIVE : State::LIGHT_IDLE;
    }

    Snapshot snapshot(void) const {
      Snapshot result = {
        state_, last_wake_, last_failure_, seconds_, requested_cycles_,
        completed_cycles_,
        requests_, attempts_, entries_, rtc_timer_wakes_, keyboard_wakes_,
        rtc_alarm_wakes_, other_wakes_, failures_, last_elapsed_ms_,
        total_elapsed_ms_, last_blockers_, {}
      };
      for(usize index = 0; index < BLOCKER_COUNT; index++) {
        result.rejected[index] = rejected_[index];
      }
      return result;
    }

  private:
    State state_;
    WakeReason last_wake_;
    FailureReason last_failure_;
    u8 seconds_;
    u16 requested_cycles_;
    u16 completed_cycles_;
    u32 requests_;
    u32 attempts_;
    u32 entries_;
    u32 rtc_timer_wakes_;
    u32 keyboard_wakes_;
    u32 rtc_alarm_wakes_;
    u32 other_wakes_;
    u32 failures_;
    u32 last_elapsed_ms_;
    u64 total_elapsed_ms_;
    u32 last_blockers_;
    u32 rejected_[BLOCKER_COUNT];
};

inline const char* state_name(State state) {
  switch(state) {
    case State::ACTIVE: return "active";
    case State::LIGHT_IDLE: return "light";
    case State::DEEP_IDLE_PENDING: return "pending";
    case State::STOP_ENTERING: return "entering";
    case State::STOPPED: return "stopped";
    case State::RESUMING: return "resuming";
    case State::RECOVERY: return "recovery";
  }
  return "unknown";
}

inline const char* wake_name(WakeReason reason) {
  switch(reason) {
    case WakeReason::NONE: return "none";
    case WakeReason::RTC_TIMER: return "rtc-timer";
    case WakeReason::KEYBOARD: return "keyboard";
    case WakeReason::RTC_ALARM: return "rtc-alarm";
    case WakeReason::USB_HOST: return "usb-host";
    case WakeReason::OTHER: return "other";
    case WakeReason::ERROR: return "error";
  }
  return "unknown";
}

inline const char* failure_name(FailureReason reason) {
  switch(reason) {
    case FailureReason::NONE: return "none";
    case FailureReason::STATE: return "state";
    case FailureReason::DISPLAY_SUSPEND: return "display-suspend";
    case FailureReason::KEYBOARD_ARM: return "keyboard-arm";
    case FailureReason::RTC_ARM: return "rtc-arm";
    case FailureReason::RTC_SNAPSHOT: return "rtc-snapshot";
    case FailureReason::CLOCK_RESTORE: return "clock-restore";
    case FailureReason::TICK_RESTORE: return "tick-restore";
    case FailureReason::RTC_DISARM: return "rtc-disarm";
    case FailureReason::DISPLAY_RESUME: return "display-resume";
    case FailureReason::USB_ARM: return "usb-arm";
    case FailureReason::USB_RESUME: return "usb-resume";
  }
  return "unknown";
}

inline const char* blocker_name(usize index) {
  switch(index) {
    case 0: return "foreground";
    case 1: return "calculator";
    case 2: return "msc";
    case 3: return "uscreen";
    case 4: return "terminal";
    case 5: return "sound";
    case 6: return "keyboard";
    case 7: return "classic";
    case 8: return "scheduled";
    case 9: return "spi";
    case 10: return "display";
    case 11: return "rtc";
    case 12: return "watchdog";
    case 13: return "irq";
    case 14: return "usb";
    default: return "unknown";
  }
}

} // namespace deep_idle_policy

#endif

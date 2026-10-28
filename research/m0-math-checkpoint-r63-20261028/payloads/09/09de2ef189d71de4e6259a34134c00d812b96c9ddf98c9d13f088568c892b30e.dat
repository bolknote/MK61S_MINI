#ifndef MK61_OLED_PROTECTION_HPP
#define MK61_OLED_PROTECTION_HPP

#include "rust_types.h"

namespace oled_protection {

enum class Timeout : u8 {
  OFF = 0,
  MINUTES_5 = 1,
  MINUTES_15 = 2,
  MINUTES_30 = 3,
};

enum class Transition : u8 {
  NONE = 0,
  DISPLAY_ON,
  DISPLAY_OFF,
};

constexpr Timeout normalizeTimeout(u8 raw) {
  return raw <= (u8) Timeout::MINUTES_30 ? (Timeout) raw
                                         : Timeout::MINUTES_15;
}

constexpr u32 timeoutMilliseconds(Timeout timeout) {
  switch(timeout) {
    case Timeout::MINUTES_5: return 5UL * 60UL * 1000UL;
    case Timeout::MINUTES_15: return 15UL * 60UL * 1000UL;
    case Timeout::MINUTES_30: return 30UL * 60UL * 1000UL;
    case Timeout::OFF: default: return 0;
  }
}

inline const char* timeoutName(Timeout timeout) {
  switch(timeout) {
    case Timeout::OFF: return "off";
    case Timeout::MINUTES_5: return "5m";
    case Timeout::MINUTES_15: return "15m";
    case Timeout::MINUTES_30: return "30m";
  }
  return "15m";
}

class State {
  public:
    constexpr State(void)
      : last_activity_ms_(0), timeout_(Timeout::MINUTES_15), awake_(true),
        initialized_(false) {}

    void configure(Timeout timeout, u32 now) {
      timeout_ = normalizeTimeout((u8) timeout);
      last_activity_ms_ = now;
      initialized_ = true;
    }

    Transition activity(u32 now) {
      last_activity_ms_ = now;
      initialized_ = true;
      if(awake_) return Transition::NONE;
      awake_ = true;
      return Transition::DISPLAY_ON;
    }

    Transition poll(u32 now) {
      if(!initialized_) {
        last_activity_ms_ = now;
        initialized_ = true;
        return Transition::NONE;
      }
      const u32 interval = timeoutMilliseconds(timeout_);
      if(!awake_ || interval == 0 ||
         (u32) (now - last_activity_ms_) < interval) {
        return Transition::NONE;
      }
      awake_ = false;
      return Transition::DISPLAY_OFF;
    }

    void force(bool awake, u32 now) {
      awake_ = awake;
      if(awake) last_activity_ms_ = now;
      initialized_ = true;
    }

    Timeout timeout(void) const { return timeout_; }
    bool awake(void) const { return awake_; }
    u32 lastActivity(void) const { return last_activity_ms_; }

  private:
    u32 last_activity_ms_;
    Timeout timeout_;
    bool awake_;
    bool initialized_;
};

} // namespace oled_protection

#endif

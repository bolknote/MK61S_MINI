#ifndef RUNTIME_SAFETY_HPP
#define RUNTIME_SAFETY_HPP

#include "rust_types.h"

namespace runtime_safety {

static constexpr isize SOUND_FREQUENCY_MAX_HZ = 65535;

inline bool time_reached(t_time_ms now, t_time_ms target) {
  return (i32) (now - target) >= 0;
}

class Deadline {
  public:
    Deadline(void) : pending_(false), target_(0) {}

    bool pending(void) const { return pending_; }
    t_time_ms target(void) const { return target_; }

    void schedule(t_time_ms start, t_time_ms delay_ms) {
      pending_ = true;
      target_ = start + delay_ms;
    }

    bool due(t_time_ms now) const {
      return pending_ && time_reached(now, target_);
    }

    void clear(void) {
      pending_ = false;
    }

  private:
    bool pending_;
    t_time_ms target_;
};

inline bool valid_index(i32 index, usize count) {
  return index >= 0 && (usize) index < count;
}

inline isize positive_quantum(isize value) {
  return value > 0 ? value : 1;
}

inline bool valid_extended_command(u8 code, usize command_count) {
  return code != 0 && (usize) code < command_count;
}

inline bool extended_command_delay(u8 code, t_time_ms& delay_ms) {
  switch(code) {
    case 1: delay_ms = 200;  return true;
    case 2: delay_ms = 500;  return true;
    case 3: delay_ms = 1000; return true;
    case 4: delay_ms = 2000; return true;
    case 5:
    case 6: delay_ms = 100;  return true;
    default: return false;
  }
}

inline bool valid_sound_frequency(isize frequency_Hz) {
  return frequency_Hz > 0 && frequency_Hz <= SOUND_FREQUENCY_MAX_HZ;
}

inline bool valid_sound_note(u16 frequency_Hz, u16 duration_ms, u8 volume_percent) {
  return duration_ms != 0 && volume_percent <= 100 &&
         (frequency_Hz == 0 || valid_sound_frequency((isize) frequency_Hz));
}

inline usize blink_transition_count(usize blink_count) {
  if(blink_count == 0) return 0;
  const usize max_value = (usize) ~((usize) 0);
  const usize max_exact_count = max_value / 2 + 1;
  if(blink_count > max_exact_count) return max_value;
  return (blink_count - 1) * 2 + 1;
}

} // namespace runtime_safety

#endif

#ifndef MK61_POWER_MONITOR_POLICY_HPP
#define MK61_POWER_MONITOR_POLICY_HPP

#include "rust_types.h"

namespace power_monitor_policy {

enum StateFlag : u32 {
  BELOW_THRESHOLD = 1UL << 0,
  RECOVERY_DELAY = 1UL << 1
};

struct State {
  u32 flags;
  u32 recovery_started_ms;
};

inline State initial_state(bool below_threshold, u32 now_ms) {
  return {
    below_threshold ? (u32) BELOW_THRESHOLD : 0,
    now_ms
  };
}

inline bool below_threshold(const State& state) {
  return (state.flags & BELOW_THRESHOLD) != 0;
}

inline bool recovering(const State& state) {
  return (state.flags & RECOVERY_DELAY) != 0;
}

inline bool writes_allowed(const State& state) {
  return (state.flags & (BELOW_THRESHOLD | RECOVERY_DELAY)) == 0;
}

// Returns true only when the logical comparator state changed. The STM32 PVD
// EXTI can have a pending edge from configuration itself, so repeated samples
// must not manufacture extra low-voltage events.
inline bool note_edge(State& state, bool now_below, u32 now_ms) {
  if(now_below == below_threshold(state)) return false;
  if(now_below) {
    state.flags = BELOW_THRESHOLD;
  } else {
    state.flags = RECOVERY_DELAY;
    state.recovery_started_ms = now_ms;
  }
  return true;
}

inline bool poll_stable(State& state, u32 now_ms, u32 stable_interval_ms) {
  if(!recovering(state) || below_threshold(state)) return false;
  if((u32) (now_ms - state.recovery_started_ms) < stable_interval_ms) {
    return false;
  }
  state.flags = 0;
  return true;
}

inline u32 stable_remaining_ms(const State& state, u32 now_ms,
                               u32 stable_interval_ms) {
  if(!recovering(state)) return 0;
  const u32 elapsed = (u32) (now_ms - state.recovery_started_ms);
  return elapsed >= stable_interval_ms ? 0 : stable_interval_ms - elapsed;
}

} // namespace power_monitor_policy

#endif

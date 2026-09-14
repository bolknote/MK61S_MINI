#ifndef MK61_RUN_MEASUREMENT_HPP
#define MK61_RUN_MEASUREMENT_HPP

#include "rust_types.h"

namespace run_measurement {

enum class State : u8 {
  IDLE,
  ARMED,
  RUNNING
};

// `measure` is deliberately one-shot: a script arms the next calculator run,
// and the state returns to IDLE as soon as that run finally stops.
void arm_next(void);
void cancel(void);
State state(void);
bool program_started(u32 now_ms);
bool program_stopped(u32 now_ms, u32& elapsed_ms);

// Modal result used by the firmware after the final program stop.
void show_and_wait(u32 elapsed_ms);

} // namespace run_measurement

#endif

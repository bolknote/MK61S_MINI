#ifndef MK61_STM32F4_TIMER_MATH_HPP
#define MK61_STM32F4_TIMER_MATH_HPP

#include "rust_types.h"

namespace stm32f4_timer_math {

static constexpr u32 TIMER_FACTOR_LIMIT = 65536UL;
static constexpr u32 CLASSIC_COUNTER_HZ = 10000UL;
static constexpr u32 CLASSIC_PERIOD_NUMERATOR = 15UL;
static constexpr u32 CLASSIC_PERIOD_DENOMINATOR = 13UL;
static constexpr u32 CLASSIC_PHASE_LIMIT =
  CLASSIC_COUNTER_HZ * CLASSIC_PERIOD_NUMERATOR;

struct Divider {
  u16 prescaler_register;
  u16 auto_reload_register;

  u32 prescaler_factor(void) const {
    return (u32) prescaler_register + 1UL;
  }

  u32 period_ticks(void) const {
    return (u32) auto_reload_register + 1UL;
  }
};

inline Divider frequency_divider(u32 timer_hz, u32 frequency_hz) {
  if(timer_hz == 0 || frequency_hz == 0) return {0, 0};

  u32 target_cycles = timer_hz / frequency_hz;
  if(target_cycles == 0) target_cycles = 1;

  u32 prescaler =
    (target_cycles + TIMER_FACTOR_LIMIT - 1UL) / TIMER_FACTOR_LIMIT;
  if(prescaler == 0) prescaler = 1;
  if(prescaler > TIMER_FACTOR_LIMIT) prescaler = TIMER_FACTOR_LIMIT;

  const u32 divisor = frequency_hz * prescaler;
  u32 ticks = (timer_hz + divisor / 2UL) / divisor;
  if(ticks == 0) ticks = 1;
  if(ticks > TIMER_FACTOR_LIMIT) ticks = TIMER_FACTOR_LIMIT;

  return {
    (u16) (prescaler - 1UL),
    (u16) (ticks - 1UL)
  };
}

inline u32 pwm_compare(u32 period_ticks, u32 duty_8bit) {
  if(period_ticks == 0 || duty_8bit == 0) return 0;
  if(duty_8bit > 255UL) duty_8bit = 255UL;
  return (period_ticks * duty_8bit) / 255UL;
}

inline u16 elapsed_counter_ticks(u16 previous, u16 current) {
  return (u16) (current - previous);
}

inline u32 advance_classic_phase(u16 elapsed_ticks, u32& phase) {
  phase += (u32) elapsed_ticks * CLASSIC_PERIOD_DENOMINATOR;
  const u32 due = phase / CLASSIC_PHASE_LIMIT;
  phase %= CLASSIC_PHASE_LIMIT;
  return due;
}

} // namespace stm32f4_timer_math

#endif

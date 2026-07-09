#ifndef LED_CONTROL_TOOLS
#define LED_CONTROL_TOOLS

#include "rust_types.h"

namespace led {
  // Шаг паттерна: состояние светодиода и время удержания до следующего шага.
  // Удержание последнего шага не имеет значения - его состояние остаётся.
  struct PatternStep {
    u8        on;
    t_time_ms hold_ms;
  };
  static constexpr usize PATTERN_MAX = 16;

  extern void init(void);
  extern void on(void);
  extern void off(void);
  extern void blink(usize count, t_time_ms on_ms, t_time_ms off_ms);
  extern void blink_continuous(t_time_ms on_ms, t_time_ms off_ms);
  extern void blink_stop(void);
  extern bool pattern_start(const PatternStep* steps, usize count);
  extern void control(void);
  extern void control(t_time_ms now);
}

#endif

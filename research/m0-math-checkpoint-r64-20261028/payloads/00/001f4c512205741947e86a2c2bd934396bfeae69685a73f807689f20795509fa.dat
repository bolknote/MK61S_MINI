#ifndef LED_CONTROL_TOOLS
#define LED_CONTROL_TOOLS

#include "rust_types.h"

namespace led {
  // Шаг паттерна: состояние светодиода и время удержания до следующего шага.
  // Удержание последнего шага не имеет значения - его состояние остаётся.
  // u16 достаточно (до 65 с на шаг), буфер паттерна живёт в ОЗУ постоянно.
  struct PatternStep {
    u8  on;
    u16 hold_ms;
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

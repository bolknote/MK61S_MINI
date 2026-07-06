#ifndef LED_CONTROL_TOOLS
#define LED_CONTROL_TOOLS

#include "rust_types.h"

namespace led {
  extern void init(void);
  extern void on(void);
  extern void off(void);
  extern void blink(usize count, t_time_ms on_ms, t_time_ms off_ms);
  extern void blink_continuous(t_time_ms on_ms, t_time_ms off_ms);
  extern void blink_stop(void);
  extern void control(void);
  extern void control(t_time_ms now);
}

#endif

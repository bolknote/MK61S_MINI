#include "rust_types.h"
#include "config.h"
#include "ledcontrol.h"

struct t_blink_state {
  bool active;
  bool continuous;
  bool led_on;
  usize transitions_left;
  t_time_ms next_ms;
  t_time_ms on_ms;
  t_time_ms off_ms;
};

static t_blink_state blink_state;

static inline bool time_reached(t_time_ms now, t_time_ms target) {
  return (i32) (now - target) >= 0;
}

namespace led {

void init(void) {
  pinMode(PIN_LED, OUTPUT);
  digitalWrite(PIN_LED, LOW);
  blink_state = {};
}

void control(void) {
  control(millis());
}

void control(t_time_ms now) {
  if(!blink_state.active || !time_reached(now, blink_state.next_ms)) return;

  if(blink_state.led_on) {
    off();
    blink_state.led_on = false;
    if(!blink_state.continuous) {
      blink_state.transitions_left--;
      if(blink_state.transitions_left == 0) {
        blink_state.active = false;
        return;
      }
    }
    blink_state.next_ms = now + blink_state.off_ms;
  } else {
    on();
    blink_state.led_on = true;
    if(!blink_state.continuous) blink_state.transitions_left--;
    blink_state.next_ms = now + blink_state.on_ms;
  }
}

void on(void) {
  digitalWrite(PIN_LED, HIGH);
}

void off(void) {
  digitalWrite(PIN_LED, LOW);
}

void blink(usize count, t_time_ms on_ms, t_time_ms off_ms) {
  if(count == 0) {
    blink_state.active = false;
    off();
    return;
  }

  blink_state.active = true;
  blink_state.continuous = false;
  blink_state.led_on = true;
  blink_state.transitions_left = count * 2 - 1;
  blink_state.next_ms = millis() + on_ms;
  blink_state.on_ms = on_ms;
  blink_state.off_ms = off_ms;
  on();
}

void blink_continuous(t_time_ms on_ms, t_time_ms off_ms) {
  blink_state.active = true;
  blink_state.continuous = true;
  blink_state.led_on = true;
  blink_state.transitions_left = 0;
  blink_state.next_ms = millis() + on_ms;
  blink_state.on_ms = on_ms;
  blink_state.off_ms = off_ms;
  on();
}

void blink_stop(void) {
  blink_state = {};
  off();
}

}

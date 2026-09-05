#ifndef CLASS_KEYBOARD
#define CLASS_KEYBOARD

#include "config.h"
#include "keyboard_core.hpp"
#include "rust_types.h"

#if MK61_DEEP_IDLE_ENABLED && \
    ((defined(MK61_KEYBOARD_MINI) && defined(MK61_OLED1602_WS0010)) || \
     (defined(MK61_KEYBOARD_CLASSIC) && defined(MK61_DISPLAY_UC1609) && \
      defined(MK61_BOARD_CLASSIC_V3))) && \
    defined(ARDUINO_ARCH_STM32) && \
    defined(__ARM_ARCH_7EM__) && \
    (defined(STM32F401xC) || defined(STM32F401xE) || \
     defined(STM32F411xE))
  #define MK61_KEYBOARD_STOP_WAKE_SUPPORTED 1
#else
  #define MK61_KEYBOARD_STOP_WAKE_SUPPORTED 0
#endif

enum class key_state {PRESSED=0, RELEASED=keyboard_core::RELEASE_MASK};

struct keyboard_stop_wake_snapshot {
  bool supported;
  u32 capture_events;
  i32 last_scan_code;
  u8 last_capture_count;
  u8 wake_rows;
  u8 captured_rows;
};

static constexpr key_state PRESS             =   key_state::PRESSED;
static constexpr key_state RELEASE           =   key_state::RELEASED;

extern  bool  cir_buff_write(i8 data);
extern  i8    cir_buff_get(usize index);
extern  i32   cir_buff_read(void);

namespace kbd {
  extern  bool    push(i8 key_code);
  inline  i32     last_key(void)    { return  cir_buff_get(0); }
  inline  i32     get_key(void)     { return  cir_buff_read(); }

  extern  void    test(void);
  extern  void    init(void);
  extern  i32     get_key(key_state state);
  extern  i32     get_key_wait(void);
  using Event = keyboard_core::Event;
  extern  Event   poll_event(void); // scan once, consume exactly one FIFO event
  extern  void    handoff(Event cause);
  extern  bool    handoff_pending(void);
  extern  u32     overflow_count(void);
  extern  void    clear_hold_key(void);
  extern  bool    take_immediate_press(i32 key_code);
  extern  void    clear_immediate_presses(void);
  extern  bool    any_key_pressed(void);
  extern  bool    is_key_pressed(i32 key_code);
  extern  bool    is_physical_key_pressed(i32 key_code);
  extern  void    set_external_key_pressed(i32 key_code, bool pressed);
  extern  bool    prepare_stop_wake(void);
  extern  bool    stop_wake_pending(void);
  extern  keyboard_stop_wake_snapshot stop_wake_statistics(void);
  extern  void    reset_stop_wake_statistics(void);
  // Restores the ordinary matrix scanner and returns the number of physical
  // presses preserved from the wake configuration.
  extern  u8      resume_from_stop(void);
  extern  void    cancel_stop_wake(void);
  extern  isize   scan(void);
  extern  isize   scan_m61_controls(void);
}

#endif

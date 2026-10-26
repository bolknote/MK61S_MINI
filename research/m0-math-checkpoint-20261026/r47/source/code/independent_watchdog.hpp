#ifndef MK61_INDEPENDENT_WATCHDOG_HPP
#define MK61_INDEPENDENT_WATCHDOG_HPP

#include "rust_types.h"
#include "watchdog_gate.hpp"

#ifndef MK61_ENABLE_INDEPENDENT_WATCHDOG
  #define MK61_ENABLE_INDEPENDENT_WATCHDOG 1
#endif
#if MK61_ENABLE_INDEPENDENT_WATCHDOG != 0 && \
    MK61_ENABLE_INDEPENDENT_WATCHDOG != 1
  #error "MK61_ENABLE_INDEPENDENT_WATCHDOG must be 0 or 1"
#endif

#ifndef MK61_ENABLE_WATCHDOG_TEST
  #define MK61_ENABLE_WATCHDOG_TEST 0
#endif
#if MK61_ENABLE_WATCHDOG_TEST != 0 && MK61_ENABLE_WATCHDOG_TEST != 1
  #error "MK61_ENABLE_WATCHDOG_TEST must be 0 or 1"
#endif

#if MK61_ENABLE_INDEPENDENT_WATCHDOG && defined(ARDUINO_ARCH_STM32) && \
    defined(__ARM_ARCH_7EM__) && \
    (defined(STM32F401xC) || defined(STM32F401xE) || \
     defined(STM32F411xE))
  #define MK61_INDEPENDENT_WATCHDOG_SUPPORTED 1
#else
  #define MK61_INDEPENDENT_WATCHDOG_SUPPORTED 0
#endif

namespace independent_watchdog {

// Use the full 12-bit reload range: 32.768 s at nominal 32 kHz LSI. At the
// fastest specified LSI this is still about 22.3 s. A nearly full 512-KiB C6
// USB import has measured 18.8 s between completed progress checkpoints, so
// the former nominal 20 s timeout (13.6 s worst-case) was insufficient.
static constexpr u32 NOMINAL_TIMEOUT_MS = 32768;
static constexpr u32 PRESCALER = 256;
static constexpr u32 RELOAD = 4095;
static_assert(RELOAD <= 0x0FFF, "IWDG reload exceeds the 12-bit register");

enum RetainedState : u32 {
  RETAINED_RUNNING = 1,
  RETAINED_INHIBITED = 2,
  RETAINED_HANG_TEST = 3
};

struct Breadcrumb {
  u32 magic;
  u32 inverse_magic;
  u32 generation;
  u32 state;
  u32 epochs;
  u32 reloads;
  u32 last_epoch_ms;
  u32 last_reload_ms;
  u32 maximum_reload_gap_ms;
};

struct Snapshot {
  watchdog_gate::Snapshot gate;
  bool boot_was_watchdog_reset;
  bool previous_breadcrumb_valid;
  u32 generation;
  Breadcrumb previous;
};

// Запускается в самом конце setup(), когда все критические подсистемы готовы.
bool initialize(u32 now_ms);

// Main-loop reload point: call after a complete foreground idle/service
// epoch. Never call from an ISR.
void foreground_epoch(u32 now_ms);

// A USB-disk import may keep the foreground inside one APP call for longer
// than the IWDG period. Call only after a complete, durable C6 file commit;
// never from an ISR or from a loop waiting for one operation to finish.
void completed_storage_unit(void);

bool running(void);
Snapshot statistics(void);

#if MK61_INDEPENDENT_WATCHDOG_SUPPORTED && MK61_ENABLE_WATCHDOG_TEST
void inhibit_for_test(void);
[[noreturn]] void hang_for_test(void);
#endif

} // namespace independent_watchdog

#endif

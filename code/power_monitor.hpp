#ifndef MK61_POWER_MONITOR_HPP
#define MK61_POWER_MONITOR_HPP

#include "config.h"
#include "rust_types.h"

#ifndef MK61_ENABLE_PVD
  #define MK61_ENABLE_PVD 1
#endif
#if MK61_ENABLE_PVD != 0 && MK61_ENABLE_PVD != 1
  #error "MK61_ENABLE_PVD must be 0 or 1"
#endif

#ifndef MK61_PVD_LEVEL
  // PLS=6 crosses downward at 2.85..2.99 V and upward at 2.96..3.10 V
  // on STM32F401/F411. This stays above the 2.7 V minimum of the fitted
  // W25Q128 while retaining useful margin below the measured 3.28 V rail.
  #define MK61_PVD_LEVEL 6
#endif
#if MK61_PVD_LEVEL < 0 || MK61_PVD_LEVEL > 7
  #error "MK61_PVD_LEVEL must be in the range 0..7"
#endif

#ifndef MK61_PVD_RECOVERY_STABLE_MS
  #define MK61_PVD_RECOVERY_STABLE_MS 100UL
#endif
#if MK61_PVD_RECOVERY_STABLE_MS < 10UL || \
    MK61_PVD_RECOVERY_STABLE_MS > 5000UL
  #error "MK61_PVD_RECOVERY_STABLE_MS must be 10..5000"
#endif

#if MK61_ENABLE_PVD && defined(ARDUINO_ARCH_STM32) && \
    (defined(STM32F401xC) || defined(STM32F401xE) || \
     defined(STM32F411xE))
  #define MK61_POWER_MONITOR_SUPPORTED 1
#else
  #define MK61_POWER_MONITOR_SUPPORTED 0
#endif

namespace power_monitor {

enum class Operation : u8 {
  NOR_PROGRAM,
  NOR_ERASE,
  MSC_WRITE
};

struct ThresholdRange {
  u16 falling_min_mv;
  u16 falling_typ_mv;
  u16 falling_max_mv;
  u16 rising_min_mv;
  u16 rising_typ_mv;
  u16 rising_max_mv;
};

struct Snapshot {
  bool supported;
  bool initialized;
  bool below_threshold;
  bool recovering;
  bool writes_allowed;
  bool previous_unstable;
  bool edge_seen;
  bool last_edge_low;
  u8 level;
  u32 stable_remaining_ms;
  u32 low_events;
  u32 recovery_events;
  u32 rejected_programs;
  u32 rejected_erases;
  u32 rejected_msc_writes;
  u32 last_edge_ms;
  u32 last_edge_cycles;
  u32 previous_edge_ms;
};

// Called near the beginning of setup(), before external Flash or USB can
// start a write. The interrupt handler only samples PVDO, updates bounded
// counters/state and publishes a small .noinit breadcrumb.
void initialize(void);
void poll(u32 now_ms);
bool writes_allowed(void);
bool allow(Operation operation);
Snapshot snapshot(void);
ThresholdRange threshold_range(void);
const char* backend_name(void);

// Public only for the vector wrapper and the target ELF policy test.
void interrupt_handler(void);

} // namespace power_monitor

#endif

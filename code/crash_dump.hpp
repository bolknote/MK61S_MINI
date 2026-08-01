#ifndef MK61_CRASH_DUMP_HPP
#define MK61_CRASH_DUMP_HPP

#include "crash_dump_format.hpp"
#include "rust_types.h"

#ifndef MK61_ENABLE_CRASH_DUMP
  #define MK61_ENABLE_CRASH_DUMP 1
#endif
#if MK61_ENABLE_CRASH_DUMP != 0 && MK61_ENABLE_CRASH_DUMP != 1
  #error "MK61_ENABLE_CRASH_DUMP must be 0 or 1"
#endif

#ifndef MK61_ENABLE_FAULT_INJECTION
  #define MK61_ENABLE_FAULT_INJECTION 0
#endif
#if MK61_ENABLE_FAULT_INJECTION != 0 && MK61_ENABLE_FAULT_INJECTION != 1
  #error "MK61_ENABLE_FAULT_INJECTION must be 0 or 1"
#endif

#if MK61_ENABLE_CRASH_DUMP && defined(ARDUINO_ARCH_STM32) && \
    defined(__ARM_ARCH_7EM__) && \
    (defined(STM32F401xC) || defined(STM32F401xE) || \
     defined(STM32F411xE))
  #define MK61_CRASH_DUMP_SUPPORTED 1
#else
  #define MK61_CRASH_DUMP_SUPPORTED 0
#endif

namespace crash_dump {

enum RuntimeState : u32 {
  RUNTIME_UNKNOWN = 0,
  RUNTIME_BOOT = 1,
  RUNTIME_CALCULATOR = 2,
  RUNTIME_RUN_CLASSIC = 3,
  RUNTIME_RUN_FAST = 4,
  RUNTIME_MENU = 5,
  RUNTIME_M61 = 6,
  RUNTIME_USB_MASS_STORAGE = 7,
  RUNTIME_USB_SCREEN = 8,
  RUNTIME_FAULT_TEST = 9
};

// Вызывать первой строкой setup(): функция читает reset flags до их очистки,
// валидирует .noinit и включает отдельные configurable fault handlers.
void initialize(void);

bool available(void);
bool copy(crash_dump_format::Record& output);
void clear(void);
u32 boot_reset_flags(void);
u32 current_build_id(void);
bool memory_layout_valid(void);

void update_runtime(u32 state, u32 detail, u32 uptime_ms);
void update_classic(u32 ticks, u32 steps, u32 missed, u32 pending);

bool persisted(void);
bool mark_persisted(void);

#if MK61_CRASH_DUMP_SUPPORTED && MK61_ENABLE_FAULT_INJECTION
[[noreturn]] void inject_usage_fault(void);
[[noreturn]] void inject_bus_fault(void);
[[noreturn]] void inject_hard_fault(void);
#endif

} // namespace crash_dump

#endif

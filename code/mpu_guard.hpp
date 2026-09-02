#ifndef MK61_MPU_GUARD_HPP
#define MK61_MPU_GUARD_HPP

#include "rust_types.h"

#ifndef MK61_ENABLE_MPU_GUARDS
  #define MK61_ENABLE_MPU_GUARDS 1
#endif
#ifndef MK61_ENABLE_MPU_TEST
  #define MK61_ENABLE_MPU_TEST 0
#endif

#if MK61_ENABLE_MPU_GUARDS && defined(ARDUINO_ARCH_STM32) && \
    defined(__ARM_ARCH_7EM__) && \
    (defined(STM32F401xC) || defined(STM32F401xE) || \
     defined(STM32F411xE))
  #define MK61_MPU_GUARD_SUPPORTED 1
#else
  #define MK61_MPU_GUARD_SUPPORTED 0
#endif

namespace mpu_guard {

struct Snapshot {
  bool supported;
  bool enabled;
  bool layout_valid;
  bool sram_execute_never;
  bool stack_watermark_enabled;
  u8 available_regions;
  u8 required_regions;
  u32 ram_start;
  u32 ram_end;
  u32 static_end;
  u32 guard_base;
  u32 guard_size;
  u32 stack_budget;
  u32 initial_msp;
  u32 current_msp;
  u32 lowest_observed_msp;
  u32 watermark_remaining_stack_bytes;

  u32 sampled_remaining_stack_bytes(void) const {
    const u32 guard_end = guard_base + guard_size;
    return lowest_observed_msp >= guard_end
        ? lowest_observed_msp - guard_end : 0;
  }

  u32 remaining_stack_bytes(void) const {
    const u32 sampled = sampled_remaining_stack_bytes();
    return stack_watermark_enabled &&
           watermark_remaining_stack_bytes < sampled
        ? watermark_remaining_stack_bytes : sampled;
  }
};

bool initialize(void);
void observe_stack(void);
Snapshot statistics(void);
const char* backend_name(void);

#if MK61_MPU_GUARD_SUPPORTED && MK61_ENABLE_MPU_TEST
bool inject_guard_fault(void);
bool inject_null_fault(void);
bool inject_execute_fault(void);
#endif

} // namespace mpu_guard

#endif

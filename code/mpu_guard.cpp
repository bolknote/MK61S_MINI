#include "mpu_guard.hpp"

#include "config.h"
#include "mpu_guard_policy.hpp"
#include "stack_watermark.hpp"

#if MK61_MPU_GUARD_SUPPORTED
  #include <Arduino.h>
  #include <stm32f4xx.h>
  static_assert(__MPU_PRESENT == 1, "STM32F401/F411 must expose an MPU");
  #if MK61_ENABLE_MPU_TEST
    #include "crash_dump.hpp"
  #endif
#endif

namespace mpu_guard {
namespace {

#if MK61_MPU_GUARD_SUPPORTED

extern "C" u8 _end;

#if defined(STM32F411xE)
static constexpr mpu_guard_policy::Profile ACTIVE_PROFILE =
    mpu_guard_policy::F411_PROFILE;
#else
static constexpr mpu_guard_policy::Profile ACTIVE_PROFILE =
    mpu_guard_policy::F401_PROFILE;
#endif

static mpu_guard_policy::Layout active_layout = {};
static u8 available_region_count;
static u32 lowest_msp;
static bool hardware_enabled;

static void disable_region(u8 region) {
  MPU->RNR = region;
  MPU->RASR = 0;
}

static void configure_region(u8 region, u32 base, u32 size,
                             u32 attributes) {
  MPU->RNR = region;
  MPU->RBAR = base & MPU_RBAR_ADDR_Msk;
  MPU->RASR = attributes |
      ((u32) mpu_guard_policy::region_size_encoding(size)
       << MPU_RASR_SIZE_Pos) |
      MPU_RASR_ENABLE_Msk;
}

static constexpr u32 NO_ACCESS_ATTRIBUTES = MPU_RASR_XN_Msk;
static constexpr u32 SRAM_XN_ATTRIBUTES =
    MPU_RASR_XN_Msk |
    (3UL << MPU_RASR_AP_Pos) |
    MPU_RASR_S_Msk | MPU_RASR_C_Msk | MPU_RASR_B_Msk;

static u32 read_msp(void) {
  return __get_MSP();
}

#endif

} // namespace

bool initialize(void) {
#if MK61_MPU_GUARD_SUPPORTED
  const u32 primask = __get_PRIMASK();
  __disable_irq();

  available_region_count =
      (u8) ((MPU->TYPE & MPU_TYPE_DREGION_Msk) >> MPU_TYPE_DREGION_Pos);
  const u32 initial_msp = read_msp();
  active_layout = mpu_guard_policy::make_layout(
      ACTIVE_PROFILE, (u32) (usize) &_end, initial_msp,
      available_region_count);
  lowest_msp = initial_msp;

  MPU->CTRL = 0;
  __DSB();
  __ISB();
  for(u8 region = 0; region < available_region_count; region++) {
    disable_region(region);
  }

  if(active_layout.valid) {
    u8 region = 0;
    if(active_layout.sram_execute_never) {
      configure_region(region++, active_layout.ram_start,
                       active_layout.ram_end - active_layout.ram_start,
                       SRAM_XN_ATTRIBUTES);
    }
    configure_region(region++, 0x00000000UL, 32UL,
                     NO_ACCESS_ATTRIBUTES);
    configure_region(region++, active_layout.guard_base,
                     active_layout.guard_size, NO_ACCESS_ATTRIBUTES);
    (void) region;
    MPU->CTRL = MPU_CTRL_PRIVDEFENA_Msk | MPU_CTRL_ENABLE_Msk;
    __DSB();
    __ISB();
    hardware_enabled = (MPU->CTRL & MPU_CTRL_ENABLE_Msk) != 0;
    if(hardware_enabled) {
      // Paint only memory below the current MSP. The loop is deliberately in
      // this frame: calling a painter after capturing MSP could overwrite the
      // painter's own newly allocated frame. Stack grows downwards, so the
      // half-open [guard_end, current_msp) interval is inactive and safe.
      const u32 guard_end = active_layout.guard_end;
      const u32 current_msp = read_msp() & ~3UL;
      const u32 watermark_high = current_msp < active_layout.initial_msp
          ? current_msp : active_layout.initial_msp;
      volatile u32* const words = reinterpret_cast<volatile u32*>(guard_end);
      const usize word_count = watermark_high > guard_end
          ? (watermark_high - guard_end) / sizeof(u32) : 0;
      for(usize index = 0; index < word_count; index++) {
        words[index] = stack_watermark::pattern(index);
      }
      __DSB();
    }
  } else {
    hardware_enabled = false;
  }

  __set_PRIMASK(primask);
  return hardware_enabled;
#else
  return false;
#endif
}

void observe_stack(void) {
#if MK61_MPU_GUARD_SUPPORTED
  if(!hardware_enabled) return;
  const u32 msp = read_msp();
  if(msp < lowest_msp) lowest_msp = msp;
#endif
}

Snapshot statistics(void) {
#if MK61_MPU_GUARD_SUPPORTED
  const u32 current_msp = read_msp();
  if(hardware_enabled && current_msp < lowest_msp) lowest_msp = current_msp;
  const bool stack_watermark_enabled =
    hardware_enabled && active_layout.initial_msp > active_layout.guard_end;
  u32 watermark_remaining = 0;
  if(stack_watermark_enabled) {
    const volatile u32* const words =
      reinterpret_cast<const volatile u32*>(active_layout.guard_end);
    const usize word_count =
      (active_layout.initial_msp - active_layout.guard_end) / sizeof(u32);
    watermark_remaining = (u32)
      (stack_watermark::untouchedPrefixWords(words, word_count) * sizeof(u32));
  }
  return {
      true, hardware_enabled, active_layout.valid,
      active_layout.sram_execute_never, stack_watermark_enabled,
      available_region_count,
      active_layout.required_regions, active_layout.ram_start,
      active_layout.ram_end, active_layout.static_end,
      active_layout.guard_base, active_layout.guard_size,
      active_layout.stack_budget, active_layout.initial_msp,
      current_msp, lowest_msp, watermark_remaining};
#else
  return {false, false, false, false, false, 0, 0, 0, 0, 0, 0, 0, 0,
          0, 0, 0, 0};
#endif
}

const char* backend_name(void) {
#if MK61_MPU_GUARD_SUPPORTED
  return "ARMv7-M";
#else
  return "none";
#endif
}

#if MK61_MPU_GUARD_SUPPORTED && MK61_ENABLE_MPU_TEST

bool inject_guard_fault(void) {
  if(!hardware_enabled || !active_layout.valid) return false;
  crash_dump::update_runtime(crash_dump::RUNTIME_FAULT_TEST, 0x4D500001UL,
                             millis());
  __DSB();
  *reinterpret_cast<volatile u32*>(active_layout.guard_base) = 0x61C0FFEEUL;
  __DSB();
  return false;
}

bool inject_null_fault(void) {
  if(!hardware_enabled || !active_layout.valid) return false;
  crash_dump::update_runtime(crash_dump::RUNTIME_FAULT_TEST, 0x4D500002UL,
                             millis());
  __DSB();
  const u32 value = *reinterpret_cast<volatile u32*>(0x00000000UL);
  __asm__ volatile("" : : "r"(value) : "memory");
  return false;
}

bool inject_execute_fault(void) {
  if(!hardware_enabled || !active_layout.valid ||
     !active_layout.sram_execute_never) return false;
  crash_dump::update_runtime(crash_dump::RUNTIME_FAULT_TEST, 0x4D500003UL,
                             millis());
  static volatile u16 return_instruction[2] = {0x4770U, 0x4770U};
  using Probe = void (*)(void);
  const Probe probe = reinterpret_cast<Probe>(
      (usize) return_instruction | (usize) 1U);
  __DSB();
  __ISB();
  probe();
  return false;
}

#endif

} // namespace mpu_guard

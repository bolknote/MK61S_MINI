#ifndef MK61_MPU_GUARD_POLICY_HPP
#define MK61_MPU_GUARD_POLICY_HPP

#include "rust_types.h"

namespace mpu_guard_policy {

struct Profile {
  u32 ram_start;
  u32 ram_size;
  u32 stack_budget;
  u32 guard_size;
  bool sram_execute_never;
};

struct Layout {
  bool valid;
  u8 required_regions;
  u32 ram_start;
  u32 ram_end;
  u32 static_end;
  u32 initial_msp;
  u32 guard_base;
  u32 guard_end;
  u32 guard_size;
  u32 stack_budget;
  bool sram_execute_never;
};

static constexpr Profile F401_PROFILE = {
    0x20000000UL, 64UL * 1024UL, 6UL * 1024UL, 256UL, false};
static constexpr Profile F411_PROFILE = {
    0x20000000UL, 128UL * 1024UL, 16UL * 1024UL, 256UL, true};

// At most five regions cover every 32-byte-aligned APP of up to 20 KiB
// immediately below F411's guard. No executable padding outside its lease.
static constexpr u8 APP_REGION_COUNT = 5;

constexpr Layout with_app_overlay(Layout layout, u8 available_regions) {
  if(layout.sram_execute_never) {
    layout.required_regions += APP_REGION_COUNT;
    layout.valid = layout.valid && available_regions >= layout.required_regions;
  }
  return layout;
}

constexpr bool power_of_two(u32 value) {
  return value >= 32U && (value & (value - 1U)) == 0;
}

constexpr u8 region_size_encoding(u32 size) {
  u8 log2 = 0;
  while(size > 1U) {
    size >>= 1U;
    log2++;
  }
  return log2 > 0 ? (u8) (log2 - 1U) : 0;
}

struct AppRegion {
  u32 base;
  u32 size;
  u32 end;
  u8 disabled_subregions;
};

// Largest contiguous MPU span starting at begin and contained in [begin,end).
// Subregions let one MPU region describe several adjacent aligned blocks.
constexpr AppRegion next_app_region(u32 begin, u32 end) {
  AppRegion best = {};
  if(begin >= end || ((begin | end) & 31U) != 0) return best;
  for(u32 size = 32; size <= F411_PROFILE.ram_size; size <<= 1U) {
    const u32 base = begin & ~(size - 1U);
    const u32 step = size >= 256U ? size / 8U : size;
    if((begin & (step - 1U)) != 0) continue;
    const u32 limit = end < base + size ? end & ~(step - 1U) : base + size;
    if(limit <= begin || limit <= best.end) continue;
    const u32 first = (begin - base) / step;
    const u32 last = (limit - base) / step;
    const u8 mask = size < 256U ? 0 :
        (u8) ~(((1U << last) - 1U) & ~((1U << first) - 1U));
    best = {base, size, limit, mask};
  }
  return best;
}

constexpr Layout make_layout(const Profile& profile, u32 static_end,
                             u32 initial_msp, u8 available_regions) {
  const u32 ram_end = profile.ram_start + profile.ram_size;
  const u32 guard_base = ram_end - profile.stack_budget - profile.guard_size;
  const u32 guard_end = guard_base + profile.guard_size;
  const u8 required_regions = profile.sram_execute_never ? 3U : 2U;
  const bool profile_valid =
      power_of_two(profile.ram_size) &&
      power_of_two(profile.guard_size) &&
      profile.stack_budget > 0U &&
      profile.stack_budget + profile.guard_size < profile.ram_size &&
      (profile.ram_start & (profile.ram_size - 1U)) == 0U &&
      (guard_base & (profile.guard_size - 1U)) == 0U;
  const bool layout_valid =
      profile_valid && available_regions >= required_regions &&
      static_end >= profile.ram_start && static_end <= guard_base &&
      initial_msp >= guard_end && initial_msp <= ram_end;
  return {
      layout_valid, required_regions, profile.ram_start, ram_end,
      static_end, initial_msp, guard_base, guard_end, profile.guard_size,
      profile.stack_budget, profile.sram_execute_never};
}

} // namespace mpu_guard_policy

#endif

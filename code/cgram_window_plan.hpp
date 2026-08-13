#ifndef MK61_CGRAM_WINDOW_PLAN_HPP
#define MK61_CGRAM_WINDOW_PLAN_HPP

#include "rust_types.h"

// A compact, allocation-free plan for one complete character-display window.
// Some controllers reserve fixed CGRAM slots for product symbols, while the
// remaining slots may be borrowed for Unicode glyphs absent from CGROM.
namespace cgram_window_plan {

static constexpr u8 SLOT_COUNT = 8;

struct Plan {
  u16 codepoints[SLOT_COUNT];
  u8 slots[SLOT_COUNT];
  u8 count;
  u8 reserved_mask;
  bool overflow;
};

inline i8 slotFor(const Plan& plan, u16 codepoint) {
  for(u8 index = 0; index < plan.count; index++) {
    if(plan.codepoints[index] == codepoint) return (i8) plan.slots[index];
  }
  return -1;
}

inline u8 usedMask(const Plan& plan) {
  u8 mask = plan.reserved_mask;
  for(u8 index = 0; index < plan.count; index++) {
    mask |= (u8) 1u << plan.slots[index];
  }
  return mask;
}

inline i8 firstFreeSlot(const Plan& plan) {
  const u8 used = usedMask(plan);
  for(u8 slot = 0; slot < SLOT_COUNT; slot++) {
    if((used & ((u8) 1u << slot)) == 0) return (i8) slot;
  }
  return -1;
}

inline void removeAt(Plan& plan, u8 index) {
  if(index >= plan.count) return;
  for(u8 next = (u8) (index + 1u); next < plan.count; next++) {
    plan.codepoints[next - 1u] = plan.codepoints[next];
    plan.slots[next - 1u] = plan.slots[next];
  }
  plan.count--;
}

inline void reserve(Plan& plan, u8 slot) {
  if(slot >= SLOT_COUNT) {
    plan.overflow = true;
    return;
  }
  const u8 bit = (u8) 1u << slot;
  if((plan.reserved_mask & bit) != 0) return;
  plan.reserved_mask |= bit;

  // A fixed symbol can appear after a dynamic glyph during a multi-row scan.
  // Relocate that glyph deterministically; if all other slots are occupied,
  // evict it so write_text() emits the documented fallback instead of showing
  // the wrong glyph in either cell.
  for(u8 index = 0; index < plan.count; index++) {
    if(plan.slots[index] != slot) continue;
    const i8 replacement = firstFreeSlot(plan);
    if(replacement >= 0) {
      plan.slots[index] = (u8) replacement;
    } else {
      removeAt(plan, index);
      plan.overflow = true;
    }
    return;
  }
}

inline bool add(Plan& plan, u16 codepoint) {
  if(slotFor(plan, codepoint) >= 0) return true;
  if(plan.count >= SLOT_COUNT) {
    plan.overflow = true;
    return false;
  }
  const i8 slot = firstFreeSlot(plan);
  if(slot < 0) {
    plan.overflow = true;
    return false;
  }
  plan.codepoints[plan.count] = codepoint;
  plan.slots[plan.count] = (u8) slot;
  plan.count++;
  return true;
}

} // namespace cgram_window_plan

#endif

#ifndef MK61_CORE_PACKED_AMK_HPP
#define MK61_CORE_PACKED_AMK_HPP

#include "rust_types.h"

// Candidate Cortex-M4 DSP optimization for the operation shared by all three
// IK chips at every microtick.  Each raw AMK byte in 0..67 is incremented iff
// it is at least 60 and the corresponding L latch is zero.  Bytes are separate
// lanes: no carry or state may cross from one emulated chip to another.
namespace core_packed_amk {

struct Selection {
  u8 ik1302;
  u8 ik1303;
  u8 ik1306;
};

constexpr u8 adjust_reference(u8 raw, bool latch_nonzero) {
  return (raw >= 60U && !latch_nonzero) ? (u8) (raw + 1U) : raw;
}

constexpr Selection select_reference(
    u8 ik1302, u8 ik1303, u8 ik1306,
    bool l1302, bool l1303, bool l1306) {
  return {
    adjust_reference(ik1302, l1302),
    adjust_reference(ik1303, l1303),
    adjust_reference(ik1306, l1306)
  };
}

constexpr u32 pack(u8 lane0, u8 lane1, u8 lane2, u8 lane3 = 0) {
  return (u32) lane0 | ((u32) lane1 << 8U) |
         ((u32) lane2 << 16U) | ((u32) lane3 << 24U);
}

constexpr Selection unpack(u32 value) {
  return {
    (u8) value,
    (u8) (value >> 8U),
    (u8) (value >> 16U)
  };
}

// Portable model of the exact USUB8(GE)+SEL sequence.  It is intentionally
// separate from the scalar reference so exhaustive host tests validate lane
// order, thresholds and the unused fourth byte.
constexpr Selection select_instruction_model(
    u8 ik1302, u8 ik1303, u8 ik1306,
    bool l1302, bool l1303, bool l1306) {
  const u32 raw = pack(ik1302, ik1303, ik1306);
  const u32 threshold = pack(
      l1302 ? 0xFFU : 60U,
      l1303 ? 0xFFU : 60U,
      l1306 ? 0xFFU : 60U,
      0xFFU);
  u32 selected = 0;
  for(u8 lane = 0; lane < 4; lane++) {
    const u32 shift = (u32) lane * 8U;
    const u8 value = (u8) (raw >> shift);
    const u8 floor = (u8) (threshold >> shift);
    const u8 result = value >= floor ? (u8) (value + 1U) : value;
    selected |= (u32) result << shift;
  }
  return unpack(selected);
}

inline Selection select(
    u8 ik1302, u8 ik1303, u8 ik1306,
    bool l1302, bool l1303, bool l1306) {
#if defined(__ARM_FEATURE_DSP) && (__ARM_FEATURE_DSP == 1)
  const u32 raw = pack(ik1302, ik1303, ik1306);
  const u32 threshold = pack(
      l1302 ? 0xFFU : 60U,
      l1303 ? 0xFFU : 60U,
      l1306 ? 0xFFU : 60U,
      0xFFU);
  // USUB8 sets one GE flag per byte. SEL then chooses raw+1 only for lanes
  // whose unsigned raw value reached their threshold. Raw AMK is at most 67,
  // so adding 0x01010101 cannot carry between bytes.
  (void) __USUB8(raw, threshold);
  return unpack(__SEL(raw + 0x01010101UL, raw));
#else
  return select_instruction_model(
      ik1302, ik1303, ik1306, l1302, l1303, l1306);
#endif
}

} // namespace core_packed_amk

#endif

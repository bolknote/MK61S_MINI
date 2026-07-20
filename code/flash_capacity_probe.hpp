#ifndef FLASH_CAPACITY_PROBE_HPP
#define FLASH_CAPACITY_PROBE_HPP

#include "rust_types.h"

namespace flash_capacity_probe {

static constexpr u32 SECTOR_SIZE = 4096;
static constexpr u32 MIN_CAPACITY = 128U * 1024U;
static constexpr u32 MAX_CAPACITY = 128U * 1024U * 1024U;
static constexpr u32 THREE_BYTE_LIMIT = 16U * 1024U * 1024U;

// complete=false announces a candidate before any destructive access;
// complete=true reports whether that boundary proved physically distinct.
using ProbeProgress = void (*)(u32 candidate, bool complete, bool distinct);

static bool power_of_two(u32 value) {
  return value != 0 && (value & (value - 1)) == 0;
}

// Most serial NOR devices encode the byte-capacity as 2^N. Winbond's
// W25Q512/W25Q01 family uses the continuation values 0x20/0x21 instead of
// 0x1A/0x1B; accepting both forms is harmless because detect() still verifies
// the physical boundary before C5 trusts the result.
inline u32 jedec_capacity_bytes(u8 capacity_code) {
  if(capacity_code >= 0x10 && capacity_code <= 0x1B) {
    return (u32) 1UL << capacity_code;
  }
  if(capacity_code == 0x20) return 64U * 1024U * 1024U;
  if(capacity_code == 0x21) return 128U * 1024U * 1024U;
  return 0;
}

static void make_marker(u8* out, u32 candidate, u8 role) {
  // Complementary payloads make an aliased second program require forbidden
  // 0->1 transitions. Even a driver without read-back verification is caught
  // by the final comparison of both locations.
  const u8 salt = role == 0 ? 0xA5 : 0x5A;
  for(u8 i = 0; i < 32; i++) {
    const u8 size_byte = (u8) (candidate >> ((i & 3) * 8));
    out[i] = (u8) (salt ^ size_byte ^ (u8) (i * 29));
  }
  out[0] = 'C';
  out[1] = '5';
  out[2] = role;
  out[3] = (u8) ~role;
}

template<typename RawFlash>
static bool marker_matches(RawFlash& flash, u32 address,
                           const u8* expected) {
  u8 recovered[32];
  if(!flash.rawRead(address, recovered, sizeof(recovered))) return false;
  for(u8 i = 0; i < sizeof(recovered); i++) {
    if(recovered[i] != expected[i]) return false;
  }
  return true;
}

template<typename RawFlash>
static bool prepare_address_width_guards(RawFlash& flash, u32 candidate,
                                         u32 lower_address,
                                         u32 upper_address,
                                         u32& lower_guard_address,
                                         u32& upper_guard_address,
                                         u8* lower_guard,
                                         u8* upper_guard) {
  if(candidate <= THREE_BYTE_LIMIT) return flash.rawPrepare(candidate);

  // A 3-byte-only counterfeit may ignore EN4B. It then consumes A31..A8 as
  // the address and mistakes A7..A0 for the first data byte. Protect those
  // two low "shadow" sectors before issuing any 4-byte command. A genuine
  // 4-byte access leaves the guards intact; an ignored EN4B erases them.
  if(!flash.rawPrepare(MIN_CAPACITY)) return false;
  const u32 lower_shadow = (lower_address >> 8) & ~(SECTOR_SIZE - 1U);
  const u32 upper_shadow = (upper_address >> 8) & ~(SECTOR_SIZE - 1U);
  lower_guard_address = lower_shadow + 64;
  upper_guard_address = upper_shadow + 64;
  make_marker(lower_guard, candidate, 2);
  make_marker(upper_guard, candidate, 3);
  if(!flash.rawEraseSector(upper_shadow) ||
     (lower_shadow != upper_shadow && !flash.rawEraseSector(lower_shadow)) ||
     !flash.rawWrite(lower_guard_address, lower_guard, 32) ||
     !flash.rawWrite(upper_guard_address, upper_guard, 32) ||
     !marker_matches(flash, lower_guard_address, lower_guard) ||
     !marker_matches(flash, upper_guard_address, upper_guard)) return false;
  return flash.rawPrepare(candidate);
}

template<typename RawFlash>
static bool boundary_is_distinct(RawFlash& flash, u32 candidate) {
  if(candidate < MIN_CAPACITY || !power_of_two(candidate)) return false;
  const u32 lower_address = candidate / 2 - SECTOR_SIZE;
  const u32 upper_address = candidate - SECTOR_SIZE;
  u32 lower_guard_address = 0;
  u32 upper_guard_address = 0;
  u8 lower_marker[32];
  u8 upper_marker[32];
  u8 lower_guard[32];
  u8 upper_guard[32];
  u8 recovered_lower[32];
  u8 recovered_upper[32];
  make_marker(lower_marker, candidate, 0);
  make_marker(upper_marker, candidate, 1);
  if(!prepare_address_width_guards(flash, candidate, lower_address,
                                   upper_address, lower_guard_address,
                                   upper_guard_address, lower_guard,
                                   upper_guard)) return false;

  // Erase the possible alias first and the known lower location second. If
  // both addresses alias, the following two distinct programs expose it.
  if(!flash.rawEraseSector(upper_address) ||
     !flash.rawEraseSector(lower_address) ||
     !flash.rawWrite(lower_address, lower_marker, sizeof(lower_marker)) ||
     !flash.rawWrite(upper_address, upper_marker, sizeof(upper_marker)) ||
     !flash.rawRead(lower_address, recovered_lower, sizeof(recovered_lower)) ||
     !flash.rawRead(upper_address, recovered_upper, sizeof(recovered_upper))) return false;
  for(u8 i = 0; i < sizeof(lower_marker); i++) {
    if(recovered_lower[i] != lower_marker[i] ||
       recovered_upper[i] != upper_marker[i]) return false;
  }
  if(candidate > THREE_BYTE_LIMIT) {
    if(!flash.rawPrepare(MIN_CAPACITY) ||
       !marker_matches(flash, lower_guard_address, lower_guard) ||
       !marker_matches(flash, upper_guard_address, upper_guard)) return false;
  }
  return true;
}

// Destructive only in the two probe sectors of each candidate. Call solely
// when neither C5 locator is valid. Standard SPI NOR capacities are powers of
// two, so binary-searching their exponents minimizes erase cycles while still
// finding the largest physically distinct address range.
template<typename RawFlash>
bool detect(RawFlash& flash, u32 reported_capacity, u32& capacity,
            ProbeProgress progress = nullptr) {
  // The report is deliberately not a search bound. Counterfeit or mangled
  // identification data can be wrong in either direction, and C5 promises to
  // use the whole physically addressable device. There are only eleven
  // supported power-of-two sizes, so a full-range binary search still needs
  // at most four boundary checks.
  (void) reported_capacity;
  u8 low_exponent = 17; // 128 KiB
  u8 high_exponent = 27; // 128 MiB
  u32 best = 0;
  while(low_exponent <= high_exponent) {
    const u8 exponent = (u8) (low_exponent +
        (high_exponent - low_exponent) / 2);
    const u32 candidate = (u32) 1UL << exponent;
    if(progress != nullptr) progress(candidate, false, false);
    const bool distinct = boundary_is_distinct(flash, candidate);
    if(progress != nullptr) progress(candidate, true, distinct);
    if(distinct) {
      best = candidate;
      low_exponent = (u8) (exponent + 1);
    } else {
      high_exponent = (u8) (exponent - 1);
    }
  }
  capacity = best;
  return best != 0;
}

} // namespace flash_capacity_probe

#endif

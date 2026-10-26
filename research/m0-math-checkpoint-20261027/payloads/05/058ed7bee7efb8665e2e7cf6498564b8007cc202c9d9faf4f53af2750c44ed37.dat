// SPDX-License-Identifier: 0BSD
// ARM-Thumb transform from XZ Embedded (Lasse Collin, Igor Pavlov), adapted
// for a complete APP image at filter position zero, in place.
// https://github.com/tukaani-project/xz-embedded/blob/master/linux/lib/xz/xz_dec_bcj.c
#ifndef MK61_ARM_THUMB_BCJ_HPP
#define MK61_ARM_THUMB_BCJ_HPP

#include "rust_types.h"

namespace arm_thumb_bcj {

inline void transform(u8* data, u32 size, bool encode) {
  if(size < 4) return;
  for(u32 i = 0; i <= size - 4; i += 2) {
    if((data[i + 1] & 0xF8U) != 0xF0U ||
       (data[i + 3] & 0xF8U) != 0xF8U) continue;
    u32 address = ((u32) (data[i + 1] & 7U) << 19) |
        ((u32) data[i] << 11) | ((u32) (data[i + 3] & 7U) << 8) |
        data[i + 2];
    address <<= 1;
    address = encode ? address + i + 4 : address - i - 4;
    address >>= 1;
    data[i + 1] = (u8) (0xF0U | ((address >> 19) & 7U));
    data[i] = (u8) (address >> 11);
    data[i + 3] = (u8) (0xF8U | ((address >> 8) & 7U));
    data[i + 2] = (u8) address;
    i += 2;
  }
}

} // namespace arm_thumb_bcj
#endif

/*
 * ZX0 format and original decompressor:
 * Copyright (c) 2021, Einar Saukas. All rights reserved.
 *
 * Redistribution and use in source and binary forms, with or without
 * modification, are permitted provided that the following conditions are met:
 * 1. Redistributions of source code must retain the above copyright notice,
 *    this list of conditions and the following disclaimer.
 * 2. Redistributions in binary form must reproduce the above copyright
 *    notice, this list of conditions and the following disclaimer in the
 *    documentation and/or other materials provided with the distribution.
 * 3. Neither the name of the copyright holder nor the names of its
 *    contributors may be used to endorse or promote products derived from
 *    this software without specific prior written permission.
 *
 * THIS SOFTWARE IS PROVIDED BY THE COPYRIGHT HOLDERS AND CONTRIBUTORS "AS IS"
 * AND ANY EXPRESS OR IMPLIED WARRANTIES ARE DISCLAIMED. IN NO EVENT SHALL THE
 * COPYRIGHT HOLDER OR CONTRIBUTORS BE LIABLE FOR ANY DIRECT, INDIRECT,
 * INCIDENTAL, SPECIAL, EXEMPLARY, OR CONSEQUENTIAL DAMAGES.
 */

#include "zx0.hpp"

namespace zx0 {
namespace {

class BitInput {
  public:
    BitInput(const Input& input, u32 size)
      : input_(input), remaining_(size), bit_value_(0), bit_mask_(0),
        byte_value_(0) {}

    i32 byte(void) {
      if(remaining_ == 0 ||
         !input_.next(input_.context, byte_value_)) return -1;
      remaining_--;
      return byte_value_;
    }

    i32 bit(void) {
      bit_mask_ >>= 1;
      if(bit_mask_ == 0) {
        bit_mask_ = 0x80;
        const i32 value = byte();
        if(value < 0) return -1;
        bit_value_ = (u8) value;
      }
      return (bit_value_ & bit_mask_) != 0;
    }

    // Корректный gamma-код всегда не меньше 1, поэтому 0 означает ошибку.
    // first передаёт уже прочитанный первый бит; -2 требует прочитать его.
    u32 gamma(bool inverted, i32 first = -2) {
      u32 result = 1;
      i32 current = first == -2 ? bit() : first;
      while(true) {
        if(current < 0) return 0;
        if(current != 0) return result;
        if(result > 0x7FFFFFFFUL) return 0;
        current = bit();
        if(current < 0) return 0;
        result = (result << 1) |
                 ((u32) current ^ (inverted ? 1U : 0U));
        current = bit();
      }
    }

    bool exhausted(void) const { return remaining_ == 0; }

  private:
    Input input_;
    u32 remaining_;
    u8 bit_value_;
    u8 bit_mask_;
    u8 byte_value_;
};

static bool copy_match(u8*& output, const u8* begin, const u8* end,
                       u32 offset, u32 length) {
  if(offset > (u32) (output - begin) ||
     length > (u32) (end - output)) return false;
  const u8* source = output - offset;
  while(length-- != 0) *output++ = *source++;
  return true;
}

} // namespace

bool decode(const Input& source, u32 source_size,
            u8* output, u32 capacity, u32& written) {
  written = 0;
  if(source.next == nullptr || source_size == 0 ||
     output == nullptr || capacity == 0) return false;

  BitInput input(source, source_size);
  u8* current = output;
  u8* const end = output + capacity;
  u32 last_offset = 1;
  i32 selector = 0;

copy_literals:
  u32 length = input.gamma(false);
  if(length == 0 || length > (u32) (end - current)) goto fail;
  while(length-- != 0) {
    const i32 value = input.byte();
    if(value < 0) goto fail;
    *current++ = (u8) value;
  }
  selector = input.bit();
  if(selector < 0) goto fail;
  if(selector != 0) goto copy_new_offset;

  length = input.gamma(false);
  if(length == 0 ||
     !copy_match(current, output, end, last_offset, length)) goto fail;
  selector = input.bit();
  if(selector < 0) goto fail;
  if(selector == 0) goto copy_literals;

copy_new_offset:
  last_offset = input.gamma(true);
  if(last_offset == 0) goto fail;
  if(last_offset == 256U) {
    written = (u32) (current - output);
    return current == end && input.exhausted();
  }
  if(last_offset > 256U) goto fail;
  {
    const i32 value = input.byte();
    if(value < 0) goto fail;
    last_offset = last_offset * 128U - ((u32) value >> 1);
    // Младший бит байта смещения — первый бит следующего gamma-кода ZX0.
    length = input.gamma(false, value & 1);
  }
  if(length == 0 || length == 0xFFFFFFFFUL ||
     !copy_match(current, output, end, last_offset, length + 1U)) goto fail;
  selector = input.bit();
  if(selector < 0) goto fail;
  if(selector != 0) goto copy_new_offset;
  goto copy_literals;

fail:
  written = (u32) (current - output);
  return false;
}

} // namespace zx0

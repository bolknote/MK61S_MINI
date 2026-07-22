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
        last_byte_(0), backtrack_(false), failed_(input.next == nullptr) {}

    bool byte(u8& value) {
      if(failed_ || remaining_ == 0 ||
         !input_.next(input_.context, value)) {
        failed_ = true;
        return false;
      }
      remaining_--;
      last_byte_ = value;
      return true;
    }

    bool bit(u32& value) {
      if(backtrack_) {
        backtrack_ = false;
        value = last_byte_ & 1U;
        return true;
      }
      bit_mask_ >>= 1;
      if(bit_mask_ == 0) {
        bit_mask_ = 0x80;
        if(!byte(bit_value_)) return false;
      }
      value = (bit_value_ & bit_mask_) != 0;
      return true;
    }

    bool gamma(bool inverted, u32& value) {
      u32 result = 1;
      u32 current = 0;
      while(true) {
        if(!bit(current)) return false;
        if(current != 0) break;
        if(result > 0x7FFFFFFFUL || !bit(current)) return false;
        result = (result << 1) | (current ^ (inverted ? 1U : 0U));
      }
      value = result;
      return true;
    }

    void backtrack(void) { backtrack_ = true; }
    bool exhausted(void) const { return !failed_ && remaining_ == 0; }

  private:
    Input input_;
    u32 remaining_;
    u8 bit_value_;
    u8 bit_mask_;
    u8 last_byte_;
    bool backtrack_;
    bool failed_;
};

static bool copy_match(u8* output, u32 capacity, u32& written,
                       u32 offset, u32 length) {
  if(offset == 0 || offset > written || length > capacity - written) {
    return false;
  }
  while(length-- != 0) {
    output[written] = output[written - offset];
    written++;
  }
  return true;
}

} // namespace

bool decode(const Input& source, u32 source_size,
            u8* output, u32 capacity, u32& written) {
  written = 0;
  if(source.next == nullptr || source_size == 0 ||
     output == nullptr || capacity == 0) return false;

  BitInput input(source, source_size);
  u32 last_offset = 1;
  u32 length = 0;
  u32 selector = 0;
  u8 value = 0;

copy_literals:
  if(!input.gamma(false, length) || length > capacity - written) return false;
  while(length-- != 0) {
    if(!input.byte(output[written])) return false;
    written++;
  }
  if(!input.bit(selector)) return false;
  if(selector != 0) goto copy_new_offset;

  if(!input.gamma(false, length) ||
     !copy_match(output, capacity, written, last_offset, length) ||
     !input.bit(selector)) return false;
  if(selector == 0) goto copy_literals;

copy_new_offset:
  if(!input.gamma(true, last_offset)) return false;
  if(last_offset == 256U) {
    return written == capacity && input.exhausted();
  }
  if(last_offset > 256U || !input.byte(value)) return false;
  last_offset = last_offset * 128U - (value >> 1);
  input.backtrack();
  if(!input.gamma(false, length) || length == 0xFFFFFFFFUL ||
     !copy_match(output, capacity, written, last_offset, length + 1U) ||
     !input.bit(selector)) return false;
  if(selector != 0) goto copy_new_offset;
  goto copy_literals;
}

} // namespace zx0

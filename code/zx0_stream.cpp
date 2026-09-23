#include "zx0_stream.hpp"

// ZX0 v2 format by Einar Saukas. See zx0.cpp for the format's BSD notice.
namespace zx0 {

void StreamDecoder::gamma(State state) {
  state_ = state;
  gamma_ = 1;
  control_ = true;
}

void StreamDecoder::reset(const Memory& memory) {
  memory_ = memory;
  written_ = remaining_ = 0;
  offset_ = 1;
  bits_ = mask_ = 0;
  gamma(LITERAL_LENGTH);
}

bool StreamDecoder::match(u16 length) {
  if(offset_ == 0 || offset_ > written_ ||
     length > memory_.capacity - written_) return fail();
  while(length-- != 0) {
    u8 value;
    if(!memory_.read(memory_.context, written_ - offset_, value) ||
       !memory_.write(memory_.context, written_, value)) return fail();
    ++written_;
  }
  state_ = AFTER_MATCH;
  return true;
}

bool StreamDecoder::feed(u8 value) {
  if(state_ == BAD || state_ == DONE || memory_.read == nullptr ||
     memory_.write == nullptr) return fail();
  bool available = true;
  for(;;) {
    if(state_ == LITERALS || state_ == OFFSET_LOW) {
      if(!available) return true;
      available = false;
      if(state_ == LITERALS) {
        if(!memory_.write(memory_.context, written_, value)) return fail();
        ++written_;
        if(--remaining_ == 0) state_ = AFTER_LITERAL;
      } else {
        offset_ = gamma_ * 128U - (value >> 1);
        gamma(MATCH_LENGTH);
        // Low offset bit supplies the first gamma control bit.
        if(value & 1U) {
          if(!match(2)) return false;
        } else control_ = false;
      }
      continue;
    }

    if(mask_ == 0) {
      if(!available) return true;
      available = false;
      bits_ = value;
      mask_ = 0x80;
    }
    const bool bit = (bits_ & mask_) != 0;
    mask_ >>= 1;
    if(state_ == AFTER_LITERAL) {
      gamma(bit ? OFFSET_HIGH : LAST_LENGTH);
    } else if(state_ == AFTER_MATCH) {
      gamma(bit ? OFFSET_HIGH : LITERAL_LENGTH);
    } else if(!control_) {
      const u16 limit = state_ == OFFSET_HIGH ? 256U : memory_.capacity;
      const u32 next = (u32(gamma_) << 1) | (bit ^ (state_ == OFFSET_HIGH));
      if(next > limit) return fail();
      gamma_ = (u16) next;
      control_ = true;
    } else if(!bit) {
      control_ = false;
    } else if(state_ == OFFSET_HIGH) {
      if(gamma_ == 256U) {
        // The compressor pads its final control byte with zero bits.
        if(available || (mask_ != 0 &&
            (bits_ & ((u16(mask_) << 1) - 1U)) != 0)) return fail();
        state_ = DONE;
        return true;
      }
      state_ = OFFSET_LOW;
    } else if(state_ == LITERAL_LENGTH) {
      if(gamma_ > memory_.capacity - written_) return fail();
      remaining_ = gamma_;
      state_ = LITERALS;
    } else {
      const u32 length = gamma_ + (state_ == MATCH_LENGTH ? 1U : 0U);
      if(length > u32(memory_.capacity - written_) || !match((u16) length)) return fail();
    }
  }
}

} // namespace zx0

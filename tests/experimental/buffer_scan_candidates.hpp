#ifndef MK61_BUFFER_SCAN_CANDIDATES_HPP
#define MK61_BUFFER_SCAN_CANDIDATES_HPP

// Experimental kernels only. Keeping these out of the firmware makes an
// unsuccessful measurement cheap and leaves the production semantics intact.
#include "usb_screen_protocol.hpp"
#include "utf8_codec.hpp"
#if defined(__ARM_FEATURE_SIMD32)
#include <arm_acle.h>
#endif

namespace buffer_scan_candidates {

inline u32 load_word(const u8* data) {
  u32 word;
  __builtin_memcpy(&word, data, sizeof(word));
  return word;
}

// These three functions count UTF-8 leading bytes. Their contract requires
// already valid UTF-8; unlike the strict decoder they do not validate input.
inline usize count_valid_scalar(const u8* data, usize size) {
  usize count = size;
  for(usize i = 0; i < size; ++i)
    count -= utf8_codec::is_continuation(data[i]);
  return count;
}

inline usize count_valid_swar(const u8* data, usize size) {
  usize count = size;
  usize offset = 0;
  for(; size - offset >= 4; offset += 4) {
    const u32 word = load_word(data + offset);
    const u32 ones = (word & ~(word << 1) & 0x80808080U) >> 7;
    count -= (ones * 0x01010101U) >> 24;
  }
  for(; offset < size; ++offset)
    count -= utf8_codec::is_continuation(data[offset]);
  return count;
}

inline usize count_valid_dsp(const u8* data, usize size) {
#if defined(__ARM_FEATURE_SIMD32)
  usize count = size;
  usize offset = 0;
  for(; size - offset >= 4; offset += 4) {
    const u32 word = load_word(data + offset);
    (void) __ssub8((int8x4_t) 0xBFBFBFBFU, (int8x4_t) word);
    count -= __usada8(__sel(0x01010101U, 0U), 0U, 0U);
  }
  for(; offset < size; ++offset)
    count -= utf8_codec::is_continuation(data[offset]);
  return count;
#else
  return count_valid_swar(data, size);
#endif
}

inline usize count_strict_scalar(const u8* data, usize size) {
  usize count = 0;
  for(usize offset = 0; offset < size; ++count)
    offset += utf8_codec::decode(data + offset, size - offset).size;
  return count;
}

inline usize count_strict_ascii(const u8* data, usize size) {
  usize count = 0;
  usize offset = 0;
  while(offset < size) {
    if(data[offset] < 0x80U) {
      while(size - offset >= 4 &&
            (load_word(data + offset) & 0x80808080U) == 0) {
        offset += 4;
        count += 4;
      }
      if(offset == size) break;
      if(data[offset] < 0x80U) {
        ++offset;
        ++count;
        continue;
      }
    }
    offset += utf8_codec::decode(data + offset, size - offset).size;
    ++count;
  }
  return count;
}

inline usize equal_prefix(const u8* a, const u8* b, usize size) {
  usize offset = 0;
  while(size - offset >= 4 && load_word(a + offset) == load_word(b + offset))
    offset += 4;
  while(offset < size && a[offset] == b[offset]) ++offset;
  return offset;
}

inline usize repeated_count(const u8* data, usize size, usize at) {
  const usize available = size - at;
  const usize limit = available < 128 ? available : 128;
  if(limit == 1 || data[at + 1] != data[at]) return 1;
  usize count = 2;
  const u32 repeated = (u32) data[at] * 0x01010101U;
  while(limit - count >= 4 && load_word(data + at + count) == repeated)
    count += 4;
  while(count < limit && data[at + count] == data[at]) ++count;
  return count;
}

inline usb_screen_protocol::Status packbits_encode(
    const u8* input, usize size, u8* output, usize capacity, usize& written) {
  using namespace usb_screen_protocol;
  written = 0;
  if((input == nullptr && size != 0) || output == nullptr)
    return Status::INVALID_ARGUMENT;
  usize source = 0;
  usize target = 0;
  while(source < size) {
    const usize run = repeated_count(input, size, source);
    if(run >= 3) {
      if(capacity - target < 2) return Status::OUTPUT_TOO_SMALL;
      output[target++] = (u8) (257 - run);
      output[target++] = input[source];
      source += run;
      continue;
    }
    const usize literal_start = source;
    source += run;
    while(source < size && source - literal_start < 128) {
      const usize next_run = repeated_count(input, size, source);
      if(next_run >= 3) break;
      const usize available = 128 - (source - literal_start);
      source += next_run < available ? next_run : available;
    }
    const usize literal_size = source - literal_start;
    if(capacity - target < literal_size + 1) return Status::OUTPUT_TOO_SMALL;
    output[target++] = (u8) (literal_size - 1);
    __builtin_memcpy(output + target, input + literal_start, literal_size);
    target += literal_size;
  }
  written = target;
  return Status::OK;
}

inline usb_screen_protocol::Status plan_diff(
    const u8* previous, const u8* current, usb_screen_protocol::DiffPlan& plan,
    bool force_keyframe = false) {
  using namespace usb_screen_protocol;
  plan.count = 0;
  plan.keyframe = false;
  if(previous == nullptr || current == nullptr) return Status::INVALID_ARGUMENT;
  const auto keyframe = [&]() {
    plan.count = PAGE_COUNT;
    plan.keyframe = true;
    for(u8 page = 0; page < PAGE_COUNT; ++page)
      plan.runs[page] = {0, page, (u8) SCREEN_WIDTH};
  };
  if(force_keyframe) { keyframe(); return Status::OK; }
  constexpr usize overhead = RECT_HEADER_SIZE + HEADER_SIZE + CRC_SIZE;
  usize total_cost = 0;
  for(u8 page = 0; page < PAGE_COUNT; ++page) {
    const usize base = (usize) page * SCREEN_WIDTH;
    const u8 saved_count = plan.count;
    usize page_cost = 0;
    bool overflow = false;
    u16 x = 0;
    while(x < SCREEN_WIDTH) {
      x += (u16) equal_prefix(previous + base + x, current + base + x,
                              SCREEN_WIDTH - x);
      if(x == SCREEN_WIDTH) break;
      const u16 first = x;
      u16 last = x;
      u8 gap = 0;
      ++x;
      while(x < SCREEN_WIDTH) {
        if(previous[base + x] != current[base + x]) { last = x; gap = 0; }
        else if(++gap > DIFF_MERGE_GAP) break;
        ++x;
      }
      if(plan.count >= MAX_DIFF_RUNS) { overflow = true; break; }
      plan.runs[plan.count++] = {(u8) first, page, (u8) (last - first + 1)};
      page_cost += last - first + 1 + overhead;
    }
    if(overflow || page_cost >= SCREEN_WIDTH + overhead) {
      plan.count = saved_count;
      if(plan.count >= MAX_DIFF_RUNS) { keyframe(); return Status::OK; }
      plan.runs[plan.count++] = {0, page, (u8) SCREEN_WIDTH};
      page_cost = SCREEN_WIDTH + overhead;
    }
    total_cost += page_cost;
  }
  if(total_cost >= (usize) PAGE_COUNT * (SCREEN_WIDTH + overhead)) keyframe();
  return Status::OK;
}

} // namespace buffer_scan_candidates
#endif

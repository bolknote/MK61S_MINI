// Ordinary APP benchmark: matched kernels run from the same SRAM image.
// The report is transported as framebuffer bytes, with USB Screen CRC checks.
#if defined(BUFFER_SCAN_BENCH_O3)
#pragma GCC optimize ("O3")
#endif
#include "mk61_app.h"
#include "buffer_scan_candidates.hpp"
#include "../../code/usb_screen_protocol.cpp"

namespace candidate = buffer_scan_candidates;
namespace protocol = usb_screen_protocol;

#define KERNEL __attribute__((noipa, flatten, aligned(16)))
alignas(4) static u8 previous_storage[protocol::FRAME_BYTES + 4];
alignas(4) static u8 input_storage[protocol::FRAME_BYTES + 4];
static u8 packed[256], packed_reference[256];
static u8 report[protocol::FRAME_BYTES];
static protocol::DiffPlan plan;
static volatile usize checksum;
static u32 failures, rows;
static u8* const input = input_storage + 1;
static u8* const previous = previous_storage + 1;

extern "C" KERNEL usize bench_valid_scalar(const u8* p, usize n) {
  return candidate::count_valid_scalar(p, n);
}
extern "C" KERNEL usize bench_valid_dsp(const u8* p, usize n) {
  return candidate::count_valid_dsp(p, n);
}
extern "C" KERNEL usize bench_valid_swar(const u8* p, usize n) {
  return candidate::count_valid_swar(p, n);
}
extern "C" KERNEL usize bench_strict_scalar(const u8* p, usize n) {
  return candidate::count_strict_scalar(p, n);
}
extern "C" KERNEL usize bench_strict_ascii(const u8* p, usize n) {
  return candidate::count_strict_ascii(p, n);
}
extern "C" KERNEL usize bench_diff_scalar(const u8* p, usize n) {
  (void) n;
  (void) protocol::plan_diff(previous, p, plan);
  return ((usize) plan.count << 1) | plan.keyframe;
}
extern "C" KERNEL usize bench_diff_word(const u8* p, usize n) {
  (void) n;
  (void) candidate::plan_diff(previous, p, plan);
  return ((usize) plan.count << 1) | plan.keyframe;
}
extern "C" KERNEL usize bench_packbits_scalar(const u8* p, usize n) {
  usize written = 0;
  (void) protocol::packbits_encode(p, n, packed, sizeof(packed), written);
  return written;
}
extern "C" KERNEL usize bench_packbits_word(const u8* p, usize n) {
  usize written = 0;
  (void) candidate::packbits_encode(p, n, packed, sizeof(packed), written);
  return written;
}

using Function = usize (*)(const u8*, usize);
static const Function kernels[] = {
  bench_valid_scalar, bench_valid_dsp, bench_valid_swar,
  bench_strict_scalar, bench_strict_ascii, bench_diff_scalar, bench_diff_word,
  bench_packbits_scalar, bench_packbits_word
};

static volatile u32& reg(u32 address) {
  return *(volatile u32*) (uintptr_t) address;
}
static u32 cycles() {
  __asm__ __volatile__("" ::: "memory");
  const u32 value = reg(0xE0001004U);
  __asm__ __volatile__("" ::: "memory");
  return value;
}
static void write8(usize at, u8 value) {
  // Leave the disk-activity overlay's top-right 16x16 pixels out of the wire
  // report. The display may update them independently of this APP.
  usize physical = at;
  if(at >= 176) physical += 16;
  if(at >= 352) physical += 16;
  report[physical] = value;
}
static void write32(usize at, u32 value) {
  for(u8 i = 0; i < 4; ++i) write8(at + i, (u8) (value >> (i * 8)));
}

static void run_group(u8 first, u8 count, u8 dataset, usize size) {
  constexpr u8 samples = 7;
  u32 measurements[5][samples];
  const usize iterations = size <= 16 ? 512 : size <= 64 ? 256 : 64;
  for(u8 k = 0; k < count; ++k)
    for(u8 warmup = 0; warmup < 8; ++warmup)
      checksum += kernels[first + k](input, size);
  for(u8 sample = 0; sample < samples; ++sample) {
    for(u8 order = 0; order < count; ++order) {
      const u8 k = sample & 1 ? (u8) (count - order - 1) : order;
      const Function function = kernels[first + k];
      const u32 started = cycles();
      for(usize iteration = 0; iteration < iterations; ++iteration)
        checksum += function(input, size);
      measurements[k][sample] = cycles() - started;
      mk61_api->service();
    }
  }
  for(u8 k = 0; k < count; ++k) {
    for(u8 i = 1; i < samples; ++i) {
      const u32 value = measurements[k][i];
      u8 j = i;
      while(j && measurements[k][j - 1] > value) {
        measurements[k][j] = measurements[k][j - 1];
        --j;
      }
      measurements[k][j] = value;
    }
    const usize at = 32 + rows * 20;
    if(at + 20 > sizeof(report) - 32) { ++failures; return; }
    write8(at, first + k);
    write8(at + 1, dataset);
    write8(at + 2, 1); // Deliberately unaligned input.
    write32(at + 4, iterations);
    write32(at + 8, measurements[k][0]);
    write32(at + 12, measurements[k][samples / 2]);
    write32(at + 16, measurements[k][samples - 1]);
    ++rows;
  }
}

static usize prepare_text(u8 dataset) {
  const usize lengths[] = {4, 16, 64, 256, 1024};
  const usize size = dataset < 5 ? lengths[dataset] : 1024;
  for(usize i = 0; i < size; ++i) {
    if(dataset < 5) input[i] = (u8) ('A' + i % 26);
    else if(dataset == 5) input[i] = i & 1 ? 0xAF : 0xD0;
    else if(dataset == 6) {
      const u8 mixed[] = {'t','e','x','t',' ','a','b','c','d','e','f','g','h',' ',0xD0,0xAF};
      input[i] = mixed[i % sizeof(mixed)];
    } else if(dataset == 7) {
      const u8 emoji[] = {0xF0,0x9F,0x98,0x80};
      input[i] = emoji[i % sizeof(emoji)];
    } else {
      const u8 invalid[] = {'a',0x80,0xED,0xA0,0x80,0xC0,0xAF,'b'};
      input[i] = invalid[i % sizeof(invalid)];
    }
  }
  return size;
}

static void prepare_frame(u8 dataset) {
  u32 random = 0x61F411U;
  for(usize i = 0; i < protocol::FRAME_BYTES; ++i) {
    previous[i] = 0;
    if(dataset == 0) input[i] = 0;
    else if(dataset == 1) input[i] = i % 192 == 95 ? 0xFF : 0;
    else if(dataset == 2) input[i] = i % 32 < 16 ? 0 : (u8) (i % 7 + 1);
    else if(dataset == 3) {
      random ^= random << 13; random ^= random >> 17; random ^= random << 5;
      input[i] = (u8) random;
    } else input[i] = i & 1 ? 0xFF : 0;
  }
}

extern "C" int main() {
  if(!mk61_app_api_compatible(mk61_api, sizeof(*mk61_api),
      MK61_APP_CAP_TIME | MK61_APP_CAP_GRAPHICS | MK61_APP_CAP_KEYBOARD))
    return MK61_APP_RUNTIME_ERROR;
  rows = failures = 0;
  checksum = 0;
  __builtin_memset(report, 0, sizeof(report));
  const u32 demcr = reg(0xE000EDFCU);
  const u32 control = reg(0xE0001000U);
  reg(0xE000EDFCU) = demcr | (1U << 24);
  reg(0xE0001000U) = control | 1U;
  const u32 before = cycles();
  for(volatile u32 i = 0; i < 32; ++i) {}
  if(cycles() == before) ++failures;
  for(u8 dataset = 0; dataset < 9; ++dataset) {
    const usize size = prepare_text(dataset);
    const usize expected = bench_strict_scalar(input, size);
    if(expected != bench_strict_ascii(input, size)) ++failures;
    if(dataset < 8) {
      if(expected != bench_valid_scalar(input, size) ||
         expected != bench_valid_dsp(input, size) ||
         expected != bench_valid_swar(input, size)) ++failures;
      run_group(0, 5, dataset, size);
    } else run_group(3, 2, dataset, size);
  }
  for(u8 dataset = 0; dataset < 5; ++dataset) {
    prepare_frame(dataset);
    (void) bench_diff_scalar(input, protocol::FRAME_BYTES);
    const protocol::DiffPlan expected = plan;
    (void) bench_diff_word(input, protocol::FRAME_BYTES);
    if(expected.count != plan.count || expected.keyframe != plan.keyframe)
      ++failures;
    for(u8 i = 0; i < expected.count; ++i)
      if(expected.runs[i].x != plan.runs[i].x ||
         expected.runs[i].page != plan.runs[i].page ||
         expected.runs[i].width != plan.runs[i].width) ++failures;
    run_group(5, 2, dataset, protocol::FRAME_BYTES);
    const usize size = bench_packbits_scalar(input, protocol::SCREEN_WIDTH);
    __builtin_memcpy(packed_reference, packed, size);
    if(size != bench_packbits_word(input, protocol::SCREEN_WIDTH)) ++failures;
    for(usize i = 0; i < size; ++i)
      if(packed_reference[i] != packed[i]) ++failures;
    run_group(7, 2, dataset, protocol::SCREEN_WIDTH);
  }
  // Restore profiler control without resetting the shared cycle counter.
  reg(0xE0001000U) = control;
  reg(0xE000EDFCU) = demcr;
  report[0] = 'B'; report[1] = 'S'; report[2] = 'C'; report[3] = '1';
  write32(4, 1);
  write32(8, rows);
  write32(12, failures);
  write32(16, (u32) (uintptr_t) bench_valid_scalar);
  write32(20, control);
#if defined(BUFFER_SCAN_BENCH_O3)
  write32(24, 3);
#else
  write32(24, 0);
#endif
  write32(28, checksum);
  if(!mk61_api->graphics_begin()) return MK61_APP_RUNTIME_ERROR;
  (void) mk61_api->graphics_present(report, sizeof(report));
  while(mk61_api->key_poll() != MK61_APP_KEY_ESC) mk61_api->delay_ms(10);
  mk61_api->graphics_end();
  return failures ? MK61_APP_RUNTIME_ERROR : MK61_APP_OK;
}

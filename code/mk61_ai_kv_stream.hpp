#ifndef MK61_AI_KV_STREAM_HPP
#define MK61_AI_KV_STREAM_HPP
#include "mk61_ai_model.hpp"
#include <algorithm>
#if defined(PICO_ON_DEVICE)
#define MK61_KV_STREAM_CODE __attribute__((section(".ai_kv_stream_extension"),noinline))
#else
#define MK61_KV_STREAM_CODE
#endif
namespace mk61ai {
// Borrow the inactive activation lookup table to gather up to 16 KV rows per
// DMA. When there is room for two buffers, start the next block while both
// cores use the current one. Wait before calling service or reusing either
// buffer. Service can itself access PSRAM.
struct KVStream {
  const Memory &memory;
  float *scratch;
  unsigned capacity;
  ComputeMetrics &metrics;
  bool enabled;
  float *alternate = nullptr;
  unsigned rows = 0;
  unsigned staged_rows = 0;

  MK61_KV_STREAM_CODE unsigned begin(float *buffer, std::uint32_t offset,
                                      unsigned width, unsigned step, unsigned remaining) {
    const unsigned take = std::min(std::min(remaining, 16U), capacity / width);
    if (take < 2) return 0;
    block_io::ReadSpan spans[16];
    for (unsigned i = 0; i < take; ++i)
      spans[i] = {offset + i * step, buffer + i * (width / sizeof(float)), width};
    if (!memory.read_begin(memory.context, spans, take)) return 0;
    ++metrics.attention_batches;
    ++metrics.attention_read_transactions;
    metrics.attention_read_bytes += take * width;
    return take;
  }

  MK61_KV_STREAM_CODE const float *read(std::uint32_t offset, unsigned width,
                                       unsigned step, unsigned remaining) {
    if (staged_rows) {
      std::swap(scratch, alternate);
      rows = staged_rows;
      staged_rows = 0;
      return scratch;
    }
    if (!width || width % sizeof(float) || width > capacity) return nullptr;
    if (enabled && memory.read_begin && memory.read_finish) {
      rows = begin(scratch, offset, width, step, remaining);
      if (rows) return memory.read_finish(memory.context) ? scratch : nullptr;
    }
    ++metrics.attention_read_transactions;
    metrics.attention_read_bytes += width;
    rows = 1;
    return memory.read(memory.context, offset, scratch, width) ? scratch : nullptr;
  }

  void prefetch(std::uint32_t offset, unsigned width, unsigned step, unsigned remaining) {
    staged_rows = begin(alternate, offset + rows * step, width, step, remaining - rows);
  }
  bool wait() { return !staged_rows || memory.read_finish(memory.context); }
};
}
#undef MK61_KV_STREAM_CODE
#endif

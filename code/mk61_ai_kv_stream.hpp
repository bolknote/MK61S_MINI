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
// The activation lookup table is dead throughout attention. Borrow at most
// 2048 bytes of it to gather up to16 adjacent positions into one PSRAM DMA.
// Every read is joined here: no DMA or borrowed pointer survives attention.
struct KVStream {
  const Memory &memory;
  float *scratch;
  unsigned capacity;
  ComputeMetrics &metrics;
  bool enabled;
  unsigned used=0,count=0,bytes=0,stride=0;
  std::uint32_t next=0;
  unsigned chunk_count() const { return count-used+1; }
  void consume_chunk(unsigned offset,unsigned rows) { used=count;next=offset+rows*stride; }
  MK61_KV_STREAM_CODE const float *read(std::uint32_t offset,unsigned width,
                                       unsigned step,unsigned remaining) {
    if(used<count && offset==next && width==bytes && step==stride) {
      const float *out=scratch+used*(width/sizeof(float));
      ++used;next+=step;return out;
    }
    used=count=0;bytes=width;stride=step;
    if(!width || width%sizeof(float) || width>capacity) return nullptr;
    const unsigned take=enabled && memory.read_begin && memory.read_finish?
        std::min(std::min(remaining,16U),capacity/width):1U;
    if(take>1) {
      block_io::ReadSpan spans[16];
      for(unsigned i=0;i<take;++i)
        spans[i]={offset+i*step,scratch+i*(width/sizeof(float)),width};
      if(memory.read_begin(memory.context,spans,take)) {
        ++metrics.attention_batches;++metrics.attention_read_transactions;
        metrics.attention_read_bytes+=take*width;
        if(!memory.read_finish(memory.context)) return nullptr;
        count=take;
      }
    }
    if(!count) {
      ++metrics.attention_read_transactions;metrics.attention_read_bytes+=width;
      if(!memory.read(memory.context,offset,scratch,width)) return nullptr;
      count=1;
    }
    used=1;next=offset+step;return scratch;
  }
};
}
#undef MK61_KV_STREAM_CODE
#endif

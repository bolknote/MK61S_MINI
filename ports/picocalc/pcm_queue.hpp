#ifndef MK61_PICOCALC_PCM_QUEUE_HPP
#define MK61_PICOCALC_PCM_QUEUE_HPP
#include <atomic>
#include <cstdint>
namespace picocalc::audio_stream {
// Core-0 foreground producer, timer-IRQ consumer. Unsigned monotonic cursors
// preserve the empty/full distinction across uint32 wrap without a lock.
struct Queue {
    static constexpr unsigned CAPACITY=1024;
    int16_t samples[CAPACITY]{};
    std::atomic<uint32_t> read{0},write{0},underruns{0};
    bool primed=false; // Consumer-owned.
    unsigned queued() const { return write.load(std::memory_order_acquire)-read.load(std::memory_order_acquire); }
    unsigned push(const int16_t* input,unsigned count) {
        const uint32_t w=write.load(std::memory_order_relaxed),r=read.load(std::memory_order_acquire);
        const unsigned free=CAPACITY-(w-r),n=count<free?count:free;
        for(unsigned i=0;i<n;++i) samples[(w+i)&(CAPACITY-1)]=input[i];
        write.store(w+n,std::memory_order_release);return n;
    }
    int16_t pop() {
        const uint32_t r=read.load(std::memory_order_relaxed),w=write.load(std::memory_order_acquire);
        if(r==w) { if(primed) underruns.store(underruns.load(std::memory_order_relaxed)+1,std::memory_order_relaxed);return 0; }
        primed=true;const int16_t value=samples[r&(CAPACITY-1)];
        read.store(r+1,std::memory_order_release);return value;
    }
};
}
#endif

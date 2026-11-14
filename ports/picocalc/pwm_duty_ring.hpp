#ifndef MK61_PICOCALC_PWM_DUTY_RING_HPP
#define MK61_PICOCALC_PWM_DUTY_RING_HPP
#include <cstdint>
namespace picocalc::audio_stream {
// Continuous single-channel DMA reads 64 duties. A 1.28 ms alarm fills the
// consumed 32-sample half while the other half is on the wire. The sample
// source is the bounded M3 duty queue, never an arbitrary APP callback.
struct DutyRing {
    static constexpr unsigned HALF=32,SIZE=64;
    static constexpr int SAMPLE_US=40;
    uint32_t filled=0;
    enum Result { EARLY,REFILLED,LATE };
    static int next_delay(Result result,uint32_t head,uint32_t previous_filled) {
        if(result==EARLY) return -SAMPLE_US;
        // A negative timer delay is relative to the last scheduled time.
        // Remove the phase error measured by the actual DMA read position.
        const unsigned late=head-previous_filled-HALF;
        return -static_cast<int>(HALF-late)*SAMPLE_US;
    }
    template<class Fill> void prime_block(uint32_t samples[SIZE],Fill fill) {
        filled=0;fill(samples,SIZE);
    }
    template<class Head,class Fill> Result refill_block(uint32_t samples[SIZE],Head head,Fill fill) {
        const uint32_t before=head(),advance=before-filled;
        if(advance<HALF)return EARLY;
        if(advance>=SIZE || (before&(HALF-1))>HALF/2)return LATE;
        const unsigned at=filled&(SIZE-1);fill(samples+at,HALF);
        if(head()-filled>=SIZE)return LATE;
        filled+=HALF;return REFILLED;
    }
    template<class Sample> void prime(uint32_t samples[SIZE],Sample sample) {
        filled=0;for(unsigned i=0;i<SIZE;++i)samples[i]=sample();
    }
    template<class Head,class Sample> Result refill(uint32_t samples[SIZE],Head head,Sample sample) {
        return refill_block(samples,head,[&sample](uint32_t* out,unsigned n){for(unsigned i=0;i<n;++i)out[i]=sample();});
    }
};
}
#endif

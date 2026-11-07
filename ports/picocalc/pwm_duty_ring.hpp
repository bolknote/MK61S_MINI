#ifndef MK61_PICOCALC_PWM_DUTY_RING_HPP
#define MK61_PICOCALC_PWM_DUTY_RING_HPP
#include <cstdint>
namespace picocalc::audio_stream {
// Continuous single-channel DMA reads64 duties. A1.28ms alarm fills the
// consumed32-sample half while the other half is on the wire. The sample
// source is the bounded M3 duty queue, never an arbitrary APP callback.
struct DutyRing {
    static constexpr unsigned HALF=32,SIZE=64;
    uint32_t filled=0;
    enum Result { EARLY,REFILLED,LATE };
    template<class Sample> void prime(uint32_t samples[SIZE],Sample sample) {
        filled=0;for(unsigned i=0;i<SIZE;++i)samples[i]=sample();
    }
    template<class Head,class Sample> Result refill(uint32_t samples[SIZE],Head head,Sample sample) {
        const uint32_t before=head(),advance=before-filled;
        if(advance<HALF)return EARLY;
        // Retain at least640us before DMA can revisit this half. A delayed
        // IRQ never writes into a half currently being read by hardware.
        if(advance>=SIZE || (before&(HALF-1))>HALF/2)return LATE;
        const unsigned at=filled&(SIZE-1);
        for(unsigned i=0;i<HALF;++i)samples[at+i]=sample();
        if(head()-filled>=SIZE)return LATE;
        filled+=HALF;return REFILLED;
    }
};
}
#endif

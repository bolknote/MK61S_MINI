#ifndef MK61_PICOCALC_KEY_CLICK_HPP
#define MK61_PICOCALC_KEY_CLICK_HPP
#include <cstdint>

namespace picocalc::audio {
// An 8 ms, low-pass noise impulse with a short attack and quadratic decay.
// Its unipolar output starts and ends at zero duty: unlike centered music
// PCM, a single click needs no abrupt 0 -> 50% -> 0 bias transitions.
class KeyClick {
public:
    static constexpr unsigned RATE = 25000, SAMPLES = 200;
    void reset() { noise_=0x61C4A37Du;filtered_=0;position_=0; }
    bool done() const { return position_==SAMPLES; }
    int16_t next() {
        if(done()) return 0;
        const unsigned at=position_++;
        noise_^=noise_<<13;noise_^=noise_>>17;noise_^=noise_<<5;
        const int32_t white=(int32_t)(noise_>>16)-32768;
        filtered_+=(white-filtered_)/4;
        int32_t sample=16384+filtered_;
        if(sample<0) sample=0;
        if(sample>32767) sample=32767;
        const unsigned remaining=SAMPLES-1-at;
        const unsigned decay=remaining*remaining*32767u/((SAMPLES-1)*(SAMPLES-1));
        const unsigned envelope=decay*(at<8?at:8)/8;
        return (int16_t)((uint32_t)sample*envelope/32768u);
    }
private:
    uint32_t noise_=0;
    int32_t filtered_=0;
    unsigned position_=SAMPLES;
};
}
#endif

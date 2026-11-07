#include "pwm_duty_ring.hpp"
#include <array>
#include <cassert>
#include <cstdio>
using picocalc::audio_stream::DutyRing;
static uint32_t duty(unsigned n){return (n&255u)|((n&255u)<<16);}
int main() {
    DutyRing ring;std::array<uint32_t,64> data{};uint32_t head=0,source=0;
    auto sample=[&]{return duty(source++);};auto position=[&]{return head;};
    ring.prime(data.data(),sample);assert(source==64);
    for(unsigned i=0;i<25000;++i) {
        assert(data[head&63]==duty(i));++head;
        if((head&31)==31) {
            const auto saved=data;const unsigned calls=source;
            assert(ring.refill(data.data(),position,sample)==DutyRing::EARLY && data==saved && calls==source);
        }
        if(!(head&31))assert(ring.refill(data.data(),position,sample)==DutyRing::REFILLED);
    }
    // Alarm latency may consume part of the peer half, but must leave at
    // least16samples/640us before writing into the consumed half.
    for(unsigned late:{49u,63u,64u,96u}) {
        source=0;ring.prime(data.data(),sample);head=late;const auto saved=data;const unsigned calls=source;
        assert(ring.refill(data.data(),position,sample)==DutyRing::LATE && data==saved && calls==source);
    }
    source=0;ring.prime(data.data(),sample);head=48;
    assert(ring.refill(data.data(),position,sample)==DutyRing::REFILLED);
    // A preempted refill that exhausted its peer half is diagnosed too.
    ring.prime(data.data(),sample);head=32;
    assert(ring.refill(data.data(),position,[&]{head+=2;return sample();})==DutyRing::LATE && !ring.filled);
    puts("Single-channel PWM ring:25000 exact ordered duties, early alarm,640us refill guard, missed half and refill overrun detection PASS");
}

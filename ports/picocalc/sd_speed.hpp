#ifndef MK61_PICOCALC_SD_SPEED_HPP
#define MK61_PICOCALC_SD_SPEED_HPP
#include <cstdint>
#include <cstring>
namespace picocalc::sd {
constexpr uint32_t SAFE_HZ=12500000,FAST_HZ=20833333;
inline uint32_t transfer_rate(uint8_t csd) {
    constexpr uint8_t multiplier[]={0,10,12,13,15,20,25,30,35,40,45,50,55,60,70,80};
    const unsigned unit=csd&7,value=multiplier[(csd>>3)&15];
    if((csd&0x80) || unit>3 || !value) return SAFE_HZ;
    uint32_t hz=100000;for(unsigned i=0;i<unit;++i) hz*=10;
    return hz/10*value;
}
struct SpeedQualification { bool ok=false,fallback=false;uint32_t hz=0,safe_hz=0,advertised_hz=0; };
// No probe writes. Compare actual sector bytes at both speeds as well as
// the card's wire CRC; a failed fast trial is accepted only after safe reread.
template<class Bus>
SpeedQualification qualify_speed(Bus& bus,uint8_t csd,uint32_t last,bool fast=true) {
    SpeedQualification r;r.advertised_hz=transfer_rate(csd);
    const auto safe=r.advertised_hz<SAFE_HZ?r.advertised_hz:SAFE_HZ;
    const auto target=r.advertised_hz<FAST_HZ?r.advertised_hz:FAST_HZ;
    alignas(4) uint8_t baseline[512],actual[512];
    r.safe_hz=bus.rate(safe);
    const uint32_t sectors[]={0U,last?1U:0U,last};
    for(uint32_t sector:sectors) {
        bus.rate(safe);
        if(!bus.read(sector,baseline)) return r;
        r.hz=bus.rate(fast?target:safe);
        if(r.hz<=r.safe_hz) { r.ok=true;return r; }
        if(!bus.read(sector,actual) || std::memcmp(baseline,actual,sizeof(actual))) {
            r.fallback=true;r.hz=bus.rate(safe);
            r.ok=bus.read(sector,actual) && !std::memcmp(baseline,actual,sizeof(actual));return r;
        }
    }
    r.ok=true;return r;
}
// Poll once before sleeping: idle cards have no added latency. Busy flash
// programming waits yield the CPU in bounded slices, without recursively
// reentering TinyUSB/FatFs while a storage callback owns the card.
template<class Bus> bool wait_ready(Bus& bus,uint64_t timeout_us) {
    const auto deadline=bus.now()+timeout_us;
    do {
        if(bus.byte()==0xFF) return true;
        const auto now=bus.now();if(now>=deadline) return false;
        bus.wait(deadline-now<50?deadline:now+50);
    } while(true);
}
}
#endif

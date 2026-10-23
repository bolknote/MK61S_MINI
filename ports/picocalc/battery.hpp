#ifndef MK61_PICOCALC_BATTERY_HPP
#define MK61_PICOCALC_BATTERY_HPP
#include <cstdint>
namespace picocalc {
struct BatteryStatus {
    int16_t percent=-1;
    bool bios_flag7=false,available=false;
    void clear_reading() { percent=-1;bios_flag7=false; }
    bool decode(uint8_t reg,uint8_t value) {
        if(reg!=0x0B || (value&0x7F)>100) { clear_reading();return false; }
        percent=value&0x7F;bios_flag7=(value&0x80)!=0;available=true;return true;
    }
};
// Native pixels, no scaled font. The LCD title and clock reserve this space.
template<class Pixel> void battery_icon(const BatteryStatus& state,Pixel pixel) {
    if(!state.available) return;
    constexpr unsigned left=290,top=11;
    for(unsigned x=0;x<20;++x) { pixel(left+x,top);pixel(left+x,top+11); }
    for(unsigned y=1;y<11;++y) { pixel(left,top+y);pixel(left+19,top+y); }
    for(unsigned y=4;y<8;++y) for(unsigned x=20;x<22;++x) pixel(left+x,top+y);
    if(state.percent<0) {
        for(unsigned x=7;x<13;++x) pixel(left+x,top+5);
    } else {
        const unsigned fill=(unsigned)state.percent*16/100;
        for(unsigned y=2;y<10;++y) for(unsigned x=0;x<fill;++x) pixel(left+2+x,top+y);
    }

}
}
#endif

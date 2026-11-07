#ifndef MK61_PICOCALC_BATTERY_HPP
#define MK61_PICOCALC_BATTERY_HPP
#include <cstdint>
#include "bios/power_status.h"
namespace picocalc {
struct BatteryStatus {
    int16_t percent=-1;
    bool bios_flag7=false,available=false;
    uint8_t power_status=0;
    void clear_reading() { percent=-1;bios_flag7=false; }
    bool power_supported() const { return (power_status&BIOS_POWER_TAG_MASK)==BIOS_POWER_TAG; }
    bool power_valid() const { return power_supported() && (power_status&BIOS_POWER_VALID); }
    bool battery_present() const { return power_valid() && (power_status&BIOS_POWER_BATTERY); }
    bool external_power() const { return power_valid() && (power_status&BIOS_POWER_EXTERNAL); }
    bool charging() const { return power_valid() && (power_status&BIOS_POWER_CHARGING); }
    bool charge_complete() const { return power_valid() && (power_status&BIOS_POWER_COMPLETE); }
    void clear_power() { power_status=power_supported()?BIOS_POWER_TAG:0; }
    bool decode_power(uint8_t reg,uint8_t value) {
        if(reg!=BIOS_POWER_REG || !bios_power_valid_encoding(value)) { clear_power();return false; }
        power_status=value;available=true;return true;
    }
    const char* power_name() const {
        if(!power_valid()) return "UNKNOWN";
        if(charging()) return "CHARGING";
        if(charge_complete()) return "COMPLETE";
        if(external_power()) return "EXTERNAL";
        return battery_present()?"BATTERY":"NO_BATTERY";
    }
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
    if(state.external_power()) {
        // Plug: independent of charging/DONE; stays visible at full charge.
        for(unsigned y=1;y<4;++y) { pixel(282,top+y);pixel(285,top+y); }
        for(unsigned x=280;x<288;++x) pixel(x,top+4);
        for(unsigned y=5;y<8;++y) { pixel(281,top+y);pixel(286,top+y); }
        for(unsigned x=282;x<286;++x) pixel(x,top+8);
        pixel(283,top+9);pixel(283,top+10);
    }
    if(state.percent<0 && !state.charging() && !state.charge_complete()) {
        for(unsigned x=7;x<13;++x) pixel(left+x,top+5);
    } else {
        const unsigned fill=state.percent<=0?0:state.percent>=100?16:(unsigned)state.percent*16/100;
        constexpr uint8_t bolt[8]={0x08,0x18,0x30,0x7E,0x0C,0x18,0x30,0x20};
        constexpr uint8_t check[8]={0,0,0x02,0x06,0x4C,0x78,0x30,0};
        for(unsigned y=0;y<8;++y) for(unsigned x=0;x<16;++x) {
            const bool mark=x>=4 && x<11 &&
                ((state.charging()?bolt[y]:state.charge_complete()?check[y]:0)&(0x40>>(x-4)));
            if((x<fill)!=mark) pixel(left+2+x,top+2+y);
        }
    }

}
}
#endif

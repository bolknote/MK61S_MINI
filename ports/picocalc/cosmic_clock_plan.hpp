#ifndef MK61_COSMIC_CLOCK_PLAN_HPP
#define MK61_COSMIC_CLOCK_PLAN_HPP
#include <cstdint>
namespace picocalc::cosmic_clock {
constexpr uint32_t USB_HZ=48000000,PERI_HZ=48000000;
constexpr uint32_t PIO_HZ=100000000,PWM_HZ=100000000,LEASE_MS=105000;
struct Plan { uint32_t mhz,vco_hz,postdiv1,postdiv2,pio_div256,pwm_div16; };
constexpr Plan step(uint32_t mhz) {return {mhz,mhz*6000000,6,1,(mhz*64+24)/25,(mhz*4+24)/25};}
constexpr Plan plans[]={{125,1500000000,6,2,320,20},step(130),step(140),step(150),step(160),step(170),
    step(180),step(190),step(200),step(210),step(220),step(230),step(240),step(250)};
constexpr const Plan* find(uint32_t mhz) {
    for(const auto& p:plans)if(p.mhz==mhz)return &p;
    return nullptr;
}
constexpr bool valid(const Plan& p) {
    return p.vco_hz%12000000==0 && p.postdiv1>=p.postdiv2 && p.postdiv1<=7 && p.postdiv2>=1 &&
        uint64_t(p.mhz)*1000000*p.postdiv1*p.postdiv2==p.vco_hz &&
        p.vco_hz>=750000000 && p.vco_hz<=1600000000 &&
        uint64_t(p.mhz)*1000000*256<=uint64_t(PIO_HZ)*p.pio_div256 &&
        uint64_t(p.mhz)*1000000*16<=uint64_t(PWM_HZ)*p.pwm_div16 &&
        uint64_t(p.mhz)*1000000*10>=uint64_t(USB_HZ)*11;
}
constexpr bool valid_plans(){for(const auto& p:plans)if(!valid(p))return false;return true;}
static_assert(valid_plans(),"Invalid clock profile");
// Every drive operation pulls a line LOW. Releasing it uses the pull-up.
template<class Pins> bool clear_i2c(Pins& p) {
    p.init();p.release_sda();p.release_scl();
    const auto high=[&] {for(unsigned n=0;n<20;++n){if(p.scl_high())return true;p.delay();}return false;};
    if(!high())return false;
    for(unsigned n=0;n<9;++n){p.low_scl();p.delay();p.release_scl();if(!high())return false;p.delay();}
    p.low_scl();p.low_sda();p.delay();p.release_scl();if(!high())return false;
    p.delay();p.release_sda();p.delay();return p.sda_high() && p.scl_high();
}
template<class Reset> [[noreturn]] void planned_reboot(Reset& r) {
    r.stop_click();r.drain();r.prepare_psram();r.reply();r.drain();r.arm_reset();
    // Returning to main would feed the delayed watchdog every10ms forever.
    // It would also allow a new keyboard transaction before the reset.
    for(;;)r.spin();
}
// Shared by the firmware and HOST fault-injection tests.
template<class Backend> bool transition(Backend& io,const Plan& before,const Plan& after) {
    if(!io.idle())return false;
    io.stop_click();io.drain();
    if(after.mhz>before.mhz && !io.pio(after.pio_div256))return false;
    io.disconnect();
    if(!io.deinit_usb()){io.reboot();return false;}
    io.hold_usb_reset();io.detach_delay();
    if(!io.change_clock(after)){io.reboot();return false;}
    if(after.mhz<=before.mhz && !io.pio(after.pio_div256)){io.reboot();return false;}
    if(!io.healthy(after.mhz)){io.reboot();return false;}
    io.release_usb_reset();
    if(!io.init_usb()){io.reboot();return false;}
    io.connect();return true;
}
struct Lease {
    bool active=false;
    uint32_t mhz=125;
    uint64_t until=0;
    bool arm(uint32_t target,uint64_t now) {
        if(active || !find(target) || now>UINT64_MAX-uint64_t(LEASE_MS)*1000)return false;
        active=true;mhz=target;until=now+uint64_t(LEASE_MS)*1000;return true;
    }
    bool expired(uint64_t now)const {return active && now>=until;}
    void clear(){active=false;mhz=125;until=0;}
};
struct AudioClock {
    bool active=false;
    template<class Backend> bool begin(Backend& io) {
        if(active)return true;
        if(!io.switch_to(200))return false;
        active=true;return true;
    }
    template<class Backend> void end(Backend& io) {
        if(!active)return;
        active=false;
        if(!io.switch_to(125))io.reboot();
    }
};
}
#endif

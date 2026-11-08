#include "compute_clock.hpp"
#include "cosmic_clock.hpp"
#include "cosmic_clock_plan.hpp"
#include "psram.hpp"
#include "script.hpp"
#include "audio_stream.hpp"
#include "hardware/clocks.h"
#include "hardware/structs/clocks.h"
#include "hardware/sync.h"
#include "hardware/vreg.h"
#include "pico/flash.h"
#include "pico/stdlib.h"

namespace {
bool restore_profile(uint8_t profile,uint32_t target) {
    const uint32_t high=compute_clock::high_mhz(compute_clock::Platform::PICO,profile)*1000000U;
    if(!profile || (target!=high && target!=high/2))return false;
    const auto* plan=picocalc::cosmic_clock::find(high/1000000);
    if(!plan)return false;
    // Boot/battery-wake only, before USB is enabled. Run-time requests never
    // reprogram PLL_SYS or pass through the SDK's temporary48MHz SYS clock.
    vreg_set_voltage(VREG_VOLTAGE_1_20);busy_wait_us_32(1000);
    set_sys_clock_pll(plan->vco_hz,plan->postdiv1,plan->postdiv2);
    clocks_hw->clk[clk_sys].div=(target==high?1U:2U)<<8;
    clock_set_reported_hz(clk_sys,target);
    return true;
}
struct Change {uint32_t hz,divider;bool changed=false;};
void write_divider(void* raw) {
    const auto& change=*(Change*)raw;
    clocks_hw->clk[clk_sys].div=change.divider<<8;
    __dsb();__isb();clock_set_reported_hz(clk_sys,change.hz);
}
void transition(void* raw) {
    auto& change=*(Change*)raw;
    const auto* plan=picocalc::cosmic_clock::find(change.hz/1000000);
    if(plan)change.changed=picocalc::psram::compute_clock_transition(plan->pio_div256,write_divider,&change);
}
}
namespace compute_clock {
Platform platform(){return Platform::PICO;}
namespace backend {
uint32_t hz(){return clock_get_hz(clk_sys);}
uint32_t now_ms(){return uint32_t(time_us_64()/1000);}
bool configure(uint8_t profile) {
    return profile?restore_profile(profile,low_mhz(Platform::PICO,profile)*1000000U):hz()==125000000;
}
bool set_fast(bool fast) {
    if(get_core_num()!=0)return false;
    const auto tone=picocalc::script::tone_status();
    if(tone.wrap || tone.software || picocalc::audio_stream::key_click_statistics().active)return false;
    const uint32_t high=high_mhz(Platform::PICO,active_profile())*1000000U;
    Change change{high/(fast?1U:2U),fast?1U:2U};
    return flash_safe_execute(transition,&change,2)==PICO_OK && change.changed;
}
}
}
namespace picocalc::cosmic_clock {
bool restore_compute_clock(uint32_t expected_hz) {
    return restore_profile(compute_clock::active_profile(),expected_hz);
}
}

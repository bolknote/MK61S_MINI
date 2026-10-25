#include "picocalc_power_sdk.hpp"
#include "power.hpp"
#include <cstdio>
#include <stdexcept>
#undef assert
#define assert(condition) do { if(!(condition)) throw std::runtime_error(#condition); } while(false)
namespace picocalc::io_worker {
void drain() { ++power_test::drains; }
bool input_ready() { return power_test::input; }
}
namespace picocalc::clock { bool alarm_pending() { return power_test::rtc_alarm; } }
static void cycle(bool usb,bool initial_irq=true) {
    using namespace power_test;
    reset(125000000,usb);usb_irq=initial_irq;
    const auto before=*clocks_hw;const auto scr=scb_hw->scr;
    picocalc::SleepClocks clocks;clocks.init();
    const auto rtc=clocks_hw->clk[clk_rtc];
    assert((rtc.ctrl>>5)==CLOCKS_CLK_RTC_CTRL_AUXSRC_VALUE_XOSC_CLKSRC && rtc.div==65536);
    for(unsigned repeat=0;repeat<3;++repeat) {
        const unsigned entries=clocks.entries();clocks.enter();
        assert(!e16_violations && !stop_order_errors);
        const uint32_t expected=usb?125000000:XOSC_HZ;
        assert(clocks.active() && clocks.usb_available()==usb && clocks.entries()==entries+1);
        assert(clock_get_hz(clk_sys)==expected && clock_get_hz(clk_peri)==expected);
        assert(clock_get_hz(clk_rtc)==46875 && !clock_get_hz(clk_adc));
        assert(clocks.pll_mask()==(usb?3U:0U) && (scb_hw->scr&M0PLUS_SCR_SLEEPDEEP_BITS));
        if(usb) assert(!sys_helpers && !peri_helpers && !sys_restarts && connected && usb_irq==initial_irq);
        else assert(!connected && !usb_irq && !clock_get_hz(clk_usb));
        const unsigned drains_before=drains;clocks.enter();
        assert(drains==drains_before && clocks.entries()==entries+1 && !clocks.refresh());
        clocks.leave();
        assert(!clocks.active() && clock_get_hz(clk_sys)==125000000 && clock_get_hz(clk_peri)==125000000);
        assert(clock_get_hz(clk_rtc)==46875 && clock_get_hz(clk_adc)==USB_CLK_HZ && clock_get_hz(clk_usb)==USB_CLK_HZ);
        assert(clocks.pll_mask()==3 && connected && usb_irq==initial_irq);
        assert(clocks_hw->clk[clk_sys].div==before.clk[clk_sys].div);
        assert(clocks_hw->clk[clk_adc].ctrl==before.clk[clk_adc].ctrl && clocks_hw->clk[clk_adc].div==before.clk[clk_adc].div);
        assert(clocks_hw->clk[clk_usb].ctrl==before.clk[clk_usb].ctrl && clocks_hw->clk[clk_usb].div==before.clk[clk_usb].div);
        assert(clocks_hw->clk[clk_rtc].ctrl==rtc.ctrl && clocks_hw->clk[clk_rtc].div==rtc.div);
        assert(clocks_hw->sleep_en0==before.sleep_en0 && clocks_hw->sleep_en1==before.sleep_en1 && scb_hw->scr==scr);
        assert(!e16_violations && !unsafe_pll_stops && !stop_order_errors);
        const unsigned after=drains;clocks.leave();assert(drains==after);
    }
    assert(drains==6 && uart_clocks.size()==6 && clocks.battery_entries()==(usb?0U:3U));
    for(unsigned i=0;i<uart_clocks.size();++i)
        assert(uart_clocks[i]==(usb || (i&1)?125000000U:XOSC_HZ));
}
static int run_tests() {
    cycle(true);cycle(true,false);cycle(false);cycle(false,false);
    using namespace power_test;
    reset();picocalc::SleepClocks clocks;clocks.init();clocks.enter();
    for(unsigned repeat=0;repeat<4;++repeat) {
        vbus=false;assert(clocks.refresh());
        assert(clocks.active() && !clocks.usb_available() && clocks.pll_mask()==0);
        assert(clock_get_hz(clk_sys)==XOSC_HZ && !usb_irq && !connected);
        vbus=true;assert(clocks.refresh());
        assert(clocks.active() && clocks.usb_available() && clocks.pll_mask()==3);
        assert(clock_get_hz(clk_sys)==125000000 && usb_irq && connected);
        assert(!e16_violations && !unsafe_pll_stops && !stop_order_errors);
    }
    clocks.leave();assert(clock_get_hz(clk_sys)==125000000 && clocks.pll_mask()==3);
    assert(!e16_violations && !unsafe_pll_stops && !stop_order_errors);
    std::puts("PicoCalc actual SleepClocks: USB retains125MHz without SDK source transients; battery stop-before12MHz, both VBUS transitions, RTC/masks/UART/drain restoration PASS");
    return 0;
}
int main() {
    try { return run_tests(); }
    catch(const std::exception& error) { std::fprintf(stderr,"FAIL: %s\n",error.what());return 1; }
}

#ifndef MK61_TEST_PICOCALC_POWER_SDK_HPP
#define MK61_TEST_PICOCALC_POWER_SDK_HPP
#include <array>
#include <cassert>
#include <cstdint>
#include <vector>
// Host clock/register boundary for actual power.cpp. Model SDK clock helper
// transients through REF/PLL_USB so the test cannot hide RP2040-E16.
#define LIB_PICO_STDIO_UART 1
#define PICO_DEFAULT_UART_BAUD_RATE 115200
constexpr unsigned PICO_VBUS_PIN=24,GPIO_IN=0,USBCTRL_IRQ=5;
constexpr uint32_t XOSC_HZ=12000000,USB_CLK_HZ=48000000,PLL_PWR_PD_BITS=1;
constexpr unsigned PLL_USB_REFDIV=1,PLL_USB_VCO_FREQ_HZ=480000000,PLL_USB_POSTDIV1=5,PLL_USB_POSTDIV2=2;
constexpr unsigned CLOCKS_CLK_SYS_CTRL_SRC_VALUE_CLK_REF=0,CLOCKS_CLK_SYS_CTRL_SRC_VALUE_CLKSRC_CLK_SYS_AUX=1;
constexpr unsigned CLOCKS_CLK_SYS_CTRL_AUXSRC_VALUE_CLKSRC_PLL_SYS=0,CLOCKS_CLK_SYS_CTRL_AUXSRC_VALUE_CLKSRC_PLL_USB=1;
constexpr unsigned CLOCKS_CLK_PERI_CTRL_AUXSRC_VALUE_CLK_SYS=0,CLOCKS_CLK_RTC_CTRL_AUXSRC_VALUE_XOSC_CLKSRC=3;
constexpr uint32_t CLOCKS_SLEEP_EN0_CLK_RTC_RTC_BITS=1U<<21;
constexpr uint32_t CLOCKS_SLEEP_EN1_CLK_SYS_TIMER_BITS=1U<<10,CLOCKS_SLEEP_EN1_CLK_SYS_WATCHDOG_BITS=1U<<11;
constexpr uint32_t CLOCKS_SLEEP_EN1_CLK_SYS_USBCTRL_BITS=1U<<4,CLOCKS_SLEEP_EN1_CLK_USB_USBCTRL_BITS=1U<<5;
constexpr uint32_t M0PLUS_SCR_SLEEPDEEP_BITS=4;
enum clock_handle_t { clk_sys,clk_peri,clk_adc,clk_usb,clk_rtc,clk_ref,clock_count };
struct clock_hw_t { uint32_t ctrl=0,div=256; };
struct clocks_hw_t { std::array<clock_hw_t,clock_count> clk{};uint32_t sleep_en0=0,sleep_en1=0; };
struct pll_hw_t { uint32_t pwr=0; };
struct scb_hw_t { uint32_t scr=0; };
inline clocks_hw_t power_test_clocks;
inline pll_hw_t power_test_pll_sys,power_test_pll_usb;
inline scb_hw_t power_test_scb;
inline auto* clocks_hw=&power_test_clocks;
inline auto* pll_sys=&power_test_pll_sys;
inline auto* pll_usb=&power_test_pll_usb;
inline auto* scb_hw=&power_test_scb;
namespace power_test {
inline std::array<uint32_t,clock_count> hz{};
inline bool vbus=true,connected=true,usb_irq=true,usb_event=false,uart_rx=false,input=false,rtc_alarm=false;
inline uint64_t now=1;
inline unsigned e16_violations=0,unsafe_pll_stops=0,drains=0,sys_helpers=0,peri_helpers=0,sys_restarts=0,waits=0,stop_order_errors=0;
inline std::vector<uint32_t> usb_sys_rates,uart_clocks;
inline void observe() {
    if(vbus && connected && hz[clk_usb]) {
        usb_sys_rates.push_back(hz[clk_sys]);
        if(uint64_t(hz[clk_sys])*10<uint64_t(hz[clk_usb])*11) ++e16_violations;
    }
}
inline void reset(uint32_t run=125000000,bool usb=true) {
    power_test_clocks={};power_test_pll_sys={};power_test_pll_usb={};power_test_scb={};
    hz={run,run,USB_CLK_HZ,USB_CLK_HZ,46875,XOSC_HZ};
    clocks_hw->sleep_en0=0x79BDAF41;clocks_hw->sleep_en1=0x5A071C32;scb_hw->scr=0x12;
    clocks_hw->clk[clk_adc]={0x801,777};clocks_hw->clk[clk_usb]={0x802,999};
    vbus=usb;connected=true;usb_irq=true;usb_event=uart_rx=input=rtc_alarm=false;
    e16_violations=unsafe_pll_stops=drains=sys_helpers=peri_helpers=sys_restarts=waits=stop_order_errors=0;
    now=1;usb_sys_rates.clear();uart_clocks.clear();
}
}
inline uint32_t clock_get_hz(clock_handle_t clock) { return power_test::hz[clock]; }
inline void clock_set_reported_hz(clock_handle_t clock,uint32_t hz) {
    power_test::hz[clock]=hz;power_test::observe();
}
inline bool clock_configure(clock_handle_t clock,uint32_t src,uint32_t aux,uint32_t source_hz,uint32_t hz) {
    assert(hz && source_hz>=hz);
    if(clock==clk_peri) ++power_test::peri_helpers;
    if(clock==clk_sys) {
        if(uint64_t(hz)*10<uint64_t(USB_CLK_HZ)*11 &&
           (power_test::hz[clk_usb] || power_test::connected || power_test::usb_irq))
            ++power_test::stop_order_errors;
        ++power_test::sys_helpers;
        // SDK2.2 clock_configure_internal leaves AUX via REF first.
        if(src==CLOCKS_CLK_SYS_CTRL_SRC_VALUE_CLKSRC_CLK_SYS_AUX) {
            power_test::hz[clk_sys]=XOSC_HZ;power_test::observe();
            assert(!((aux==0?pll_sys:pll_usb)->pwr&PLL_PWR_PD_BITS));
        }
    }
    clocks_hw->clk[clock].ctrl=(aux<<5)|src;
    clocks_hw->clk[clock].div=uint32_t((uint64_t(source_hz)<<8)/hz);
    power_test::hz[clock]=hz;power_test::observe();return true;
}
inline void clock_configure_undivided(clock_handle_t c,uint32_t s,uint32_t a,uint32_t hz) { (void)clock_configure(c,s,a,hz,hz); }
inline void clock_stop(clock_handle_t c) { power_test::hz[c]=0;clocks_hw->clk[c].ctrl=0; }
inline void pll_deinit(pll_hw_t* pll) {
    if(pll==pll_sys && power_test::hz[clk_sys]>XOSC_HZ) ++power_test::unsafe_pll_stops;
    if(pll==pll_usb && power_test::vbus && power_test::connected) ++power_test::unsafe_pll_stops;
    if(pll==pll_usb && power_test::hz[clk_adc]) ++power_test::unsafe_pll_stops;
    pll->pwr|=PLL_PWR_PD_BITS;
}
inline void pll_init(pll_hw_t* pll,unsigned,unsigned,unsigned,unsigned) { pll->pwr&=~PLL_PWR_PD_BITS; }
inline bool set_sys_clock_hz(uint32_t hz,bool) {
    ++power_test::sys_restarts;clock_configure_undivided(clk_sys,1,1,USB_CLK_HZ);
    pll_init(pll_sys,1,0,0,0);clock_configure_undivided(clk_sys,1,0,hz);return true;
}
inline bool gpio_get(unsigned pin) { assert(pin==PICO_VBUS_PIN);return power_test::vbus; }
inline void gpio_init(unsigned) {}
inline void gpio_set_dir(unsigned,unsigned) {}
inline bool irq_is_enabled(unsigned) { return power_test::usb_irq; }
inline void irq_set_enabled(unsigned,bool on) { power_test::usb_irq=on; }
inline void tud_disconnect() { power_test::connected=false; }
inline void tud_connect() { power_test::connected=true;power_test::observe(); }
inline bool tud_task_event_ready() { return power_test::usb_event; }
inline unsigned tud_cdc_available() { return power_test::usb_event; }
inline int power_test_uart;
inline auto* uart_default=&power_test_uart;
inline bool uart_is_readable(int*) { return power_test::uart_rx; }
inline unsigned uart_set_baudrate(int*,unsigned baud) { power_test::uart_clocks.push_back(power_test::hz[clk_peri]);return baud; }
using absolute_time_t=uint64_t;
inline uint64_t time_us_64() { return power_test::now; }
inline absolute_time_t from_us_since_boot(uint64_t v) { return v; }
inline int hardware_alarm_claim_unused(bool) { return 1; }
inline void hardware_alarm_set_callback(unsigned,void(*)(unsigned)) {}
inline bool hardware_alarm_set_target(unsigned,absolute_time_t) { return false; }
inline void hardware_alarm_cancel(unsigned) {}
inline void power_test_sev() {}
inline void power_test_wfe() { ++power_test::waits;++power_test::now; }
#define __sev power_test_sev
#define __wfe power_test_wfe
inline void best_effort_wfe_or_timeout(absolute_time_t t) { ++power_test::waits;power_test::now=t; }
#endif

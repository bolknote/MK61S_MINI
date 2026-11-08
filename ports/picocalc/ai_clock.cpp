#include "ai_clock.hpp"
#include "compute_clock.hpp"
#if defined(PICO_ON_DEVICE)
#include "pico/stdlib.h"
#include "hardware/clocks.h"
#endif
#ifndef MK61_PICOCALC_AI_OVERCLOCK
#define MK61_PICOCALC_AI_OVERCLOCK 0
#endif
#if defined(PICO_ON_DEVICE) && MK61_PICOCALC_AI_OVERCLOCK
#include "io_worker.hpp"
#include "psram.hpp"
#include "audio_stream.hpp"
#include "cosmic_clock_plan.hpp"
#include "ai_clock_transition.hpp"
#include "ai_flash_clock.hpp"
#include "hardware/i2c.h"
#include "hardware/pll.h"
#include "hardware/resets.h"
#include "hardware/structs/ssi.h"
#include "hardware/structs/vreg_and_chip_reset.h"
#include "hardware/vreg.h"
#include "pico/flash.h"
#include "tusb.h"
#endif
namespace picocalc::ai_clock {
#if !defined(PICO_ON_DEVICE)
namespace { TestStatistics simulated; }
void test_clock(u32 initial_hz) { simulated={0,0,initial_hz}; }
TestStatistics test_statistics() { return simulated; }
#endif
u32 hz() {
#if defined(PICO_ON_DEVICE)
  return clock_get_hz(clk_sys);
#else
  return simulated.hz;
#endif
}
#if defined(PICO_ON_DEVICE) && MK61_PICOCALC_AI_OVERCLOCK
namespace {
constexpr u32 MAGIC=0xA1C10607;
struct Retained { u32 magic,stage,target; };
Retained trace __attribute__((section(".uninitialized_data.picocalc_ai_clock")));
u32 measured_khz=0;
void mark(u32 stage,u32 target) { trace.magic=0;trace.stage=stage;trace.target=target;__dmb();trace.magic=MAGIC;__dmb(); }
u32 measure() {
  const u64 end=time_us_64()+50000;
  while(clocks_hw->fc0.status&CLOCKS_FC0_STATUS_RUNNING_BITS) if(time_us_64()>=end)return 0;
  clocks_hw->fc0.ref_khz=clock_get_hz(clk_ref)/1000;
  clocks_hw->fc0.interval=10;clocks_hw->fc0.min_khz=0;clocks_hw->fc0.max_khz=UINT32_MAX;
  clocks_hw->fc0.src=CLOCKS_FC0_SRC_VALUE_CLK_SYS;
  while(!(clocks_hw->fc0.status&CLOCKS_FC0_STATUS_DONE_BITS)) if(time_us_64()>=end)return 0;
  return clocks_hw->fc0.result>>CLOCKS_FC0_RESULT_KHZ_LSB;
}
void __no_inline_not_in_flash_func(write_clock)(void* raw) {
  const auto& plan=*static_cast<const cosmic_clock::Plan*>(raw);
  struct Bus {
    __attribute__((always_inline)) void divider(unsigned div) {
      while(ssi_hw->sr&SSI_SR_BUSY_BITS)__asm volatile("nop");
      ssi_hw->ssienr=0;ssi_hw->baudr=div;ssi_hw->ssienr=1;
    }
    __attribute__((always_inline)) void pll(const cosmic_clock::Plan& p) {
      set_sys_clock_pll(p.vco_hz,p.postdiv1,p.postdiv2);
    }
  } bus;
  apply_pll(bus,plan);
  // PERI already comes from PLL_USB48. Do not reconfigure it after changing
  // SYS: the old300MHz failure was in that redundant post-PLL operation.
}
bool stock_voltage() {
  return (vreg_and_chip_reset_hw->vreg&VREG_AND_CHIP_RESET_VREG_VSEL_BITS)==
      (u32(VREG_VOLTAGE_1_10)<<VREG_AND_CHIP_RESET_VREG_VSEL_LSB);
}
struct Hardware {
  bool allowed(){return stock_voltage() && !audio_stream::active() && ssi_hw->baudr==flash_divider(hz()/1000000) &&
      clock_get_hz(clk_peri)==48000000 && clock_get_hz(clk_usb)==48000000;}
  void prepare(){audio_stream::stop_key_click();io_worker::drain();stdio_flush();}
  void mark(u32 stage,u32 target){ai_clock::mark(stage,target);}
  bool pio(u32 div){return psram::diagnostic_clock_divider(div);}
  void disconnect(){if(tud_inited())tud_disconnect();}
  bool deinit(){return tud_deinit(0);}
  void reset(){reset_block(RESETS_RESET_USBCTRL_BITS);}
  void detach_delay(){sleep_ms(200);}
  bool pll(const cosmic_clock::Plan& plan){ai_clock::mark(5,plan.mhz);const bool ok=flash_safe_execute(write_clock,const_cast<cosmic_clock::Plan*>(&plan),50)==PICO_OK;if(ok)ai_clock::mark(6,plan.mhz);return ok;}
  void retune_i2c(){i2c_set_baudrate(i2c1,10000);}
  bool verify(const cosmic_clock::Plan& plan){
    measured_khz=measure();const u32 sys=plan.mhz*1000000;
    return hz()==sys && measured_khz+100>=sys/1000 && measured_khz<=sys/1000+100 &&
        clock_get_hz(clk_peri)==48000000 && clock_get_hz(clk_usb)==48000000 && stock_voltage() &&
        ssi_hw->baudr==flash_divider(plan.mhz) && psram::diagnostic_clock_divider256()==plan.pio_div256;
  }
  void unreset(){unreset_block_wait(RESETS_RESET_USBCTRL_BITS);}
  bool init(){const tusb_rhport_init_t init{TUSB_ROLE_DEVICE,TUSB_SPEED_FULL};return tusb_init(0,&init);}
  void connect(){tud_connect();}
};
bool transition(u32 sys) {
  const auto* before=cosmic_clock::find(hz()/1000000);
  const auto* after=cosmic_clock::find(sys/1000000);
  if(!before || !after)return false;
  Hardware hardware;return change(hardware,*before,*after);
}
}
#endif
bool begin(unsigned mhz,State& s) {
  const bool allowed=mhz==125 || mhz==270;
  if(s.changed || s.restore_attempted || !allowed)return false;
  s.sys=hz();
#if !defined(PICO_ON_DEVICE)
  if(simulated.hz && mhz==270 && simulated.hz==125000000) {
    ++simulated.begins;simulated.hz=270000000;s.changed=true;return true;
  }
#endif
  if(compute_clock::active_profile())return mhz==125;
  if(mhz==125 && (!s.sys || s.sys==125000000)) return true;
#if defined(PICO_ON_DEVICE) && MK61_PICOCALC_AI_OVERCLOCK
  if(s.sys!=125000000)return false;
  const auto* plan=cosmic_clock::find(mhz);unsigned vco=0,post1=0,post2=0;
  if(!plan || !check_sys_clock_khz(mhz*1000,&vco,&post1,&post2) ||
     vco!=plan->vco_hz || post1!=plan->postdiv1 || post2!=plan->postdiv2)return false;
  s.peri=clock_get_hz(clk_peri);s.changed=true;
  return transition(mhz*1000000U);
#else
  return false;
#endif
}
bool restore(State& s) {
  if(!s.changed)return true;
  if(s.restore_attempted)return false;
  s.restore_attempted=true;
#if !defined(PICO_ON_DEVICE)
  if(simulated.hz) { ++simulated.restores;simulated.hz=s.sys;s.changed=false;return true; }
#endif
#if defined(PICO_ON_DEVICE) && MK61_PICOCALC_AI_OVERCLOCK
  const bool ok=transition(s.sys);if(ok)s.changed=false;return ok;
#else
  return false;
#endif
}
}

#ifndef MK61_PICOCALC_AI_CLOCK_HPP
#define MK61_PICOCALC_AI_CLOCK_HPP
#include "rust_types.h"
namespace picocalc::ai_clock {
// Qualified AI runtime clock; ordinary chat and diagnostics share this path.
// USB disconnects deliberately while SYS traverses PLL_USB at 48 MHz; E16
// forbids leaving the 48 MHz USB controller clock active during that interval.
struct State {
  u32 sys=0,peri=0,peri_ctrl=0,peri_div=0,spi0_hz=0,spi1_hz=0;
  bool changed=false,restore_attempted=false;
};
u32 hz();
bool begin(unsigned mhz,State& state,bool quiet_usb=false);
bool restore(State& state);
#if !defined(PICO_ON_DEVICE)
struct TestStatistics { unsigned begins=0,restores=0;u32 hz=0; };
void test_clock(u32 initial_hz);
TestStatistics test_statistics();
#endif
}
#endif

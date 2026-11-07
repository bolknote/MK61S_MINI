#ifndef MK61_PICOCALC_AI_CLOCK_HPP
#define MK61_PICOCALC_AI_CLOCK_HPP
#include "rust_types.h"
namespace picocalc::ai_clock {
struct State {
  u32 sys=0,peri=0,peri_ctrl=0,peri_div=0,spi0_hz=0,spi1_hz=0;
  bool changed=false,restore_attempted=false;
};
struct Report {
  u32 stage=0,target_mhz=0,measured_khz=0,vreg_raw=0,adc_raw=0;
  i32 temperature_mc=0;
  bool diagnostic=false,temperature_valid=false,trace_valid=false;
};
u32 hz();
bool begin(unsigned mhz,State& state);
bool restore(State& state);
Report sample();
}
#endif

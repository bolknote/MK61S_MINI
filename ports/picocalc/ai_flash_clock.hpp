#ifndef MK61_PICOCALC_AI_FLASH_CLOCK_HPP
#define MK61_PICOCALC_AI_FLASH_CLOCK_HPP
#include "cosmic_clock_plan.hpp"
namespace picocalc::ai_clock {
constexpr unsigned flash_divider(unsigned mhz) { return mhz>200?6U:4U; }
// This is inlined into the SRAM callback. Slow Flash before raising SYS;
// restore its normal rate only after SYS has fallen. USB/other-core exclusion
// is owned by the surrounding clock transition and flash_safe_execute.
template<class Bus> __attribute__((always_inline)) inline void apply_pll(Bus& bus,const cosmic_clock::Plan& plan) {
  if(plan.mhz>200)bus.divider(flash_divider(plan.mhz));
  bus.pll(plan);
  if(plan.mhz<=200)bus.divider(flash_divider(plan.mhz));
}
}
#endif

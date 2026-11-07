#ifndef MK61_AI_CLOCK_TRANSITION_HPP
#define MK61_AI_CLOCK_TRANSITION_HPP
#include "cosmic_clock_plan.hpp"
namespace picocalc::ai_clock {
// Hardware and HOST fault-injection share this ordering. No voltage or PERI
// reconfiguration is part of a rate transition. USB stays reset across PLL.
template<class Bus> bool change(Bus& bus,const cosmic_clock::Plan& before,const cosmic_clock::Plan& after) {
  if(!bus.allowed())return false;
  bus.prepare();bus.mark(1,after.mhz);
  if(after.mhz>before.mhz && !bus.pio(after.pio_div256))return false;
  bus.mark(2,after.mhz);bus.disconnect();
  if(!bus.deinit())return false;
  bus.mark(3,after.mhz);bus.reset();bus.detach_delay();bus.mark(4,after.mhz);
  bool ok=bus.pll(after);
  if(after.mhz<=before.mhz)ok=bus.pio(after.pio_div256)&&ok;
  bus.retune_i2c();bus.mark(7,after.mhz);
  ok=bus.verify(after)&&ok;
  bus.mark(8,after.mhz);bus.unreset();
  const bool usb=bus.init();if(usb)bus.connect();
  if(ok && usb)bus.mark(9,after.mhz);
  return ok && usb;
}
}
#endif

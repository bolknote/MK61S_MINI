#ifndef MK61_PICOCALC_AUDIO_HPP
#define MK61_PICOCALC_AUDIO_HPP
#include "rust_types.h"
namespace picocalc::audio {
struct Plan {
  u32 wrap=0, divider16=0, level=0, period_us=0, on_us=0;
  bool software=false;
};
// PWM has a 16-bit counter and an 8.4 divider. Sub-audible notes outside
// that range use the foreground timer instead of truncating the counter.
inline Plan plan(u32 clock_hz,unsigned frequency,unsigned master,unsigned percent) {
  Plan out;
  if(!frequency || frequency>65535 || !master || master>10 || !percent || percent>100) return out;
  u64 divider=((u64)clock_hz*16+frequency*65536ULL-1)/(frequency*65536ULL);
  if(divider<16) divider=16;
  if(divider>4095) {
    out.software=true;out.period_us=1000000/frequency;
    out.on_us=(out.period_us*master*percent+2000)/4000;
    if(!out.on_us) out.on_us=1;
  } else {
    out.divider16=(u32)divider;
    out.wrap=(u32)(((u64)clock_hz*16)/(divider*frequency));
    out.level=(out.wrap*master*percent+2000)/4000;
    if(!out.level) out.level=1;
  }
  return out;
}
}
#endif

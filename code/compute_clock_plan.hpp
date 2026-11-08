#ifndef MK61_COMPUTE_CLOCK_PLAN_HPP
#define MK61_COMPUTE_CLOCK_PLAN_HPP
#include <stdint.h>

namespace compute_clock {
enum class Platform : uint8_t { F401, F411, PICO };
constexpr uint8_t profile_count(Platform p) {return p==Platform::F411?5:3;}
constexpr uint8_t normalize(Platform p,uint8_t profile) {return profile<profile_count(p)?profile:0;}
constexpr uint16_t high_mhz(Platform p,uint8_t profile) {
  profile=normalize(p,profile);
  return p==Platform::PICO ? (profile==1?200:profile==2?250:125) :
      p==Platform::F401 ? (profile==1?96:profile==2?108:84) :
      (profile==1?108:profile==2?120:profile==3?132:profile==4?138:96);
}
// These F411 PLL plans cannot produce USB48; the complete profile is
// explicitly offline, including idle/wait. Changing a profile requires reset.
constexpr bool usb_available(Platform p,uint8_t profile) {
  return p!=Platform::F411 || normalize(p,profile)<3;
}
constexpr uint16_t low_mhz(Platform p,uint8_t profile) {
  return high_mhz(p,profile)/(normalize(p,profile)?2:1);
}
constexpr uint8_t step(Platform p,uint8_t profile,int direction) {
  const auto count=profile_count(p);
  return uint8_t((normalize(p,profile)+(direction<0?count-1:1))%count);
}
struct Stm32Plan {
  uint16_t mhz,n;
  uint8_t p,q,latency;
  uint32_t fast_cfgr,slow_cfgr;
};
constexpr Stm32Plan stm32_plan(Platform p,uint8_t profile) {
  profile=normalize(p,profile);
  const uint16_t mhz=high_mhz(p,profile);
  const uint8_t divisor=mhz<=108 && (profile || p==Platform::F401)?4:2;
  const uint16_t n=uint16_t(mhz*divisor);
  // Stock profiles retain the qualified tree. Compute profiles keep both
  // APB clocks unchanged while HPRE changes, including their timer clocks.
  return {mhz,n,uint8_t(divisor/2-1),uint8_t(usb_available(p,profile)?n/48:6),
      uint8_t(profile?(mhz>120?5:4):(p==Platform::F401?2:3)),
      profile?((5U<<10)|(5U<<13)):(4U<<10),
      profile?((8U<<4)|(4U<<10)|(4U<<13)):(4U<<10)};
}
constexpr bool valid_stm32(Platform p,uint8_t profile) {
  const auto v=stm32_plan(p,profile);
  return p!=Platform::PICO && profile==normalize(p,profile) && v.n>=192 && v.n<=432 &&
      v.q>=2 && v.q<=15 && (!usb_available(p,profile) || (v.n/v.q==48 && v.n%v.q==0)) &&
      v.n/(2U*(v.p+1U))==v.mhz &&
      (profile ? v.mhz/4<=42 && v.mhz/2<=84 : true);
}
static_assert(valid_stm32(Platform::F401,0) && valid_stm32(Platform::F401,1) &&
    valid_stm32(Platform::F401,2) && valid_stm32(Platform::F411,0) &&
    valid_stm32(Platform::F411,1) && valid_stm32(Platform::F411,2) &&
    valid_stm32(Platform::F411,3) && valid_stm32(Platform::F411,4),"compute clock tree");

// A short release grace joins adjacent calculator quanta and chained VM
// calls. Explicit blocking waits bypass it. All comparisons tolerate wrap.
struct Demand {
  uint16_t users=0,waits=0;
  uint8_t holds=0;
  bool cooling=false;
  uint32_t release_at=0;
  bool acquire() {if(users==UINT16_MAX)return false;++users;cooling=false;return true;}
  void release(uint16_t count,uint32_t now) {
    if(count>users)count=users;
    if(!count)return;
    users=uint16_t(users-count);
    if(!users && !holds){cooling=true;release_at=now+4;}
  }
  bool wanted(uint32_t now) const {
    return holds || (!waits && (users || (cooling && int32_t(now-release_at)<0)));
  }
};
}
#endif

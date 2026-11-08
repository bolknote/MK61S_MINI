#include "compute_clock.hpp"
#include "loadable_app_services.h"
#include <cassert>
#include <cstdio>
#include <vector>
using namespace compute_clock;
namespace {uint32_t now;bool busy;std::vector<bool> transitions;uint32_t hz=96000000;}
namespace compute_clock {
Platform platform(){return Platform::F411;}
namespace backend {
bool configure(uint8_t profile){::hz=low_mhz(platform(),profile)*1000000U;return true;}
bool set_fast(bool high){if(busy)return false;transitions.push_back(high);::hz=high?120000000:60000000;return true;}
uint32_t hz(){return ::hz;}
uint32_t now_ms(){return now;}
}}
int main(int argc,char**) {
  if(argc>1) {
    assert(configure(0) && hz==96000000 && !configure(1));
    {Owner app;const auto token=service(MK61_COMPUTE_BEGIN,0);
      assert(token && !acquire() && !pause());
      assert(service(MK61_COMPUTE_END,token) && !service(MK61_COMPUTE_END,token));
    }
    poll(100);assert(hz==96000000 && transitions.empty());
    std::puts("Stock compute policy: optional APP hints retain 96MHz and reject live PLL reconfiguration PASS");
    return 0;
  }
  for(auto p:{Platform::F401,Platform::F411})for(unsigned i=0;i<profile_count(p);++i) {
    assert(valid_stm32(p,i));const auto plan=stm32_plan(p,i);
    assert(plan.n/(2*(plan.p+1))==high_mhz(p,i) && (!usb_available(p,i) || plan.n/plan.q==48));
    assert(step(p,step(p,i,1),-1)==i);
    assert(low_mhz(p,i)==high_mhz(p,i)/(i?2:1));
    for(unsigned shift:{10,13}) {
      const auto divisor=[&](uint32_t cfg) {unsigned field=(cfg>>shift)&7;return field<4?1U:1U<<(field-3);};
      const unsigned fast_div=divisor(plan.fast_cfgr),slow_div=divisor(plan.slow_cfgr);
      assert(high_mhz(p,i)/fast_div==low_mhz(p,i)/slow_div);
      assert(high_mhz(p,i)/fast_div*(fast_div>1?2:1)==low_mhz(p,i)/slow_div*(slow_div>1?2:1));
    }
  }
  assert(profile_count(Platform::F411)==5);
  assert(high_mhz(Platform::F411,3)==132 && high_mhz(Platform::F411,4)==138);
  assert(!usb_available(Platform::F411,3) && !usb_available(Platform::F411,4));
  assert(usb_available(Platform::F411,0) && usb_available(Platform::F411,1) && usb_available(Platform::F411,2));
  assert(normalize(Platform::F401,3)==0 && normalize(Platform::PICO,3)==0);
  assert(high_mhz(Platform::PICO,1)==200 && low_mhz(Platform::PICO,2)==125);
  assert(service(MK61_COMPUTE_PROBE,0)==MK61_COMPUTE_MAGIC);
  assert(service(MK61_COMPUTE_BEGIN,0)==0 && !configure(255));
  assert(configure(2));
  assert(configure(2) && !configure(1));
  uint32_t stale=0;
  {Owner root;
    const auto first=service(MK61_COMPUTE_BEGIN,0);stale=first;
    assert(first && hz==120000000);
    const auto second=service(MK61_COMPUTE_BEGIN,0);
    assert(second!=first && !service(MK61_COMPUTE_END,first));
    {Wait waiting;assert(hz==60000000);{Wait nested;assert(hz==60000000);}assert(hz==60000000);}
    assert(hz==120000000 && service(MK61_COMPUTE_END,second));
    {Owner child;assert(!service(MK61_COMPUTE_END,first));assert(service(MK61_COMPUTE_BEGIN,0));}
    assert(service(MK61_COMPUTE_END,first));
  }
  now=3;poll(now);assert(hz==120000000);
  now=4;poll(now);assert(hz==60000000);
  {Owner next;assert(!service(MK61_COMPUTE_END,stale));}
  busy=true;
  {Scope compute;assert(hz==60000000);busy=false;poll(now);assert(hz==120000000);
    now=8;{Scope nested;}poll(now);assert(hz==120000000);
    audio_floor(true);{Wait waiting;assert(hz==120000000);}assert(hz==120000000);
  }
  now=100;poll(now);assert(hz==120000000);audio_floor(false);
  now=104;poll(now);assert(hz==60000000);
  now=UINT32_MAX-1;{Scope compute;}poll(now);assert(hz==120000000);
  now=1;poll(now);assert(hz==120000000);now=2;poll(now);assert(hz==60000000);
  std::puts("Compute clock: USB48/offline plans, nested scopes/waits, APP ownership/stale tokens, delayed release/wrap, busy backend, audio floor PASS");
}

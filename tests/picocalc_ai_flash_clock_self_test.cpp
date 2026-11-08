#define MK61_PICOCALC_AI_OVERCLOCK 1
#include "ai_flash_clock.hpp"
#include <cassert>
#include <cstdio>
struct Bus {
  unsigned mhz,div,calls=0;
  void check() { assert(mhz<=50*div); }
  void divider(unsigned n){++calls;div=n;check();}
  void pll(const picocalc::cosmic_clock::Plan& p){++calls;mhz=p.mhz;check();}
};
int main() {
  using namespace picocalc;
  Bus b{125,4};
  for(unsigned i=0;i<100;++i) {
    ai_clock::apply_pll(b,*cosmic_clock::find(270));assert(b.mhz==270&&b.div==6);
    ai_clock::apply_pll(b,*cosmic_clock::find(125));assert(b.mhz==125&&b.div==4);
  }
  assert(b.calls==400);
  assert(ai_clock::flash_divider(200)==4&&ai_clock::flash_divider(270)==6);
  std::puts("AI Flash clock:125/div4 ->270/div6 ->125/div4; <=50MHz throughout100 cycles PASS");
}

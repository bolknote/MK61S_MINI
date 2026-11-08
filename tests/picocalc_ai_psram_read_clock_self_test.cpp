#include "ai_psram_read_clock.hpp"
#include <cassert>
#include <cstdio>
int main(){using picocalc::ai_psram_read_clock::divider256;
#if MK61_PICOCALC_AI_PSRAM_LATE_READ
constexpr unsigned selected=346,limit=200000000;
#else
constexpr unsigned selected=461,limit=150000000;
#endif
for(unsigned mhz=100;mhz<=300;++mhz)for(unsigned div=256;div<=768;++div){
 const unsigned got=divider256(mhz*1000000,div);
 if(mhz==270&&div==692)assert(got==selected);else assert(got==div);
}
assert(270000000ULL*256<=1ULL*limit*divider256(270000000,692));
std::printf("Only270MHz AI QPI-read profile changes; divider%u, PIO <=%uHz PASS\n",selected,limit);}

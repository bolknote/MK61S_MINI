#include "ai_psram_read_clock.hpp"
#include <cassert>
#include <cstdio>
int main(){using picocalc::ai_psram_read_clock::divider256;
using namespace picocalc::ai_psram_read_clock;
static_assert(sweep_divider(461) && sweep_divider(419) && sweep_divider(384) && sweep_divider(346));
static_assert(sweep_divider(320) && sweep_divider(288) && sweep_divider(256));
static_assert(sweep_divider(339) && sweep_divider(329) && sweep_divider(325));
static_assert(!sweep_divider(255) && !sweep_divider(345) && !sweep_divider(385) && !sweep_divider(462));
static_assert(!late_burst_sample(461) && late_burst_sample(419) && late_burst_sample(384) && late_burst_sample(346));
static_assert(late_burst_sample(320) && late_burst_sample(288) && late_burst_sample(256));
static_assert(late_burst_sample(339) && late_burst_sample(329) && late_burst_sample(325));
static_assert(high_burst_dividers[0]==default_burst_divider);
static_assert(270000000ULL*256/(6*high_burst_dividers[1])==36000000);
static_assert(270000000ULL*256/(6*high_burst_dividers[2])==40000000);
static_assert(270000000ULL*256/(6*high_burst_dividers[3])==45000000);
static_assert(near_default_burst_dividers[0]==default_burst_divider);
static_assert(270000000ULL*256/(6*near_default_burst_dividers[1])==33982300);
static_assert(270000000ULL*256/(6*near_default_burst_dividers[2])==35015197);
static_assert(270000000ULL*256/(6*near_default_burst_dividers[3])==35446153);
static_assert(default_burst_divider==346 && late_burst_sample(default_burst_divider));
static_assert(control_burst_divider==461 && !late_burst_sample(control_burst_divider));
static_assert(ai_profile(270000000,692) && !ai_profile(125000000,320) && !ai_profile(270000000,461));
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

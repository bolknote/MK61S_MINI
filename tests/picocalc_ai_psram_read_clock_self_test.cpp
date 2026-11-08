#include "ai_psram_read_clock.hpp"
#include <cassert>
#include <cstdio>
int main(){using picocalc::ai_psram_read_clock::divider256;
for(unsigned mhz=100;mhz<=300;++mhz)for(unsigned div=256;div<=768;++div){
 const unsigned got=divider256(mhz*1000000,div);
 if(mhz==270&&div==692)assert(got==461);else assert(got==div);
}
assert(270000000ULL*256<=150000000ULL*divider256(270000000,692));
std::puts("Only270MHz qualified AI QPI-read profile changes; <=25MHz SCK PASS");}

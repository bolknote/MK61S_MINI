#pragma once
#include <cstdint>
inline int research_coefficient(unsigned grid,unsigned u) {
 static constexpr int lns[8]={0,1,2,4,8,16,32,64};
 static constexpr int apot[8]={0,1,2,3,4,6,8,10};
 const int magnitude=(grid&1024)?apot[u&7]:lns[u&7];return(u&8)?-magnitude:magnitude;
}

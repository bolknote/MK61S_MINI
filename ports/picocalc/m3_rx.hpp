#ifndef MK61_PICOCALC_M3_RX_HPP
#define MK61_PICOCALC_M3_RX_HPP
#include <cstdint>
namespace picocalc::m3 {
// Catch bytes arriving during parsing without waiting for another worker
// turn. Bound a service call by one ring and four producer-head snapshots.
template<unsigned Capacity,class Head,class Feed>
bool drain_receive(const uint8_t* ring,uint32_t& tail,uint32_t& received,Head head,Feed feed) {
    static_assert(Capacity && !(Capacity&(Capacity-1)));
    unsigned budget=Capacity;
    for(unsigned pass=0;pass<4 && budget;++pass) {
        const uint32_t limit=head();
        if(limit-tail>Capacity){tail=limit;return false;}
        unsigned count=limit-tail;if(count>budget)count=budget;
        if(!count)break;
        budget-=count;received+=count;
        while(count) {
            const unsigned at=tail&(Capacity-1),part=count<Capacity-at?count:Capacity-at;
            feed(ring+at,part);tail+=part;count-=part;
        }
    }
    return true;
}
}
#endif

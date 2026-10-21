#ifndef MK61_PICOCALC_EVENT_WAIT_HPP
#define MK61_PICOCALC_EVENT_WAIT_HPP
#include <cstdint>
namespace picocalc {
// Clear an old event before rechecking the persistent predicate. An event
// arriving after that check remains latched for sleep(). Spurious wakeups
// are harmless. sleep() must also have a bounded timer fallback.
template<class Pending,class Clear,class Sleep>
uint32_t event_wait(Pending pending,Clear clear,Sleep sleep) {
    if(!pending()) return 0;
    clear();
    uint32_t waits=0;
    while(pending()) { sleep();++waits; }
    return waits;
}
}
#endif

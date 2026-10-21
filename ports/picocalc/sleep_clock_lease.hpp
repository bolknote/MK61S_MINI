#ifndef MK61_PICOCALC_SLEEP_CLOCK_LEASE_HPP
#define MK61_PICOCALC_SLEEP_CLOCK_LEASE_HPP
#include <cstdint>
namespace picocalc {
// Retain only clocks missing from the current sleep policy, then restore
// those bits. Nested leases and unrelated clock owners remain intact.
template<class Registers> class SleepClockLease {
    uint32_t added0_,added1_;
public:
    SleepClockLease(uint32_t mask0,uint32_t mask1):
        added0_(mask0&~Registers::read0()),added1_(mask1&~Registers::read1()) {
        if(added0_) Registers::set0(added0_);
        if(added1_) Registers::set1(added1_);
    }
    ~SleepClockLease() {
        if(added0_) Registers::clear0(added0_);
        if(added1_) Registers::clear1(added1_);
    }
    SleepClockLease(const SleepClockLease&)=delete;
    SleepClockLease& operator=(const SleepClockLease&)=delete;
    bool temporary() const { return added0_ || added1_; }
};
}
#endif

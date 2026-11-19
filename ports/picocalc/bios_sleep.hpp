#ifndef MK61_PICOCALC_BIOS_SLEEP_CONTROL_HPP
#define MK61_PICOCALC_BIOS_SLEEP_CONTROL_HPP
#include "bios/bios_sleep.h"
#include <stdint.h>

namespace picocalc {
class BiosSleep {
public:
    enum Operation : uint8_t { NONE, PROBE, ENTER, LEAVE };
    void idle(bool value) { if (wanted_ != value) { wanted_=value;due_=0; } }
    Operation next(uint64_t now) const {
        if (now < due_) return NONE;
        if (support_ != 1) return PROBE; // Never write before tagged discovery.
        if (wanted_ || wanted_ != requested_) return wanted_ ? ENTER : LEAVE;
        return PROBE;
    }
    void reply(uint64_t now, int count, const uint8_t *data) {
        if (count != 2) {
            ++errors_;support_=-1;requested_=slept_=false;due_=now+250000;
        } else if (data[0] != BIOS_SLEEP_REG || (data[1]&BIOS_SLEEP_MASK) != BIOS_SLEEP_TAG ||
                   ((data[1]&BIOS_SLEEP_SLEPT) && !(data[1]&BIOS_SLEEP_REQUESTED))) {
            support_=0;requested_=slept_=false;due_=now+20000000;
        } else {
            support_=1;requested_=data[1]&BIOS_SLEEP_REQUESTED;slept_=data[1]&BIOS_SLEEP_SLEPT;
            due_=now+(wanted_!=requested_ ? 0 : wanted_ ? 500000 : 20000000);
        }
    }
    int supported() const { return support_; }
    bool wanted() const { return wanted_; }
    bool requested() const { return requested_; }
    bool slept() const { return slept_; }
    uint32_t errors() const { return errors_; }
private:
    uint64_t due_=0;
    uint32_t errors_=0;
    int8_t support_=-1;
    bool wanted_=false,requested_=false,slept_=false;
};
}
#endif

#ifndef MK61_PICOCALC_SELECTIVE_IRQ_MASK_HPP
#define MK61_PICOCALC_SELECTIVE_IRQ_MASK_HPP
#include <cstdint>
namespace picocalc {
// Mask only a peripheral's cooperating IRQs on the current core. In
// particular, do not block a higher-priority PWM consumer. Preserve both
// pending interrupts and IRQs which were already disabled by an outer owner.
template<class Port> class SelectiveIrqMask {
    Port& port_;
    uint32_t restore_;
public:
    SelectiveIrqMask(Port& port,uint32_t mask):port_(port),restore_(port.enabled()&mask) {
        port_.disable(restore_);
    }
    ~SelectiveIrqMask(){port_.enable(restore_);}
    SelectiveIrqMask(const SelectiveIrqMask&)=delete;
    SelectiveIrqMask& operator=(const SelectiveIrqMask&)=delete;
};
}
#endif

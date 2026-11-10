#ifndef MK61_PICOCALC_AUDIO_IRQ_PRIORITY_HPP
#define MK61_PICOCALC_AUDIO_IRQ_PRIORITY_HPP
#include <cstdint>
namespace picocalc::audio_stream {
// This lease applies only to the bounded M3 PWM consumer on core1. Restore
// its shared alarm pool's previous priority before any other synth uses it.
struct AudioIrqPriority {
    uint8_t irq=0,previous=0,owner=0;bool active=false;
    template<class Port> bool acquire(Port& port,unsigned alarm_irq,unsigned pool_owner) {
        if(active || pool_owner!=1 || port.core()!=pool_owner)return false;
        irq=uint8_t(alarm_irq);owner=uint8_t(pool_owner);previous=uint8_t(port.priority(irq));
        port.set_priority(irq,0);active=true;return true;
    }
    template<class Port> bool release(Port& port) {
        if(!active)return true;
        if(port.core()!=owner)return false;
        port.set_priority(irq,previous);active=false;return true;
    }
};
}
#endif

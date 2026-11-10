#ifndef MK61_PICOCALC_AUDIO_IRQ_ENTRY_HPP
#define MK61_PICOCALC_AUDIO_IRQ_ENTRY_HPP
#include <cstddef>
#include <cstdint>
namespace picocalc {
// Diagnostic tail wrapper of this stream's existing, exclusive pool IRQ.
// Setup/teardown happen outside playback; pending IRQs and NVIC are untouched.
struct AudioIrqEntry {
    using Handler=void(*)();
    Handler next=nullptr;
    volatile uint32_t pc=0,psr=0,entered_us=0;
    uint32_t fault_pc=0,fault_psr=0,fault_dispatch_us=0;
    uint8_t irq=0,owner=0;
    bool active=false;
    template<class Port> bool acquire(Port& p,unsigned number,unsigned pool_owner,Handler wrapper) {
        if(!wrapper || active || number>=32 || pool_owner!=1 || p.core()!=pool_owner)return false;
        const auto saved=p.mask();
        const auto handler=p.get(number);
        if(!handler || handler==wrapper){p.unmask(saved);return false;}
        next=handler;irq=uint8_t(number);owner=uint8_t(pool_owner);
        pc=psr=entered_us=0;fault_pc=fault_psr=fault_dispatch_us=0;
        active=true;p.replace(number,handler,wrapper);p.unmask(saved);return true;
    }
    template<class Port> bool release(Port& p,Handler wrapper) {
        if(!active)return true;
        if(p.core()!=owner)return false;
        const auto saved=p.mask();
        if(p.get(irq)!=wrapper){p.unmask(saved);return false;}
        p.replace(irq,wrapper,next);active=false;next=nullptr;p.unmask(saved);return true;
    }
    void fault(uint32_t started) {
        fault_pc=pc;fault_psr=psr;fault_dispatch_us=started-entered_us;
    }
};
#if defined(__ARM_ARCH_6M__)
static_assert(offsetof(AudioIrqEntry,next)==0 && offsetof(AudioIrqEntry,pc)==4 &&
              offsetof(AudioIrqEntry,psr)==8 && offsetof(AudioIrqEntry,entered_us)==12);
static_assert(sizeof(AudioIrqEntry)==32);
#endif
}
#endif

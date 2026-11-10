#include "audio_irq_entry.hpp"
#include <array>
#include <cassert>
#include <cstdio>
using picocalc::AudioIrqEntry;
static unsigned called=0;
static void sdk(){++called;}
static void foreign(){}
static AudioIrqEntry trace;
static void wrapper(){assert(trace.next);trace.next();}
struct Port {
    std::array<AudioIrqEntry::Handler,32> table{};
    unsigned current_core=1,enabled=0x11881,pending=0,changes=0,mask_calls=0;
    bool masked=false;
    unsigned core()const{return current_core;}
    bool mask(){++mask_calls;const bool before=masked;masked=true;return before;}
    void unmask(bool before){masked=before;if(!masked && (pending&enabled&8)){pending&=~8U;table[3]();}}
    auto get(unsigned irq){return table[irq];}
    void replace(unsigned irq,AudioIrqEntry::Handler before,AudioIrqEntry::Handler after){
        assert(masked && table[irq]==before);table[irq]=after;++changes;
    }
};
int main(){
    Port port;port.enabled|=8;port.table[3]=sdk;
    assert(!trace.acquire(port,3,1,nullptr));
    assert(!trace.acquire(port,32,1,wrapper) && !trace.acquire(port,3,0,wrapper));
    port.current_core=0;assert(!trace.acquire(port,3,1,wrapper));port.current_core=1;
    port.table[3]=nullptr;assert(!trace.acquire(port,3,1,wrapper));
    port.table[3]=wrapper;assert(!trace.acquire(port,3,1,wrapper));port.table[3]=sdk;
    assert(!port.changes && !trace.active);
    for(unsigned i=0;i<1024;++i){
        const auto enabled=port.enabled;port.pending=8;
        const auto before=called;assert(trace.acquire(port,3,1,wrapper));
        assert(called==before+1 && !port.pending && port.enabled==enabled && !port.masked);
        assert(port.table[3]==wrapper && trace.next==sdk && trace.active);
        assert(!trace.acquire(port,3,1,wrapper));
        for(uint32_t begin:{0U,7U,0xfffffff0U}){
            trace.pc=0x10001000+i*2;trace.psr=0x01000000|(i%64);trace.entered_us=begin;
            trace.fault(begin+77);
            assert(trace.fault_pc==trace.pc && trace.fault_psr==trace.psr && trace.fault_dispatch_us==77);
        }
        port.current_core=0;assert(!trace.release(port,wrapper) && port.table[3]==wrapper);
        port.current_core=1;port.table[3]=foreign;
        assert(!trace.release(port,wrapper) && trace.active && port.table[3]==foreign);
        port.table[3]=wrapper;port.pending=8;
        assert(trace.release(port,wrapper));
        assert(called==before+2 && !port.pending && port.enabled==enabled && !port.masked);
        assert(port.table[3]==sdk && !trace.active && !trace.next);
        assert(trace.release(port,wrapper));
    }
    // An already-masked setup context must stay masked, with IRQ still pending.
    port.masked=true;port.pending=8;assert(trace.acquire(port,3,1,wrapper));
    assert(port.masked && port.pending==8);assert(trace.release(port,wrapper));
    assert(port.masked && port.pending==8);port.unmask(false);assert(!port.pending);
    std::puts("Owned IRQ trace:1024 acquire/release cycles, unchanged NVIC/pending dispatch, exact handler restoration, wrong owner/foreign handlers rejected, nested PRIMASK and timestamp wrap PASS");
}

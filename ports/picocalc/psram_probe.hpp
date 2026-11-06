#ifndef MK61_PICOCALC_PSRAM_PROBE_HPP
#define MK61_PICOCALC_PSRAM_PROBE_HPP
#include "rust_types.h"

namespace picocalc::psram {
enum class ProbePhase : u32 { NONE,WRITE,READ,COMPARE,ENTER_QPI,RESET_SPI };
struct ProbeFailure { ProbePhase phase{};u32 qpi=0,address=0,expected=0,actual=0; };
struct BootProbe { u32 qpi_attempts=0,failures=0;ProbeFailure first{};ProbePhase last_failure{}; };
inline const char* probe_phase_name(ProbePhase phase) {
    switch(phase) {
    case ProbePhase::WRITE:return "WRITE";
    case ProbePhase::READ:return "READ";
    case ProbePhase::COMPARE:return "COMPARE";
    case ProbePhase::ENTER_QPI:return "ENTER_QPI";
    case ProbePhase::RESET_SPI:return "RESET_SPI";
    default:return "NONE";
    }
}
inline bool probe_failure(BootProbe& out,ProbePhase phase,bool qpi,u32 address,u32 expected,u32 actual) {
    if(!out.failures) out.first={phase,qpi?1U:0U,address,expected,actual};
    ++out.failures;out.last_failure=phase;return false;
}
// Destructive only to volatile RAM, before the allocator publishes it. A
// verified zero anchor is essential: isolated powers of two can otherwise
// read back their own last write even with an address bit stuck low.
template<class Bus> bool sparse_probe(Bus& bus,BootProbe& out,bool qpi) {
    constexpr u32 CAPACITY=8U*1024*1024,UNKNOWN=0xFFFFFFFFU;
    for(unsigned pass=0;pass<2;++pass) for(unsigned i=0;i<25;++i) {
        const u32 at=i==0?0:i==24?CAPACITY-1:1U<<(i-1);
        const u8 expected=(u8)(i*37+13);u8 actual=0;
        if(!pass) {
            if(!bus.write(at,&expected,1)) return probe_failure(out,ProbePhase::WRITE,qpi,at,expected,UNKNOWN);
        } else {
            if(!bus.read(at,&actual,1)) return probe_failure(out,ProbePhase::READ,qpi,at,expected,UNKNOWN);
            if(actual!=expected) return probe_failure(out,ProbePhase::COMPARE,qpi,at,expected,actual);
        }
    }
    u8 expected[32],actual[32];
    for(unsigned pass=0;pass<2;++pass) for(unsigned block=0;block<2;++block) {
        const u32 at=block?CAPACITY-32:0;
        for(unsigned i=0;i<sizeof(expected);++i) expected[i]=(u8)(block*37+i*13);
        if(!pass) {
            if(!bus.write(at,expected,sizeof(expected))) return probe_failure(out,ProbePhase::WRITE,qpi,at,expected[0],UNKNOWN);
        } else {
            if(!bus.read(at,actual,sizeof(actual))) return probe_failure(out,ProbePhase::READ,qpi,at,expected[0],UNKNOWN);
            for(unsigned i=0;i<sizeof(expected);++i) if(expected[i]!=actual[i])
                return probe_failure(out,ProbePhase::COMPARE,qpi,at+i,expected[i],actual[i]);
        }
    }
    return true;
}
// Exactly one recovery attempt, only during boot qualification. Every
// failed QPI attempt runs the SPI reset sequence before another attempt
// or the final SPI probe. Runtime data is never reset or retried.
template<class Bus> bool qualify_boot(Bus& bus,BootProbe& out,bool allow_qpi) {
    if(allow_qpi) {
        for(unsigned attempt=0;attempt<2;++attempt) {
            ++out.qpi_attempts;
            if(!bus.enter_qpi()) probe_failure(out,ProbePhase::ENTER_QPI,true,0,0,0xFFFFFFFFU);
            else if(sparse_probe(bus,out,true)) return true;
            if(!bus.reset_spi()) return probe_failure(out,ProbePhase::RESET_SPI,true,0,0,0xFFFFFFFFU);
        }
        bus.fallback();
    }
    return sparse_probe(bus,out,false);
}
}
#endif

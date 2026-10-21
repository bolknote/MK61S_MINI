#include "buffers.hpp"
#include "psram.hpp"
#include "diagnostics.hpp"
#include "external_cache.hpp"
#include <cstring>
#if defined(PICO_ON_DEVICE)
#include "pico/stdlib.h"
#endif
namespace picocalc::buffers {
namespace {
bool initialized = false;
bool foreground() {
#if defined(PICO_ON_DEVICE)
    return get_core_num() == 0;
#else
    return true;
#endif
}
bool read(u32 address,void* bytes,usize size) { return psram::read(address,bytes,size); }
bool write(u32 address,const void* bytes,usize size) { return psram::write(address,bytes,size); }
u8 pattern(u32 address) { return (u8)((address*73U)^(address>>8)^(address>>16)^0xA7U); }
}
bool init() {
    if(initialized) return true;
    initialized=shared_memory::configure_buffer_backend({psram::CAPACITY,psram::ready,read,write,foreground});
    return initialized;
}
TestResult self_test(void (*service)()) {
    using namespace shared_memory;
    TestResult result{};
    if(!init() || !psram::ready() || !validate_buffer_invariants()) return result;
    Buffer direct,large;
    constexpr u32 size=1024U*1024,allocation=6U*1024*1024;
    if(!direct.acquire(Owner::APPLICATION,512) || !direct.data() ||
       !large.acquire(Owner::APPLICATION,allocation,BufferAccess::EXTERNAL) || large.data()) return result;
    u8 expected[1024],actual[1024];
    const u64 start=diagnostics::timestamp();
    for(u32 at=0;at<size;at+=sizeof(expected)) {
        for(unsigned i=0;i<sizeof(expected);++i) expected[i]=pattern(at+i);
        if(!large.write(at,expected,sizeof(expected))) return result;
        diagnostics::feed_watchdog();if(service && !(at&16383)) service();
    }
    result.write_us=(u32)(diagnostics::timestamp()-start);
    // Rebuild both caches in the remaining 2 MiB. Their headers and payloads
    // must never alias the required buffer, including above the old 4 MiB split.
    for(unsigned i=0;i<sizeof(expected);++i) expected[i]=pattern(allocation-1024+i);
    if(!large.write(allocation-1024,expected,sizeof(expected))) return result;
    external_cache::store_module(0x51504942,expected,sizeof(expected),"<buffer self-test>");
    external_cache::store_sector(UINT32_MAX,expected);
    unsigned count=0;
    if(!external_cache::module(0x51504942,actual,sizeof(actual),count,"<buffer self-test>") ||
       count!=sizeof(expected) || std::memcmp(expected,actual,sizeof(expected))) return result;
    if(!external_cache::sector(UINT32_MAX,actual) || std::memcmp(expected,actual,512)) return result;
    if(!large.read(allocation-1024,actual,sizeof(actual)) || std::memcmp(expected,actual,sizeof(expected))) return result;
    const u64 read_start=diagnostics::timestamp();
    for(u32 at=0;at<size;at+=sizeof(actual)) {
        for(unsigned i=0;i<sizeof(expected);++i) expected[i]=pattern(at+i);
        if(!large.read(at,actual,sizeof(actual)) || std::memcmp(expected,actual,sizeof(actual))) return result;
        diagnostics::feed_watchdog();if(service && !(at&16383)) service();
    }
    result.read_us=(u32)(diagnostics::timestamp()-read_start);
    {
        BufferWindow window;
        if(!window.acquire(large,1021,513,true) || large.reset()) return result;
        for(unsigned i=0;i<window.size();++i) if(window.data()[i]!=pattern(1021+i)) return result;
        std::memset(window.data(),0x5A,window.size());
        if(!window.writeback()) return result;
    }
    if(!large.read(1021,actual,513)) return result;
    for(unsigned i=0;i<513;++i) if(actual[i]!=0x5A) return result;
    if(large.read(allocation,actual,1) || large.write(UINT32_MAX,actual,2)) return result;
    if(!direct.fill(0x6B) || direct.data()[511]!=0x6B) return result;
    if(!large.reset() || !direct.reset() || !validate_buffer_invariants()) return result;
    result.passed=true;result.bytes=size;result.allocation=allocation;return result;
}
}

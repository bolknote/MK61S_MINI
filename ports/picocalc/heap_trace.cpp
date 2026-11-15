#include "heap_trace.hpp"
#include "pico/critical_section.h"
#include "pico/multicore.h"
#include <atomic>
#include <cstdio>
#if defined(PICO_ON_DEVICE)
#define HEAP_TRACE_CODE __attribute__((noinline,section(".ai_diagnostic_extension"),optimize("Os")))
#else
#define HEAP_TRACE_CODE __attribute__((noinline))
#endif

namespace picocalc::heap_trace {
namespace {
constexpr unsigned CAPACITY=128;
Event events[CAPACITY];
unsigned used=0,dropped=0;
critical_section_t guard;
bool initialized=false;
std::atomic<bool> enabled{false};
HEAP_TRACE_CODE void append(Kind kind,const void* address,uint32_t value,const void* site) {
    if(used==CAPACITY) { if(dropped!=UINT32_MAX) ++dropped;return; }
    events[used++]={(uint32_t)(uintptr_t)address,value,(uint32_t)(uintptr_t)site,
                    uint32_t(kind)|(get_core_num()<<8)};
}
}
HEAP_TRACE_CODE void start() {
    if(!initialized) { critical_section_init(&guard);initialized=true; }
    critical_section_enter_blocking(&guard);
    used=dropped=0;enabled.store(true,std::memory_order_release);
    critical_section_exit(&guard);
}
HEAP_TRACE_CODE void stop() {
    if(!initialized) return;
    critical_section_enter_blocking(&guard);
    enabled.store(false,std::memory_order_release);
    critical_section_exit(&guard);
}
HEAP_TRACE_CODE void record(Kind kind,const void* address,uint32_t value,const void* site) {
    if(!enabled.load(std::memory_order_acquire)) return;
    critical_section_enter_blocking(&guard);
    if(enabled.load(std::memory_order_relaxed)) append(kind,address,value,site);
    critical_section_exit(&guard);
}
HEAP_TRACE_CODE void realloc_result(const void* previous,const void* result,uint32_t size,const void* site) {
    if(!enabled.load(std::memory_order_acquire)) return;
    critical_section_enter_blocking(&guard);
    if(enabled.load(std::memory_order_relaxed)) {
        append(REALLOC_OLD,previous,size,site);append(REALLOC_NEW,result,size,site);
    }
    critical_section_exit(&guard);
}
HEAP_TRACE_CODE void mark(Phase phase,uint32_t detail) { record(MARK,(void*)(uintptr_t)phase,detail,nullptr); }
HEAP_TRACE_CODE bool report(Writer write,void* context) {
    if(!write || enabled.load(std::memory_order_acquire)) return false;
    char line[112];
    int n=std::snprintf(line,sizeof(line),"HEAP_TRACE count=%u dropped=%u capacity=%u\r\n",used,dropped,CAPACITY);
    write(context,line,(unsigned)n);
    for(unsigned i=0;i<used;++i) {
        const auto& e=events[i];
        n=std::snprintf(line,sizeof(line),"HEAP_EVENT n=%u kind=%lu core=%lu ptr=%08lX value=%lu pc=%08lX\r\n",
            i,(unsigned long)(e.info&255U),(unsigned long)(e.info>>8),(unsigned long)e.address,
            (unsigned long)e.value,(unsigned long)e.site);
        write(context,line,(unsigned)n);
    }
    return true;
}
}

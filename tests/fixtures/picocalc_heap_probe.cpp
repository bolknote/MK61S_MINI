#include "native_runtime.hpp"
#include <cstdint>
#include <cstdlib>
#include <malloc.h>

extern "C" { extern char __end__,__HeapLimit; }
extern "C" void* _sbrk(int increment) {
    static char* end=&__end__;
    char* previous=end;
    if(increment>0 && (uintptr_t)increment>(uintptr_t)&__HeapLimit-(uintptr_t)end)
        return (void*)-1;
    end+=increment;
    return previous;
}

// The same newlib, heap addresses and transient allocation sizes as the Pico
// regression: a released native frame and free top are separated by paths.
// Every call runs in a fresh ARM machine; no host allocator is substituted.
extern "C" unsigned heap_trial(unsigned initialize) {
    if(initialize) picocalc::initialize_heap();
    void* volatile previous=std::malloc(20000);
    if(!previous) return 1;
    std::free(previous);
    void* volatile stream=std::malloc(1024);
    void* volatile frame=std::malloc(12800);
    void* volatile paths=std::malloc(900);
    if(!stream || !frame || !paths) return 2;
    std::free(frame);
    void* volatile markdown=std::malloc(15296);
    unsigned result=markdown?4:0;
    if(markdown) {
        void* volatile image=std::malloc(8326);
        if(image) result|=8;
        std::free(image);
    }
    std::free(markdown);
    std::free(paths);std::free(stream);
    void* volatile large_app=std::malloc(30000);
    if(large_app) result|=16;
    std::free(large_app);
    const auto heap=mallinfo();
    if(heap.uordblks==0) result|=32;
    return result;
}

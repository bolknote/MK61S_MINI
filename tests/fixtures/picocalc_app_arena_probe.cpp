#include "loadable_buffer_services.hpp"
#include "native_runtime.hpp"
#include <cstdint>
#include <cstdlib>
#include <malloc.h>

extern "C" { extern char __end__,__HeapLimit; }
extern "C" { volatile std::uint32_t warm_allocator[4]{}; }
extern "C" void* _sbrk(int increment) {
    static char* end=&__end__;
    char* previous=end;
    if(increment>0 && (uintptr_t)increment>(uintptr_t)&__HeapLimit-(uintptr_t)end) return (void*)-1;
    end+=increment;return previous;
}

// Run with actual ARM newlib and the linked firmware's heap bounds. The
// representative image/PCM/frame sizes need no copyrighted game resources.
extern "C" unsigned arena_trial() {
    using loadable_buffers::Session;
    picocalc::initialize_heap();
    const auto empty=mallinfo().uordblks;
    // Reproduce the observed warm sequence with the real ARM allocator:
    // Explorer's path catalog remains live; the legacy APP creates its
    // 64-KiB pages before the PCM queue and SDK timer-pool allocations.
    void* catalog=std::malloc(640);void* name1=std::malloc(7);
    void* name2=std::malloc(21);void* name3=std::malloc(34);
    if(!catalog || !name1 || !name2 || !name3) return 15;
    void* old_image=std::calloc(1,31968+7);void* old_pages=std::malloc(64000);
    void* old_pcm=std::malloc(2064);void* timer_entries=std::malloc(24);
    void* timer_pool=std::calloc(1,48);void* old_cache=std::malloc(6144);
    if(!old_image || !old_pages || !old_pcm || !timer_entries || !timer_pool || !old_cache) return 16;
    std::free(old_pcm);std::free(old_cache);std::free(old_pages);std::free(old_image);
    const auto warm=mallinfo();
    warm_allocator[0]=(u32)warm.arena;warm_allocator[1]=(u32)warm.uordblks;
    warm_allocator[2]=(u32)warm.ordblks;warm_allocator[3]=(u32)warm.keepcost;
    if(warm.ordblks!=2 || warm.keepcost>=12000) return 17;
    void* warm_image=std::calloc(1,32216+7);void* warm_pcm=std::malloc(2064);
    if(!warm_image || !warm_pcm) return 18;
    {
        Session s;mk61_service_buffer arena{};arena.size=70144;
        if(s.call(MK61_BUFFER_RESERVE,arena)) return 19;
        mk61_service_buffer pages{};pages.size=64000;
        if(s.call(MK61_BUFFER_ACQUIRE,pages)) return 20;
        pages={};pages.size=32000;
        if(!s.call(MK61_BUFFER_ACQUIRE,pages)) return 21;
        mk61_service_buffer previous{};previous.size=32000;
        if(s.call(MK61_BUFFER_ACQUIRE,previous)) return 22;
    }
    std::free(warm_pcm);std::free(warm_image);
    // On APP exit the corrected audio service destroys both pool blocks.
    // The next APP must then fit its image, PCM, pool, both pages and cache.
    std::free(timer_pool);std::free(timer_entries);
    for(unsigned cycle=0;cycle<8;++cycle) {
        void* image=std::calloc(1,32216+7);void* pcm=std::malloc(2064);
        void* entries=std::malloc(24);void* pool=std::calloc(1,48);
        if(!image || !pcm || !entries || !pool) return 23;
        {
            Session s;mk61_service_buffer arena{};arena.size=70144;
            if(!s.call(MK61_BUFFER_RESERVE,arena)) return 24;
            mk61_service_buffer pages{};pages.size=64000;
            mk61_service_buffer cache{};cache.size=6144;
            if(!s.call(MK61_BUFFER_ACQUIRE,pages) || !s.call(MK61_BUFFER_ACQUIRE,cache) ||
               cache.data!=pages.data+64000) return 25;
        }
        std::free(pool);std::free(entries);std::free(pcm);std::free(image);
    }
    std::free(name3);std::free(name2);std::free(name1);std::free(catalog);
    if(mallinfo().uordblks!=empty || !shared_memory::validate_buffer_invariants()) return 26;
    for(unsigned cycle=0;cycle<8;++cycle) {
        void* image=std::calloc(1,31856+7);void* pcm=std::malloc(2064);
        if(!image || !pcm) return 1;
        {
            Session s;mk61_service_buffer r{};r.size=70144;
            if(!s.call(MK61_BUFFER_RESERVE,r)) return 2;
            mk61_service_buffer page{};page.size=64000;
            if(!s.call(MK61_BUFFER_ACQUIRE,page)) return 3;
            void* transient=std::malloc(512);
            mk61_service_buffer cache{};cache.size=6144;
            if(!transient || !s.call(MK61_BUFFER_ACQUIRE,cache) || cache.data!=page.data+64000) return 4;
            std::free(transient);
            if(!shared_memory::validate_buffer_invariants()) return 5;
            // Destructor must close this live window before releasing slices.
            cache.offset=0;cache.size=32;cache.flags=MK61_BUFFER_WINDOW_WRITABLE;
            if(!s.call(MK61_BUFFER_WINDOW_OPEN,cache)) return 6;
        }
        std::free(pcm);std::free(image);
        const auto buffers=shared_memory::buffer_statistics();
        if(buffers.active || buffers.pinned || !shared_memory::validate_buffer_invariants() ||
           mallinfo().uordblks!=empty) return 7;
    }
    void* image=std::malloc(31856);void* pcm=std::malloc(2064);
    void* small=std::malloc(5000);void* a=std::malloc(256);
    void* big=std::malloc(66000);void* b=std::malloc(256);
    if(!image || !pcm || !small || !a || !big || !b) return 8;
    std::free(small);std::free(big);
    {
        Session s;mk61_service_buffer reserve{};reserve.size=70144;
        if(s.call(MK61_BUFFER_RESERVE,reserve)) return 9;
        mk61_service_buffer page{};page.size=64000;
        if(!s.call(MK61_BUFFER_ACQUIRE,page)) return 10;
        mk61_service_buffer cache{};cache.size=6144;
        if(s.call(MK61_BUFFER_ACQUIRE,cache)) return 11;
        mk61_service_buffer head{};head.size=4096;
        mk61_service_buffer tail{};tail.size=2048;
        if(!s.call(MK61_BUFFER_ACQUIRE,head) || !s.call(MK61_BUFFER_ACQUIRE,tail)) return 12;
        if(!shared_memory::validate_buffer_invariants()) return 13;
    }
    std::free(b);std::free(a);std::free(pcm);std::free(image);
    if(shared_memory::buffer_statistics().active || mallinfo().uordblks!=empty) return 14;
    return 0;
}

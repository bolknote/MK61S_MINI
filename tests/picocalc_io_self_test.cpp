#include "io_queue.hpp"
#include <cassert>
#include <cstdint>
#include <cstdio>
#include <thread>

void picocalc_io_test() {
    picocalc::IoQueue<uint32_t,4> small;
    uint32_t value=17;
    assert(!small.pop(value) && value==17 && small.empty());
    assert(small.push(1) && small.push(2) && small.push(3));
    assert(!small.push(4));
    assert(small.pop(value) && value==1 && small.push(4));
    for(uint32_t i=2;i<=4;++i) assert(small.pop(value) && value==i);
    assert(small.empty() && !small.pop(value));
    // Concurrent pressure wraps indices many times and checks every byte of
    // the ordered stream. Full queues must apply backpressure without loss.
    picocalc::IoQueue<uint32_t,127> queue;
    constexpr uint32_t count=250000;
    std::thread producer([&] {
        for(uint32_t i=0;i<count;++i)
            while(!queue.push(i^0xF36C7A15U)) std::this_thread::yield();
    });
    for(uint32_t i=0;i<count;++i) {
        while(!queue.pop(value)) std::this_thread::yield();
        assert(value==(i^0xF36C7A15U));
    }
    producer.join();assert(queue.empty());
    std::puts("PicoCalc core 1 I/O queue: ordering, wrap, full/empty and concurrent backpressure PASS");
}

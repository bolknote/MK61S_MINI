#include "io_queue.hpp"
#include "console.hpp"
#include <cassert>
#include <cstdint>
#include <cstdio>
#include <thread>
#if defined(_WIN32)
#include <io.h>
#else
#include <unistd.h>
#endif

namespace {
void console_text_test() {
#if defined(_WIN32)
    const auto descriptor=&_fileno;const auto duplicate=&_dup;
    const auto redirect=&_dup2;const auto close_fd=&_close;
#else
    const auto descriptor=&fileno;const auto duplicate=&dup;
    const auto redirect=&dup2;const auto close_fd=&close;
#endif
    std::fflush(stdout);
    auto* capture=std::tmpfile();assert(capture);
    const int output=descriptor(stdout),saved=duplicate(output);assert(saved>=0);
    assert(redirect(descriptor(capture),output)>=0);
    const char text[]={'A',0,'B'};
    picocalc::console::write(nullptr,0);
    picocalc::console::write(text,sizeof(text));
    picocalc::console::write("%d\n",3);
    std::fflush(stdout);
    assert(redirect(saved,output)>=0);close_fd(saved);
    std::rewind(capture);char bytes[8]{};
    const auto count=std::fread(bytes,1,sizeof(bytes),capture);std::fclose(capture);
    assert(count==4 && std::memcmp(bytes,"A%d\n",4)==0);
}
}

void picocalc_io_test() {
    console_text_test();
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

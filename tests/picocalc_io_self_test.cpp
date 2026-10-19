#include "io_queue.hpp"
#include "console.hpp"
#include "lcd_update.hpp"
#include <cassert>
#include <cstdint>
#include <cstdio>
#include <thread>
#include <array>
#if defined(_WIN32)
#include <io.h>
#else
#include <unistd.h>
#endif

namespace {
void lcd_updates_test() {
    using namespace picocalc::lcd;
    std::array<uint8_t,BYTES> previous{},next{},recovered{};
    Update update;
    auto verify=[&](bool force=false) {
        update.plan(previous.data(),next.data(),force);
        recovered=previous;
        unsigned bytes=0;
        uint8_t line[WIDTH*2]{};
        assert(update.count<=Update::CAPACITY);
        for(unsigned i=0;i<update.count;++i) {
            const auto& rect=update.rectangles[i];
            assert(rect.width && rect.height && rect.x+rect.width<=WIDTH && rect.y+rect.height<=HEIGHT);
            assert(!(rect.x%8) && !(rect.y%8) && !(rect.width%8) && !(rect.height%8));
            bytes+=rect.width*rect.height*2;
            for(unsigned y=0;y<rect.height;++y) {
                scanline(next.data(),rect,y,line);
                for(unsigned x=0;x<rect.width;++x) {
                    const unsigned px=rect.x+x,py=rect.y+y;
                    const bool lit=next[py*STRIDE+px/8] & (0x80U>>(px%8));
                    assert(line[x*2]==(lit?255:0) && line[x*2+1]==line[x*2]);
                    const uint8_t mask=0x80U>>(px%8);
                    auto& target=recovered[py*STRIDE+px/8];
                    target=line[x*2] ? target|mask : target&~mask;
                }
            }
        }
        assert(bytes==update.bytes && recovered==next);
    };
    verify();assert(!update.count && !update.bytes);
    verify(true);assert(update.count==1 && update.bytes==204800);
    next[0]=0x80;next.back()=1;
    verify();assert(update.count==2 && update.bytes==256);
    previous=next;verify();assert(!update.count);
    next.fill(0);previous.fill(0);
    for(unsigned y=8;y<32;++y) { next[y*STRIDE+2]=255;next[y*STRIDE+3]=255; }
    verify();assert(update.count==1 && update.bytes==16*24*2);
    // Exhaust the rectangle budget with sparse changes, then qualify arbitrary
    // sparse/dense frames against an independent pixel reconstruction oracle.
    for(unsigned y=0;y<HEIGHT;y+=16) for(unsigned x=0;x<STRIDE;x+=2) next[y*STRIDE+x]^=1;
    verify();assert(update.count==1 && update.bytes==204800);
    uint32_t random=0x691C53AD;
    auto word=[&] { random^=random<<13;random^=random>>17;return random^=random<<5; };
    for(unsigned frame=0;frame<160;++frame) {
        previous=next;
        const unsigned changes=frame%3?4:BYTES;
        for(unsigned i=0;i<changes;++i) next[word()%BYTES]^=(uint8_t)word();
        verify();
    }
    std::puts("PicoCalc LCD windows: exact pixel reconstruction, sparse regions, edges, merging, fragmentation and RGB565 PASS");
}
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
    lcd_updates_test();
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

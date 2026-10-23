#include "io_queue.hpp"
#include "console.hpp"
#include "lcd_update.hpp"
#include "battery.hpp"
#include "lcd_scroll.hpp"
#include <deque>
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
    verify();assert(update.bytes<204800);
    // Many dense windows save a few pixels but lose to one full SPI window
    // on hardware. Keep that transfer-cost regression distinct from sparse
    // fragmentation, which must still retain partial updates.
    previous.fill(0);next.fill(0);
    for(unsigned y=0;y<HEIGHT;++y) for(unsigned x=0;x<WIDTH;++x)
        if((x/16+y/16)&1) next[y*STRIDE+x/8]|=0x80U>>(x%8);
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
void lcd_scroll_test() {
    using namespace picocalc::lcd;
    uint32_t random=0x8F1DC039;
    auto byte=[&]() -> uint8_t { random^=random<<13;random^=random>>17;random^=random<<5;return (uint8_t)random; };
    for(Region region:{Region{0,320},Region{40,240},Region{42,238}}) {
        std::array<uint8_t,BYTES> previous{},next{},ram{},visible{};
        for(auto& value:previous) value=byte();
        ram=previous;Scroll mapping{region,0};
        for(unsigned step=0;step<100;++step) {
            const int delta=step%2?-(int)(1+step%47):(int)(1+step%61);
            next=previous;
            for(unsigned y=0;y<region.height;++y) {
                const int source=(int)y+delta;
                for(unsigned x=0;x<STRIDE;++x)
                    next[(region.top+y)*STRIDE+x]=source>=0 && source<region.height?previous[(region.top+source)*STRIDE+x]:byte();
            }
            // Also change fixed title/footer pixels. They must remain fixed.
            if(region.top) next[1]^=1;
            if(region.top+region.height<HEIGHT) next.back()^=1;
            assert(Scroll::find(previous.data(),next.data(),region)==delta);
            mapping.rotate(previous.data(),delta);
            Update update;update.plan(previous.data(),next.data());
            assert(update.bytes<WIDTH*HEIGHT*2);
            for(unsigned i=0;i<update.count;++i) {
                const auto& rect=update.rectangles[i];
                for(unsigned row=0;row<rect.height;) {
                    const unsigned y=rect.y+row,n=mapping.run(y,rect.height-row),physical=mapping.map(y);
                    assert(n && physical+n<=HEIGHT);
                    for(unsigned dy=0;dy<n;++dy)
                        std::memcpy(ram.data()+(physical+dy)*STRIDE+rect.x/8,next.data()+(y+dy)*STRIDE+rect.x/8,rect.width/8);
                    row+=n;
                }
            }
            for(unsigned y=0;y<HEIGHT;++y) std::memcpy(visible.data()+y*STRIDE,ram.data()+mapping.map(y)*STRIDE,STRIDE);
            assert(visible==next);previous=next;
            assert(!Scroll::find(previous.data(),next.data(),region));
        }
    }
    assert(!Scroll::find(nullptr,nullptr,{319,2}));
    std::puts("LCD scroll: 300 exact physical-GRAM reconstructions, both directions, wrapping, unaligned fixed areas and changed headers PASS");
}
void console_route_test() {
    using namespace picocalc::console;
    struct Backend {
        std::deque<int> usb,uart;
        int read(Channel channel) {
            auto& queue=channel==Channel::USB?usb:uart;
            if(queue.empty()) return -1;
            const int value=queue.front();queue.pop_front();return value;
        }
    } backend;
    Route route;assert(route.uart_output_enabled());backend.usb={'a','b','\r'};backend.uart={'x','y','\r'};
    assert(route.read(backend,false)=='a' && route.accept('a',false));
    assert(route.output()==Channel::USB && !route.uart_output_enabled());
    assert(!route.skip_lf('\r'));
    assert(route.read(backend,true)=='b' && route.accept('b',true));
    assert(route.read(backend,true)=='\r' && route.accept('\r',true));
    assert(route.read(backend,true)<0 && backend.uart.size()==3);
    assert(route.read(backend,false)=='x' && route.accept('x',false));
    assert(route.output()==Channel::UART && route.uart_output_enabled());
    assert(!route.skip_lf('\n'));
    // A USB packet can be consumed without changing the running UART shell.
    backend.uart.clear();backend.usb={0,7};
    assert(route.read(backend,true)==0);assert(route.output()==Channel::UART && route.uart_output_enabled());
    assert(route.read(backend,true)==7);assert(route.output()==Channel::UART && route.uart_output_enabled());
    backend.usb={'z'};
    assert(route.read(backend,true)=='z' && !route.accept('z',true));
    backend.uart={'y','\r'};
    assert(route.read(backend,true)=='y' && route.accept('y',true));
    assert(route.read(backend,true)=='\r' && route.accept('\r',true));
    assert(route.read(backend,true)<0);
    assert(route.read(backend,false)=='z' && route.accept('z',false));
    assert(route.output()==Channel::USB && route.received(Channel::USB)==6 && route.received(Channel::UART)==3);
    assert(route.skip_lf('\n'));
    assert(!route.skip_lf('\n'));
    assert(route.switches()==3 && route.read(backend,false)<0);
    std::puts("Pico console routing: exact streams, partial-line ownership, USB packets, UART deferred and no byte loss PASS");
}
void battery_test() {
    picocalc::BatteryStatus lost;
    assert(lost.decode(0x0B,0x80|75) && lost.bios_flag7);
    lost.clear_reading();
    assert(lost.available && lost.percent==-1 && !lost.bios_flag7);
    picocalc::BatteryStatus status;
    assert(!status.available);
    for(unsigned raw=0;raw<256;++raw) {
        const bool valid=status.decode(0x0B,(uint8_t)raw);
        assert(valid==((raw&127)<=100));
        if(valid) assert(status.percent==(int)(raw&127) && status.bios_flag7==((raw&128)!=0) && status.available);
        else assert(status.percent<0 && !status.bios_flag7);
    }
    assert(!status.decode(0,45));
    for(int charge:{0,1}) for(int value:{-1,0,1,49,100}) {
        status={(int16_t)value,charge!=0,true};
        unsigned pixels=0;
        picocalc::battery_icon(status,[&](unsigned x,unsigned y) {
            assert(x>=290 && x<312 && y>=11 && y<=22);++pixels;
        });
        assert(pixels>=68 && pixels<=240);
    }
    std::array<bool,320*320> plain{},flagged{};
    status={75,false,true};
    picocalc::battery_icon(status,[&](unsigned x,unsigned y){plain[y*320+x]=true;});
    status.bios_flag7=true;
    picocalc::battery_icon(status,[&](unsigned x,unsigned y){flagged[y*320+x]=true;});
    assert(plain==flagged); // Raw BIOS flag cannot imply charging in the HUD.
    std::puts("Pico battery: register/percent/raw BIOS flag validation and native bounded icon PASS");
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
    lcd_scroll_test();
    console_text_test();
    console_route_test();
    battery_test();
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

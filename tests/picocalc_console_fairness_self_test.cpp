#include "console_route.hpp"
#include "usb_screen.hpp"
#include "clock.hpp"
#include <cassert>
#include <cstdio>
#include <vector>
// CLOCK_SYNC and scan-code paths are unused; exercise the actual console
// router, UsbScreen::receive, encoder and multiplex parsers below.
namespace picocalc::clock {
bool configured() { return false; }
bool set(const DateTime&) { assert(false);return false; }
DateTime get() { return {}; }
}
namespace picocalc::controls { u8 from_scan(unsigned) { return 0; } }
int main() {
    using namespace picocalc;
    using namespace console;
    using namespace usb_screen_protocol;
    for(bool flood:{false,true}) {
        struct Backend {
            std::vector<u8> usb;
            unsigned at=0,uart_left=1;
            bool usb_on=false,uart_flood=false;
            int read(Channel source) {
                if(source==Channel::USB) return usb_on?usb[at++%usb.size()]:-1;
                if(uart_flood) return 0x1B;
                if(!uart_left) return -1;
                --uart_left;return 0x1B;
            }
        } backend;
        Route route;
        const int initial=route.read(backend,false);
        assert(initial==0x1B && route.accept(initial,false) && route.output()==Channel::UART);
        UsbScreen screen;PacketEncoder encoder;
        auto feed=[&](MessageType type) {
            assert(encoder.encode(type,0,0,nullptr,0)==Status::OK);
            for(unsigned i=0;i<encoder.size();++i) assert(screen.receive(encoder.data()[i],1)<0);
        };
        feed(MessageType::ACTIVATE);feed(MessageType::ATTACH);
        assert(screen.enabled() && screen.attached());
        const u8 ping[]={0x34,0x12};
        assert(encoder.encode(MessageType::PING,0,0,ping,sizeof(ping))==Status::OK);
        backend.usb.assign(encoder.data(),encoder.data()+encoder.size());
        backend.usb_on=true;backend.uart_left=1;backend.uart_flood=flood;
        unsigned usb_bytes=0,uart_bytes=0,pings=0,first_uart=0,first_usb=0,reads=0;
        MultiplexParser observed;
        while(usb_bytes<4096 || (flood && uart_bytes<4096)) {
            assert(++reads<=8192);
            int byte=route.read(backend,true);assert(byte>=0);
            if(route.input()==Channel::USB) {
                if(!first_usb) first_usb=reads;
                ++usb_bytes;
                const auto parsed=observed.push((u8)byte);
                assert(parsed!=MultiplexPushResult::ERROR && parsed!=MultiplexPushResult::TERMINAL_BYTE);
                if(parsed==MultiplexPushResult::PACKET) {
                    assert(observed.packet().type==MessageType::PING);++pings;
                }
                assert(screen.receive((u8)byte,reads+1)<0);
            } else {
                if(!first_uart) first_uart=reads;
                ++uart_bytes;assert(byte==0x1B && route.accept(byte,true));
            }
            assert(route.output()==Channel::UART);
        }
        assert(first_uart<=2 && first_usb<=2 && screen.errors()==0 && pings>100);
        assert(uart_bytes==(flood?4096:1));
        std::printf("Console fairness: USB=%u UART=%u complete_PING=%u owner_ESC_within=%u reads parser_errors=0 PASS\n",
                    usb_bytes,uart_bytes,pings,first_uart);
    }
}

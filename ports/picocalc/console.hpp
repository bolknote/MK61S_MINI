#ifndef MK61_PICOCALC_CONSOLE_HPP
#define MK61_PICOCALC_CONSOLE_HPP
#include <cstring>
#include "console_route.hpp"
#if defined(PICO_ON_DEVICE)
#include "pico/stdio.h"
#include "pico/stdio/driver.h"
#include "pico/stdio_uart.h"
#include "pico/stdio_usb.h"
#else
#include <cstdio>
#endif

namespace picocalc::console {
#if defined(PICO_ON_DEVICE)
inline int read(bool exclusive=false,bool usb_available=true) {
    struct Backend {
        bool usb_available;
        int read(Channel channel) {
            if(channel==Channel::USB && !usb_available) return -1;
            auto& driver=channel==Channel::USB?stdio_usb:stdio_uart;
            char byte;
            return driver.in_chars && driver.in_chars(&byte,1)==1?(unsigned char)byte:-1;
        }
    } backend{usb_available};
    return routing.read(backend,exclusive);
}
inline bool input_usb() { return routing.input()==Channel::USB; }
inline bool accept(int byte,bool exclusive=false) {
    if(!routing.accept(byte,exclusive)) return false;
    stdio_filter_driver(routing.output()==Channel::USB?&stdio_usb:&stdio_uart);
    return true;
}
#endif
// Pico SDK printf flushes every driver after each call. Stream program text
// through the selected transport with the SDK CRLF policy.
// Its bounded worker queue still applies backpressure; explicit flush/drain
// retains its blocking contract before clock changes, sleep and reset.
inline void write(const char* bytes,unsigned count) {
    if(!count) return;
    // Match the previous printf("%.*s") text contract. In particular, an
    // embedded NUL must not become a USB Screen packet delimiter.
    if(const auto end=(const char*)std::memchr(bytes,0,count)) count=(unsigned)(end-bytes);
    if(!count) return;
#if defined(PICO_ON_DEVICE)
    stdio_put_string(bytes,(int)count,false,true);
#else
    (void)std::fwrite(bytes,1,count,stdout);
#endif
}
}
#endif

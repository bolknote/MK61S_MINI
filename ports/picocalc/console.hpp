#ifndef MK61_PICOCALC_CONSOLE_HPP
#define MK61_PICOCALC_CONSOLE_HPP
#include <cstring>
#if defined(PICO_ON_DEVICE)
#include "pico/stdio.h"
#else
#include <cstdio>
#endif

namespace picocalc::console {
// Pico SDK printf flushes every driver after each call. Stream program text
// through the same drivers/CRLF policy without draining UART for each fragment.
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

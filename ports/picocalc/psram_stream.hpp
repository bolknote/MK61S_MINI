#ifndef MK61_PICOCALC_PSRAM_STREAM_HPP
#define MK61_PICOCALC_PSRAM_STREAM_HPP
#include "rust_types.h"
namespace picocalc::psram {
// The writer's high-CE# idle loop has TWO instructions. Polling just one
// address can alias their nine-cycle loop forever. Neither instruction can
// start another packet when TX is empty; the reader instead stalls on PULL.
constexpr bool stream_idle(unsigned ready,unsigned pc,bool writing,bool tx_empty,bool ce_high) {
    return tx_empty && ce_high && (pc==ready || (writing && pc==ready+1));
}

constexpr unsigned READ_BLOCK=16,READ_PACKETS=128;

// All spans are aligned to READ_BLOCK. Keep long reads inside each 1 KiB
// page and use smaller packets to end a span without reading extra bytes.
inline unsigned read_commands(u32* out,u32 address,unsigned bytes,unsigned maximum) {
    const auto* start=out;
    if(maximum==READ_BLOCK) {
        for(unsigned at=0;at<bytes;at+=READ_BLOCK) *out++=0xEB000000U|(address+at);
    } else {
        while(bytes) {
            const unsigned page=1024-(address&1023);
            const unsigned room=bytes<page?bytes:page;
            const unsigned n=maximum==64 && room>=64?64:room>=32?32:READ_BLOCK;
            *out++=((2*n-1)<<24)|address;
            address+=n;bytes-=n;
        }
    }
    return unsigned(out-start);
}

// Expand backwards so a failed burst can be retried in the same command array.
inline unsigned short_read_commands(u32* commands,unsigned packets,unsigned bytes) {
    const unsigned count=bytes/READ_BLOCK;
    unsigned end=count;
    while(packets) {
        const unsigned command=commands[--packets];
        const unsigned n=((command>>24)+1)/(2*READ_BLOCK);
        end-=n;
        read_commands(commands+end,command&0xFFFFFFU,n*READ_BLOCK,READ_BLOCK);
    }
    return count;
}
}
#endif

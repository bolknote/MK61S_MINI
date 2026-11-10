#ifndef MK61_PICOCALC_M3_TX_HPP
#define MK61_PICOCALC_M3_TX_HPP
#include <cstdint>
namespace picocalc::m3 {
// One immutable encoded frame. DMA completion releases its memory; a reply
// or timeout closes the request. FIFO fallback preserves the same byte order.
struct Transmit {
    const uint8_t* source=nullptr;
    unsigned bytes=0,offset=0;
    uint16_t sequence=0;
    bool active=false,dma=false;
    uint32_t dma_requests=0,fifo_requests=0;
    bool queued()const{return active && offset==bytes;}
    template<class Port> bool pump(Port& port,const uint8_t* data,unsigned count,uint16_t tag) {
        if(!active) {
            if(!count)return false;
            source=data;bytes=count;offset=0;sequence=tag;active=true;dma=port.dma_available();
            if(dma){port.start(data,count);offset=count;++dma_requests;return true;}
            ++fifo_requests;
        }
        if(source!=data || bytes!=count || sequence!=tag)return false;
        if(!dma)while(offset<bytes && port.writable())port.write(source[offset++]);
        return true;
    }
    template<class Port> void cancel(Port& port) {
        if(active && dma)port.abort();
        source=nullptr;bytes=offset=0;active=dma=false;
    }
    template<class Port> bool complete(Port& port) {
        if(!active)return true;
        const bool ok=offset==bytes && (!dma || !port.busy());
        cancel(port);return ok;
    }
};
}
#endif

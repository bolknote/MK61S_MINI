#ifndef MK61_PICOCALC_SD_MULTI_WRITE_HPP
#define MK61_PICOCALC_SD_MULTI_WRITE_HPP
#include <cstdint>
namespace picocalc::sd {
enum class MultiWriteResult { OK, UNSUPPORTED, ERROR, INCOMPLETE };
// A partial DMA block has no known token boundary: never send a stop token
// into its payload or silently retry it. The caller takes the card offline.
// Complete rejected blocks are stopped normally so journal replay can run.
template<class Bus>
MultiWriteResult multi_write(Bus& bus,uint32_t address,const uint8_t* data,uint32_t count) {
    const auto response=bus.command(25,address);
    if(response!=0) {
        bus.deselect();
        return response==4?MultiWriteResult::UNSUPPORTED:MultiWriteResult::ERROR;
    }
    bool ok=true;
    for(uint32_t i=0;i<count;++i) {
        bus.byte(0xFF);bus.byte(0xFC);
        uint16_t crc=0;
        if(!bus.data(data+i*512,crc)) { bus.deselect();return MultiWriteResult::INCOMPLETE; }
        bus.byte((uint8_t)(crc>>8));bus.byte((uint8_t)crc);
        const auto token=bus.byte(0xFF);
        ok=(token&0x1F)==5;
        bus.byte(0xFF); // Allow the data-response-to-busy turnaround.
        if(!bus.wait()) { bus.deselect();return MultiWriteResult::INCOMPLETE; }
        if(!ok) break;
    }
    bus.byte(0xFD);
    bus.byte(0xFF); // Clock the stop-token turnaround before testing busy.
    const bool stopped=bus.wait();
    bus.deselect();
    return !stopped?MultiWriteResult::INCOMPLETE:ok?MultiWriteResult::OK:MultiWriteResult::ERROR;
}
}
#endif

#ifndef MK61_PICOCALC_PSRAM_STREAM_HPP
#define MK61_PICOCALC_PSRAM_STREAM_HPP
namespace picocalc::psram {
// The writer's high-CE# idle loop has TWO instructions. Polling just one
// address can alias their nine-cycle loop forever. Neither instruction can
// start another packet when TX is empty; the reader instead stalls on PULL.
constexpr bool stream_idle(unsigned ready,unsigned pc,bool writing,bool tx_empty,bool ce_high) {
    return tx_empty && ce_high && (pc==ready || (writing && pc==ready+1));
}
}
#endif

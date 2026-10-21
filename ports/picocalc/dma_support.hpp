#ifndef MK61_PICOCALC_DMA_SUPPORT_HPP
#define MK61_PICOCALC_DMA_SUPPORT_HPP
#include "rust_types.h"
namespace picocalc::dma_support {
struct Statistics { u32 waits[2],sleep_us[2],timeouts,crc32_calls,crc_fallbacks; };
// Call on the channel's owning core before starting a transfer. Completion
// IRQs send an event, so a completed transfer cannot race the following WFE.
void enable_irq(unsigned channel);
bool wait(unsigned first,int second=-1);
bool begin_crc(unsigned channel,bool crc32);
u32 end_crc();
u32 crc32(const u8* bytes,unsigned count);
Statistics statistics();
}
#endif

#include "dma_support.hpp"
#include "crc32.hpp"
#if defined(PICO_ON_DEVICE)
#include "hardware/dma.h"
#include "hardware/irq.h"
#include "pico/mutex.h"
#include "pico/stdlib.h"
#include <atomic>
namespace picocalc::dma_support {
namespace {
auto_init_mutex(crc_mutex);
std::atomic<u32> masks[2]{},waits[2]{},sleep_us[2]{},timeouts{0},crc_calls{0},fallbacks{0};
bool installed[2]{};
int crc_channel[2]{-1,-1};
void irq0() { const u32 bits=dma_hw->ints0 & masks[0].load();dma_hw->ints0=bits;__sev(); }
void irq1() { const u32 bits=dma_hw->ints1 & masks[1].load();dma_hw->ints1=bits;__sev(); }
}
void enable_irq(unsigned channel) {
    const unsigned core=get_core_num(),irq=core?DMA_IRQ_1:DMA_IRQ_0;
    if(!installed[core]) {
        irq_add_shared_handler(irq,core?irq1:irq0,PICO_SHARED_IRQ_HANDLER_DEFAULT_ORDER_PRIORITY);
        irq_set_enabled(irq,true);installed[core]=true;
    }
    masks[core].fetch_or(1U<<channel);
    if(core) dma_channel_set_irq1_enabled(channel,true);
    else dma_channel_set_irq0_enabled(channel,true);
}
bool wait(unsigned first,int second) {
    const unsigned core=get_core_num();
    const u64 started=time_us_64(),limit=started+1000000;
    waits[core].fetch_add(1,std::memory_order_relaxed);
    while(dma_channel_is_busy(first) || (second>=0 && dma_channel_is_busy((unsigned)second))) {
        if(time_us_64()>=limit) {
            dma_channel_abort(first);if(second>=0) dma_channel_abort((unsigned)second);
            timeouts.fetch_add(1,std::memory_order_relaxed);return false;
        }
        // The SDK alarm-pool timer also bounds the wait if a peripheral stops
        // producing DREQs. Completion itself is interrupt/event driven.
        best_effort_wfe_or_timeout(make_timeout_time_us(1000));
    }
    sleep_us[core].fetch_add((u32)(time_us_64()-started),std::memory_order_relaxed);
    return true;
}
bool begin_crc(unsigned channel,bool crc32) {
    if(!mutex_try_enter(&crc_mutex,nullptr)) { fallbacks.fetch_add(1);return false; }
    dma_sniffer_disable();
    dma_sniffer_set_byte_swap_enabled(false);
    dma_sniffer_set_output_reverse_enabled(crc32);
    dma_sniffer_set_output_invert_enabled(crc32);
    dma_sniffer_set_data_accumulator(crc32?0xFFFFFFFFU:0);
    dma_sniffer_enable(channel,crc32?DMA_SNIFF_CTRL_CALC_VALUE_CRC32R:DMA_SNIFF_CTRL_CALC_VALUE_CRC16,true);
    return true;
}
u32 end_crc() {
    const u32 result=dma_sniffer_get_data_accumulator();
    dma_sniffer_disable();mutex_exit(&crc_mutex);return result;
}
u32 crc32(const u8* bytes,unsigned count) {
    if(!count) return 0;
    const unsigned core=get_core_num();
    int& channel=crc_channel[core];
    if(channel<0) {
        channel=dma_claim_unused_channel(false);
        if(channel>=0) enable_irq((unsigned)channel);
    }
    if(channel<0 || !begin_crc((unsigned)channel,true)) return mk61_crc32::calculate(bytes,count);
    u8 discard=0;
    auto config=dma_channel_get_default_config((unsigned)channel);
    channel_config_set_transfer_data_size(&config,DMA_SIZE_8);
    channel_config_set_read_increment(&config,true);
    channel_config_set_write_increment(&config,false);
    channel_config_set_sniff_enable(&config,true);
    dma_channel_configure((unsigned)channel,&config,&discard,bytes,count,true);
    const bool ok=wait((unsigned)channel);
    const u32 result=end_crc();
    if(!ok) return mk61_crc32::calculate(bytes,count);
    crc_calls.fetch_add(1,std::memory_order_relaxed);return result;
}
Statistics statistics() {
    return {{waits[0].load(),waits[1].load()},{sleep_us[0].load(),sleep_us[1].load()},
        timeouts.load(),crc_calls.load(),fallbacks.load()};
}
}
#else
namespace picocalc::dma_support {
void enable_irq(unsigned) {}
bool wait(unsigned,int) { return true; }
bool begin_crc(unsigned,bool) { return false; }
u32 end_crc() { return 0; }
u32 crc32(const u8* bytes,unsigned count) { return mk61_crc32::calculate(bytes,count); }
Statistics statistics() { return {}; }
}
#endif

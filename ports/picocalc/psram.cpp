#include "psram.hpp"
#include "dma_support.hpp"
#include "diagnostics.hpp"
#include <cstring>
#if defined(PICO_ON_DEVICE)
#include "psram_spi.pio.h"
#include "hardware/dma.h"
#include "hardware/clocks.h"
#include "hardware/pio.h"
#include "pico/mutex.h"
#include "pico/stdlib.h"
#endif
namespace picocalc::psram {
namespace {
Statistics state{};
#if defined(PICO_ON_DEVICE)
constexpr unsigned CS=20,SCK=21,MOSI=2,MISO=3;
PIO bus=pio1;
int sm=-1,tx=-1,rx=-1;
unsigned program_offset=0;
auto_init_mutex(bus_mutex);
bool exchange(const u8* prefix,unsigned prefix_count,const u8* source,u8* target,unsigned count) {
    const unsigned total=prefix_count+count;
    if(!total || total>16 || clock_get_hz(clk_sys)<100000000) return false;
    u32 sent[4]{},received[5]{};
    for(unsigned i=0;i<total;++i) {
        const u8 byte=i<prefix_count?prefix[i]:source?source[i-prefix_count]:0xFF;
        sent[i/4]|=u32(byte)<<(24-8*(i%4));
    }
    pio_sm_set_enabled(bus,(unsigned)sm,false);
    pio_sm_restart(bus,(unsigned)sm);pio_sm_clear_fifos(bus,(unsigned)sm);
    pio_sm_exec(bus,(unsigned)sm,pio_encode_nop()|pio_encode_sideset(2,1));
    pio_sm_put(bus,(unsigned)sm,total*8-1);
    pio_sm_exec(bus,(unsigned)sm,pio_encode_pull(false,true)|pio_encode_sideset(2,1));
    // Preload the entire packet into the four-word TX FIFO while CE# is
    // high. Neither a DMA stall nor a CPU interrupt can stretch CE# low.
    dma_channel_set_read_addr((unsigned)tx,sent,false);
    dma_channel_set_trans_count((unsigned)tx,(total+3)/4,true);
    if(!dma_support::wait((unsigned)tx)) return false;
    pio_sm_exec(bus,(unsigned)sm,pio_encode_out(pio_x,32)|pio_encode_sideset(2,1));
    pio_sm_exec(bus,(unsigned)sm,pio_encode_jmp(program_offset)|pio_encode_sideset(2,1));
    dma_channel_set_write_addr((unsigned)rx,received,false);
    dma_channel_set_trans_count((unsigned)rx,total/4+1,true);
    pio_sm_set_enabled(bus,(unsigned)sm,true);
    const bool ok=dma_support::wait((unsigned)rx);
    pio_sm_set_enabled(bus,(unsigned)sm,false);
    if(!ok) {
        pio_sm_restart(bus,(unsigned)sm);
        pio_sm_exec(bus,(unsigned)sm,pio_encode_nop()|pio_encode_sideset(2,1));
        return false;
    }
    if(target) for(unsigned i=0;i<count;++i) {
        const unsigned at=prefix_count+i,word=at/4;
        const unsigned bits=word<total/4?32:(total%4)*8;
        target[i]=(u8)(received[word]>>(bits-8-8*(at%4)));
    }
    return true;
}
bool command(const u8* data,unsigned count) {
    return exchange(data,count,nullptr,nullptr,0);
}
bool access(u32 address,void* data,unsigned count,bool writing) {
    // Page boundaries and the 8 us CE# limit both apply. Complete packets
    // fit the preloaded PIO FIFO; CE# is released by PIO, never by the CPU.
    u8* bytes=(u8*)data;
    while(count) {
        const unsigned maximum=writing?12:11;
        unsigned n=count<maximum?count:maximum;
        if(n>1024-(address&1023)) n=1024-(address&1023);
        u8 header[]={(u8)(writing?0x02:0x0B),(u8)(address>>16),(u8)(address>>8),(u8)address,0};
        const bool ok=exchange(header,writing?4:5,writing?bytes:nullptr,writing?nullptr:bytes,n);
        if(!ok) return false;
        bytes+=n;address+=n;count-=n;
    }
    return true;
}
#else
u8* memory=nullptr;
unsigned memory_size=0;
#endif
bool bounds(u32 address,const void* bytes,unsigned count) {
    return state.ready && (bytes || !count) && address<=CAPACITY && count<=CAPACITY-address;
}
}
bool ready() { return state.ready; }
bool init() {
    state={};
#if defined(PICO_ON_DEVICE)
    if(sm<0) {
        if(!pio_can_add_program(bus,&mk61_psram_spi_program)) return false;
        sm=pio_claim_unused_sm(bus,false);if(sm<0) return false;
        tx=dma_claim_unused_channel(false);rx=dma_claim_unused_channel(false);
        if(tx<0 || rx<0) {
            if(tx>=0) dma_channel_unclaim((unsigned)tx);
            if(rx>=0) dma_channel_unclaim((unsigned)rx);
            pio_sm_unclaim(bus,(unsigned)sm);sm=tx=rx=-1;return false;
        }
        dma_support::enable_irq((unsigned)tx);dma_support::enable_irq((unsigned)rx);
        program_offset=pio_add_program(bus,&mk61_psram_spi_program);
        auto config=mk61_psram_spi_program_get_default_config(program_offset);
        sm_config_set_out_pins(&config,MOSI,1);sm_config_set_in_pins(&config,MISO);
        sm_config_set_sideset_pins(&config,CS);
        sm_config_set_out_shift(&config,false,true,32);
        sm_config_set_in_shift(&config,false,true,32);
        sm_config_set_clkdiv(&config,1);
        const unsigned pins[]={CS,SCK,MOSI,MISO};
        for(unsigned pin : pins) pio_gpio_init(bus,pin);
        pio_sm_set_consecutive_pindirs(bus,(unsigned)sm,CS,2,true);
        pio_sm_set_consecutive_pindirs(bus,(unsigned)sm,MOSI,1,true);
        pio_sm_set_consecutive_pindirs(bus,(unsigned)sm,MISO,1,false);
        pio_sm_init(bus,(unsigned)sm,program_offset,&config);
        pio_sm_exec(bus,(unsigned)sm,pio_encode_nop()|pio_encode_sideset(2,1));
        auto send=dma_channel_get_default_config((unsigned)tx);
        channel_config_set_transfer_data_size(&send,DMA_SIZE_32);
        channel_config_set_dreq(&send,pio_get_dreq(bus,(unsigned)sm,true));
        channel_config_set_read_increment(&send,true);channel_config_set_write_increment(&send,false);
        dma_channel_configure((unsigned)tx,&send,&bus->txf[sm],nullptr,0,false);
        auto receive=dma_channel_get_default_config((unsigned)rx);
        channel_config_set_transfer_data_size(&receive,DMA_SIZE_32);
        channel_config_set_dreq(&receive,pio_get_dreq(bus,(unsigned)sm,false));
        channel_config_set_read_increment(&receive,false);channel_config_set_write_increment(&receive,true);
        dma_channel_configure((unsigned)rx,&receive,nullptr,&bus->rxf[sm],0,false);
    }
    const u8 reset_enable=0x66,reset=0x99,id_command[]={0x9F,0,0,0};
    if(!command(&reset_enable,1) || !command(&reset,1)) return false;
    sleep_us(200);
    u8 id[8]{};
    const bool identified=exchange(id_command,sizeof(id_command),nullptr,id,sizeof(id));
    state.id=(u32(id[0])<<16)|(u32(id[1])<<8)|id[2];
    state.hz=clock_get_hz(clk_sys)/6;
    if(!identified || !id[0] || id[0]==0xFF || id[1]!=0x5D) return false;
    // Detect missing/address-aliased RAM before publishing a cache. Volatile
    // cache contents are ours; no SD or user file participates in this probe.
    u8 pattern[32],actual[32];
    state.ready=true;
    for(unsigned i=0;i<24;++i) {
        const u32 at=i<23?(1U<<i):CAPACITY-32;
        for(unsigned j=0;j<sizeof(pattern);++j) pattern[j]=(u8)(i*37+j*13);
        if(!access(at,pattern,sizeof(pattern),true)) { state.ready=false;break; }
    }
    for(unsigned i=0;state.ready && i<24;++i) {
        const u32 at=i<23?(1U<<i):CAPACITY-32;
        // Small powers overlap; only the non-overlapping address probes
        // above bit 5 are checked after all writes.
        if(i<5) continue;
        for(unsigned j=0;j<sizeof(pattern);++j) pattern[j]=(u8)(i*37+j*13);
        if(!access(at,actual,sizeof(actual),false) || std::memcmp(pattern,actual,sizeof(actual))) state.ready=false;
    }
#else
    state.ready=memory && memory_size>=CAPACITY;state.hz=31250000;state.id=0x0D5D00;
#endif
    return state.ready;
}
bool read(u32 address,void* bytes,unsigned count) {
    if(!bounds(address,bytes,count)) return false;
#if defined(PICO_ON_DEVICE)
    mutex_enter_blocking(&bus_mutex);
    const bool ok=access(address,bytes,count,false);
    mutex_exit(&bus_mutex);
#else
    const bool ok=true;if(count) std::memcpy(bytes,memory+address,count);
#endif
    if(ok) state.read_bytes+=count;else { ++state.errors;state.ready=false; }
    return ok;
}
bool write(u32 address,const void* bytes,unsigned count) {
    if(!bounds(address,bytes,count)) return false;
#if defined(PICO_ON_DEVICE)
    mutex_enter_blocking(&bus_mutex);
    const bool ok=access(address,const_cast<void*>(bytes),count,true);
    mutex_exit(&bus_mutex);
#else
    const bool ok=true;if(count) std::memcpy(memory+address,bytes,count);
#endif
    if(ok) state.write_bytes+=count;else { ++state.errors;state.ready=false; }
    return ok;
}
Statistics statistics() { return state; }
bool self_test(void (*service)()) {
    if(!ready()) return false;
    u8 expected[1024],actual[1024];
    auto pattern=[](u32 address) {
        u32 x=address*0x9E3779B9U+0x5049434FU;
        x^=x>>13;x*=0x85EBCA6BU;return (u8)(x^(x>>16));
    };
    // Write the entire device before checking any block, exposing address
    // aliases as well as stuck bits. This only destroys volatile caches.
    for(unsigned pass=0;pass<2;++pass)
        for(u32 at=0;at<CAPACITY;at+=sizeof(expected)) {
            for(unsigned i=0;i<sizeof(expected);++i) expected[i]=pattern(at+i);
            if(!pass) { if(!write(at,expected,sizeof(expected))) return false; }
            else if(!read(at,actual,sizeof(actual)) || std::memcmp(actual,expected,sizeof(actual))) {
                ++state.errors;state.ready=false;return false;
            }
            diagnostics::feed_watchdog();
            if(service && !(at&16383)) service();
        }
    return true;
}
#if !defined(PICO_ON_DEVICE)
void test_memory(u8* bytes,unsigned capacity) { memory=bytes;memory_size=capacity;state={}; }
#endif
}

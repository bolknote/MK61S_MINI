#include "psram.hpp"
#include "cosmic_clock.hpp"
#include "cosmic_clock_plan.hpp"
#include "ai_psram_read_clock.hpp"
#include "psram_stream.hpp"
#include "dma_support.hpp"
#include "diagnostics.hpp"
#include <cstring>
#include <atomic>
#if defined(PICO_ON_DEVICE)
#include "psram_spi.pio.h"
#if MK61_PICOCALC_AI_PSRAM_LATE_READ
#include "psram_qpi_late.pio.h"
#else
#include "psram_qpi.pio.h"
#endif
#include "psram_qpi_burst.pio.h"
#include "hardware/dma.h"
#include "hardware/clocks.h"
#include "hardware/pio.h"
#include "hardware/irq.h"
#include "hardware/regs/addressmap.h"
#include "pico/mutex.h"
#include "pico/stdlib.h"
#endif
namespace picocalc::psram {
namespace {
Statistics state{};
struct PendingRead {
    u32 commands[READ_PACKETS];
    unsigned bytes=0;
    std::atomic<int> owner{-1};
    u8* target=nullptr;
#if defined(PICO_ON_DEVICE)
    unsigned packets=0;
    bool burst=false;
#endif
} pending;
#if defined(PICO_ON_DEVICE)
#define PSRAM_COLD __attribute__((section(".ai_diagnostic_extension"),noinline))
constexpr unsigned CS=20,SCK=21,MOSI=2,MISO=3;
PIO bus=pio1;
#if MK61_PICOCALC_MANAGED_CLOCK
unsigned diagnostic_divider256=320;
void configure_diagnostic_clock(pio_sm_config& config) {sm_config_set_clkdiv_int_frac(&config,diagnostic_divider256/256,diagnostic_divider256%256);}
#endif
int sm=-1,tx=-1,rx=-1;
unsigned program_offset=UINT32_MAX;
unsigned qpi_write_offset=UINT32_MAX,qpi_read_offset=UINT32_MAX;
unsigned read_burst_bytes=64;
unsigned read_burst_divider256=ai_psram_read_clock::default_burst_divider;
bool burst_loaded=false;
bool burst_configured=false;
auto_init_mutex(bus_mutex);
// The burst reader occupies the SPI and short-reader slots together. Keep
// their SDK reservations throughout, and leave the writer loaded in PIO.
static_assert(sizeof(mk61_psram_spi_program_instructions)+sizeof(mk61_psram_qpi_read_program_instructions)==
    sizeof(mk61_psram_qpi_burst_program_instructions));
void load_program(const pio_program_t& program,unsigned offset) {
    for(unsigned i=0;i<program.length;++i) {
        const unsigned instruction=program.instructions[i];
        bus->instr_mem[offset+i]=instruction+((instruction&0xE000U)==pio_instr_bits_jmp?offset:0);
    }
}
PSRAM_COLD void load_read_program(bool burst) {
    burst_configured=false;
    if(burst) {
        load_program(mk61_psram_qpi_burst_program,qpi_read_offset);
        if(ai_psram_read_clock::late_burst_sample(read_burst_divider256)) {
            const unsigned at=qpi_read_offset+mk61_psram_qpi_burst_offset_burst_nibble;
            // Sample on the falling edge. Keep both clock widths at three
            // PIO cycles and leave the nonblocking push in the low phase.
            bus->instr_mem[at]=pio_encode_nop()|pio_encode_sideset(2,2)|pio_encode_delay(2);
            bus->instr_mem[at+1]=pio_encode_in(pio_pins,4)|pio_encode_sideset(2,0);
            bus->instr_mem[at+3]=pio_encode_jmp_x_dec(at)|pio_encode_sideset(2,0);
        }
    } else {
        load_program(mk61_psram_qpi_read_program,qpi_read_offset);
        load_program(mk61_psram_spi_program,program_offset);
    }
    burst_loaded=burst;
}
void select_burst_program(bool burst) {
    if(burst!=burst_loaded) load_read_program(burst);
}
unsigned active_read_burst() {
#if MK61_PICOCALC_MANAGED_CLOCK && MK61_PICOCALC_AI_OVERCLOCK && !MK61_PICOCALC_AI_PSRAM_LATE_READ
    if(read_burst_bytes>READ_BLOCK && ai_psram_read_clock::ai_profile(clock_get_hz(clk_sys),diagnostic_divider256))
        return read_burst_bytes;
#endif
    return READ_BLOCK;
}
PSRAM_COLD void park_spi() {
    burst_configured=false;
    pio_sm_set_enabled(bus,(unsigned)sm,false);
    select_burst_program(false);
    pio_sm_set_consecutive_pindirs(bus,(unsigned)sm,MOSI,1,true);
    pio_sm_set_consecutive_pindirs(bus,(unsigned)sm,MISO,1,false);
    pio_sm_set_pins_with_mask(bus,(unsigned)sm,(1U<<4)|(1U<<5),(1U<<4)|(1U<<5));
    pio_sm_set_consecutive_pindirs(bus,(unsigned)sm,4,2,true);
    auto config=mk61_psram_spi_program_get_default_config(program_offset);
#if MK61_PICOCALC_MANAGED_CLOCK
    configure_diagnostic_clock(config);
#endif
    sm_config_set_out_pins(&config,MOSI,1);sm_config_set_in_pins(&config,MISO);
    sm_config_set_sideset_pins(&config,CS);
    sm_config_set_out_shift(&config,false,true,32);sm_config_set_in_shift(&config,false,true,32);
    pio_sm_init(bus,(unsigned)sm,program_offset,&config);
    pio_sm_exec(bus,(unsigned)sm,pio_encode_nop()|pio_encode_sideset(2,1));
    auto receive=dma_channel_get_default_config((unsigned)rx);
    channel_config_set_transfer_data_size(&receive,DMA_SIZE_32);
    channel_config_set_dreq(&receive,pio_get_dreq(bus,(unsigned)sm,false));
    channel_config_set_read_increment(&receive,false);channel_config_set_write_increment(&receive,true);
    dma_channel_configure((unsigned)rx,&receive,nullptr,&bus->rxf[sm],0,false);
}
bool finish_stream(unsigned ready_offset,bool writing=false) {
    // DMA completion may precede the final CE# hold by a few clocks.
    // Wait for the idle high-CE# instruction, never deassert CE# in the CPU.
    const u64 limit=time_us_64()+1000;
    const auto idle=[&] {
        return stream_idle(ready_offset,pio_sm_get_pc(bus,(unsigned)sm),writing,
            pio_sm_is_tx_fifo_empty(bus,(unsigned)sm),gpio_get(CS));
    };
    while(!idle()) {
        if(time_us_64()>=limit) {
            // An interrupt can span the deadline after the first snapshot.
            if(idle()) break;
            ++state.tail_timeouts;
            burst_configured=false;
            state.tail_state=(ready_offset<<24)|(pio_sm_get_pc(bus,(unsigned)sm)<<16)|
                (pio_sm_get_tx_fifo_level(bus,(unsigned)sm)<<8)|
                (pio_sm_get_rx_fifo_level(bus,(unsigned)sm)<<4)|gpio_get(CS);
            pio_sm_set_enabled(bus,(unsigned)sm,false);
            dma_channel_abort((unsigned)tx);dma_channel_abort((unsigned)rx);
            pio_sm_exec(bus,(unsigned)sm,pio_encode_nop()|pio_encode_sideset(2,1));return false;
        }
        tight_loop_contents();
    }
    pio_sm_set_enabled(bus,(unsigned)sm,false);__dmb();return true;
}
bool quad_packets(const u32* sent,unsigned packet_bytes,unsigned packets) {
    if(!packet_bytes || packet_bytes>32 || !packets || clock_get_hz(clk_sys)<100000000) return false;
    burst_configured=false;
    const unsigned words=(packet_bytes+3)/4;
    pio_sm_set_enabled(bus,(unsigned)sm,false);
    auto config=mk61_psram_qpi_write_program_get_default_config(qpi_write_offset);
#if MK61_PICOCALC_MANAGED_CLOCK
    configure_diagnostic_clock(config);
#endif
    sm_config_set_out_pins(&config,MOSI,4);sm_config_set_sideset_pins(&config,CS);
    sm_config_set_out_shift(&config,false,false,32);sm_config_set_fifo_join(&config,PIO_FIFO_JOIN_TX);
    sm_config_set_mov_status(&config,STATUS_TX_LESSTHAN,words);
    pio_sm_init(bus,(unsigned)sm,qpi_write_offset,&config);
    pio_sm_set_consecutive_pindirs(bus,(unsigned)sm,MOSI,4,true);
    pio_sm_exec(bus,(unsigned)sm,pio_encode_nop()|pio_encode_sideset(2,1));
    pio_sm_put(bus,(unsigned)sm,packet_bytes*2-1);
    pio_sm_exec(bus,(unsigned)sm,pio_encode_pull(false,true)|pio_encode_sideset(2,1));
    pio_sm_exec(bus,(unsigned)sm,pio_encode_out(pio_isr,32)|pio_encode_sideset(2,1));
    dma_channel_set_read_addr((unsigned)tx,sent,false);
    dma_channel_set_trans_count((unsigned)tx,words*packets,true);
    pio_sm_set_enabled(bus,(unsigned)sm,true);
    ++state.write_batches;
    if(!dma_support::wait((unsigned)tx)) {
        pio_sm_set_enabled(bus,(unsigned)sm,false);
        pio_sm_exec(bus,(unsigned)sm,pio_encode_nop()|pio_encode_sideset(2,1));return false;
    }
    return finish_stream(qpi_write_offset,true);
}
bool quad_write(const u8* bytes,unsigned count) {
    if(!count || count>32) return false;
    u32 sent[8]{};
    for(unsigned i=0;i<count;++i) sent[i/4]|=u32(bytes[i])<<(24-8*(i%4));
    return quad_packets(sent,count,1);
}
PSRAM_COLD void setup_quad_read(void* destination,bool burst) {
    pio_sm_set_enabled(bus,(unsigned)sm,false);
    select_burst_program(burst);
    auto config=burst?mk61_psram_qpi_burst_program_get_default_config(qpi_read_offset):
        mk61_psram_qpi_read_program_get_default_config(qpi_read_offset);
#if MK61_PICOCALC_MANAGED_CLOCK
    configure_diagnostic_clock(config);
#if defined(MK61_PICOCALC_AI_OVERCLOCK) && MK61_PICOCALC_AI_OVERCLOCK
    const auto div=burst?read_burst_divider256:
        ai_psram_read_clock::divider256(clock_get_hz(clk_sys),diagnostic_divider256);
    sm_config_set_clkdiv_int_frac(&config,div/256,div%256);
#endif
#endif
    sm_config_set_out_pins(&config,MOSI,4);sm_config_set_in_pins(&config,MOSI);
    sm_config_set_set_pins(&config,MOSI,4);sm_config_set_sideset_pins(&config,CS);
    sm_config_set_out_shift(&config,false,false,32);sm_config_set_in_shift(&config,false,!burst,32);
    sm_config_set_mov_status(&config,STATUS_RX_LESSTHAN,1);
    pio_sm_init(bus,(unsigned)sm,qpi_read_offset,&config);
    pio_sm_exec(bus,(unsigned)sm,pio_encode_nop()|pio_encode_sideset(2,1));
    pio_sm_set_consecutive_pindirs(bus,(unsigned)sm,MOSI,4,true);
    auto receive=dma_channel_get_default_config((unsigned)rx);
    channel_config_set_transfer_data_size(&receive,DMA_SIZE_32);
    channel_config_set_dreq(&receive,pio_get_dreq(bus,(unsigned)sm,false));
    channel_config_set_read_increment(&receive,false);channel_config_set_write_increment(&receive,true);
    channel_config_set_bswap(&receive,true);
    channel_config_set_high_priority(&receive,burst);
    dma_channel_configure((unsigned)rx,&receive,destination,&bus->rxf[sm],0,false);
    burst_configured=burst;
}
void configure_quad_read(void* destination,bool burst=false) {
    // The successful read tail parks the SM at PULL with empty FIFOs and
    // CE# high. RX DMA still has the same source, DREQ and byte order.
    if(burst && burst_configured)
        dma_channel_set_write_addr((unsigned)rx,destination,false);
    else setup_quad_read(destination,burst);
}
void start_quad_read(const u32* commands,unsigned packets,unsigned bytes) {
    dma_channel_set_read_addr((unsigned)tx,commands,false);
    dma_channel_set_trans_count((unsigned)tx,packets,false);
    dma_channel_set_trans_count((unsigned)rx,bytes/4,false);
    dma_start_channel_mask((1U<<tx)|(1U<<rx));
    pio_sm_set_enabled(bus,(unsigned)sm,true);++state.read_batches;
}
bool wait_quad_read() {
    return dma_support::wait((unsigned)rx,tx) && finish_stream(qpi_read_offset);
}
PSRAM_COLD bool recover_quad_read(u32* commands,unsigned packets,unsigned bytes,void* destination,bool burst) {
    burst_configured=false;
    if(burst) {
        dma_channel_abort((unsigned)tx);dma_channel_abort((unsigned)rx);
        // With RX stopped, only an in-flight packet can finish. The next
        // packet waits for the FIFO to drain. Let PIO raise CE# and hold it.
        busy_wait_us_32(8);
    }
    pio_sm_set_enabled(bus,(unsigned)sm,false);
    dma_channel_abort((unsigned)tx);dma_channel_abort((unsigned)rx);
    pio_sm_exec(bus,(unsigned)sm,pio_encode_nop()|pio_encode_sideset(2,1));
    const u32 overflow=1U<<(PIO_FDEBUG_RXSTALL_LSB+sm);
    if(!burst || !(bus->fdebug&overflow)) return false;

    ++state.burst_retries;
    read_burst_bytes=READ_BLOCK;
    configure_quad_read(destination);
    const unsigned short_packets=short_read_commands(commands,packets,bytes);
    start_quad_read(commands,short_packets,bytes);
    if(wait_quad_read()) return true;
    pio_sm_set_enabled(bus,(unsigned)sm,false);
    pio_sm_exec(bus,(unsigned)sm,pio_encode_nop()|pio_encode_sideset(2,1));
    return false;
}
bool finish_quad_read(u32* commands,unsigned packets,unsigned bytes,void* destination,bool burst) {
    const u32 overflow=1U<<(PIO_FDEBUG_RXSTALL_LSB+sm);
    if((!burst || !(bus->fdebug&overflow)) && wait_quad_read() &&
       (!burst || !(bus->fdebug&overflow))) return true;
    return recover_quad_read(commands,packets,bytes,destination,burst);
}
bool quad_read(u32 address,u8* bytes,unsigned count) {
    if(!count || clock_get_hz(clk_sys)<100000000) return false;
    constexpr unsigned BATCH=64,STAGING_BYTES=BATCH*READ_BLOCK;
    u32 commands[BATCH],received[STAGING_BYTES/4];
    unsigned maximum=active_read_burst();
    configure_quad_read(received,maximum>READ_BLOCK);
    while(count) {
        const unsigned skip=address&(READ_BLOCK-1);
        const unsigned n=count<STAGING_BYTES-skip?count:STAGING_BYTES-skip;
        const unsigned length=(skip+n+READ_BLOCK-1)&~(READ_BLOCK-1);
        const unsigned packets=read_commands(commands,address-skip,length,maximum);
        dma_channel_set_write_addr((unsigned)rx,received,false);
        start_quad_read(commands,packets,length);
        if(!finish_quad_read(commands,packets,length,received,maximum>READ_BLOCK)) return false;
        if(read_burst_bytes==READ_BLOCK) maximum=READ_BLOCK;
        std::memcpy(bytes,((u8*)received)+skip,n);
        bytes+=n;address+=n;count-=n;diagnostics::feed_watchdog();
    }
    return true;
}
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
    if(state.qpi && !writing) return quad_read(address,bytes,count);
    while(count) {
        const unsigned maximum=state.qpi?(writing?28:32):(writing?12:11);
        unsigned n=count<maximum?count:maximum;
        if(n>1024-(address&1023)) n=1024-(address&1023);
        u8 header[]={(u8)(writing?0x02:0x0B),(u8)(address>>16),(u8)(address>>8),(u8)address,0};
        bool ok;
        if(state.qpi && writing) {
            constexpr unsigned BATCH=32;
            u32 sent[BATCH*8];const unsigned words=(n+7)/4;
            unsigned packets=0;
            while(packets<BATCH && count>=n && n<=1024-(address&1023)) {
                auto* packet=sent+packets*words;
                packet[0]=0x02000000U|address;
                for(unsigned i=0;i<n/4;++i) {
                    u32 word;std::memcpy(&word,bytes+i*4,4);
                    packet[1+i]=__builtin_bswap32(word);
                }
                if(n&3) {
                    u32 tail=0;
                    for(unsigned i=0;i<(n&3);++i) tail|=u32(bytes[(n&~3U)+i])<<(24-8*i);
                    packet[1+n/4]=tail;
                }
                bytes+=n;address+=n;count-=n;++packets;
            }
            ok=quad_packets(sent,n+4,packets);
            if(!ok) return false;
            diagnostics::feed_watchdog();continue;
        }
        else ok=exchange(header,writing?4:5,writing?bytes:nullptr,writing?nullptr:bytes,n);
        if(!ok) return false;
        bytes+=n;address+=n;count-=n;
        if(!(address&1023)) diagnostics::feed_watchdog();
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
#if defined(PICO_ON_DEVICE)
PSRAM_COLD
#endif
void prepare_reset() {
#if defined(PICO_ON_DEVICE)
    if(pending.owner==(int)get_core_num()) read_finish();
    if(sm<0 || !state.qpi) return;
    mutex_enter_blocking(&bus_mutex);
    const u8 exit_quad=0xF5;
    if(quad_write(&exit_quad,1)) { park_spi();state.qpi=false; }
    mutex_exit(&bus_mutex);
#endif
}
bool init() {
    if(pending.owner>=0) return false;
    state={};
#if defined(PICO_ON_DEVICE)
    read_burst_bytes=64;
    read_burst_divider256=ai_psram_read_clock::default_burst_divider;
#if MK61_PICOCALC_MANAGED_CLOCK
    if(const auto* plan=cosmic_clock::find(clock_get_hz(clk_sys)/1000000))
        diagnostic_divider256=plan->pio_div256;
#endif
    if(sm<0) {
        const auto abandon=[]() {
            if(qpi_read_offset!=UINT32_MAX) pio_remove_program(bus,&mk61_psram_qpi_read_program,qpi_read_offset);
            if(qpi_write_offset!=UINT32_MAX) pio_remove_program(bus,&mk61_psram_qpi_write_program,qpi_write_offset);
            if(program_offset!=UINT32_MAX) pio_remove_program(bus,&mk61_psram_spi_program,program_offset);
            if(tx>=0) dma_channel_unclaim((unsigned)tx);
            if(rx>=0) dma_channel_unclaim((unsigned)rx);
            if(sm>=0) pio_sm_unclaim(bus,(unsigned)sm);
            sm=tx=rx=-1;program_offset=qpi_read_offset=qpi_write_offset=UINT32_MAX;
            return false;
        };
        if(!pio_can_add_program(bus,&mk61_psram_spi_program)) return false;
        sm=pio_claim_unused_sm(bus,false);if(sm<0) return false;
        tx=dma_claim_unused_channel(false);rx=dma_claim_unused_channel(false);
        if(tx<0 || rx<0) {
            if(tx>=0) dma_channel_unclaim((unsigned)tx);
            if(rx>=0) dma_channel_unclaim((unsigned)rx);
            pio_sm_unclaim(bus,(unsigned)sm);sm=tx=rx=-1;return false;
        }
        dma_support::enable_irq((unsigned)tx);dma_support::enable_irq((unsigned)rx);
        if(!pio_can_add_program(bus,&mk61_psram_qpi_write_program)) return abandon();
        qpi_write_offset=pio_add_program(bus,&mk61_psram_qpi_write_program);
        if(!pio_can_add_program(bus,&mk61_psram_spi_program)) return abandon();
        program_offset=pio_add_program(bus,&mk61_psram_spi_program);
        if(!pio_can_add_program(bus,&mk61_psram_qpi_read_program)) return abandon();
        qpi_read_offset=pio_add_program(bus,&mk61_psram_qpi_read_program);
        if(qpi_read_offset+mk61_psram_qpi_read_program.length!=program_offset ||
           program_offset+mk61_psram_spi_program.length!=qpi_write_offset) return abandon();
        auto config=mk61_psram_spi_program_get_default_config(program_offset);
#if MK61_PICOCALC_MANAGED_CLOCK
    configure_diagnostic_clock(config);
#endif
        sm_config_set_out_pins(&config,MOSI,1);sm_config_set_in_pins(&config,MISO);
        sm_config_set_sideset_pins(&config,CS);
        sm_config_set_out_shift(&config,false,true,32);
        sm_config_set_in_shift(&config,false,true,32);
#if !MK61_PICOCALC_MANAGED_CLOCK
        sm_config_set_clkdiv(&config,1);
#endif
        const unsigned pins[]={CS,SCK,MOSI,MISO,4,5};
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
    // Warm MCU reset can leave the chip in QPI. Exit in four-bit mode first;
    // an SPI device ignores this incomplete two-clock SPI transaction.
    const u8 exit_quad=0xF5;
    if(!quad_write(&exit_quad,1)) return false;
    park_spi();
    const u8 reset_enable=0x66,reset=0x99,id_command[]={0x9F,0,0,0};
    if(!command(&reset_enable,1) || !command(&reset,1)) return false;
    sleep_us(200);
    u8 id[8]{};
    const bool identified=exchange(id_command,sizeof(id_command),nullptr,id,sizeof(id));
    state.id=(u32(id[0])<<16)|(u32(id[1])<<8)|id[2];
#if MK61_PICOCALC_MANAGED_CLOCK
    state.hz=100000000/6;
#else
    state.hz=clock_get_hz(clk_sys)/6;
#endif
    if(!identified || !id[0] || id[0]==0xFF || id[1]!=0x5D) return false;
    struct ProbeBus {
        bool read(u32 at,u8* bytes,unsigned count) { return access(at,bytes,count,false); }
        bool write(u32 at,const u8* bytes,unsigned count) { return access(at,const_cast<u8*>(bytes),count,true); }
        bool enter_qpi() { const u8 op=0x35;state.qpi=command(&op,1);return state.qpi; }
        bool reset_spi() {
            const u8 exit=0xF5,enable=0x66,reset=0x99;
            if(!quad_write(&exit,1)) return false;
            park_spi();state.qpi=false;
            if(!command(&enable,1) || !command(&reset,1)) return false;
            sleep_us(200);return true;
        }
        void fallback() { ++state.qpi_fallbacks; }
    } probe;
#if !defined(MK61_PICOCALC_PSRAM_QPI) || MK61_PICOCALC_PSRAM_QPI
    state.ready=qualify_boot(probe,state.boot,true);
#else
    state.ready=qualify_boot(probe,state.boot,false);
#endif
#else
    state.ready=memory && memory_size>=CAPACITY;state.hz=31250000;state.id=0x0D5D00;
#endif
    return state.ready;
}
#if MK61_PICOCALC_MANAGED_CLOCK
bool compute_clock_transition(u32 divider256,void (*change)(void*),void* context) {
    bool valid=false;for(const auto& plan:cosmic_clock::plans)if(plan.pio_div256==divider256)valid=true;
    if(!valid || !change)return false;
    if(sm<0 || !state.ready){change(context);return true;}
    if(!mutex_try_enter(&bus_mutex,nullptr))return false;
    const bool idle=!dma_channel_is_busy((unsigned)tx) && !dma_channel_is_busy((unsigned)rx) &&
        pio_sm_is_tx_fifo_empty(bus,(unsigned)sm) && pio_sm_is_rx_fifo_empty(bus,(unsigned)sm) && gpio_get(CS);
    if(idle) {
        burst_configured=false;
        pio_sm_set_enabled(bus,(unsigned)sm,false);
        if(divider256>diagnostic_divider256)
            pio_sm_set_clkdiv_int_frac(bus,(unsigned)sm,divider256/256,divider256%256);
        change(context);
        diagnostic_divider256=divider256;
        pio_sm_set_clkdiv_int_frac(bus,(unsigned)sm,divider256/256,divider256%256);
        pio_sm_clkdiv_restart(bus,(unsigned)sm);pio_sm_set_enabled(bus,(unsigned)sm,true);
    }
    mutex_exit(&bus_mutex);return idle;
}
bool diagnostic_clock_divider(u32 divider256) {
    bool valid=false;for(const auto& plan:cosmic_clock::plans)if(plan.pio_div256==divider256)valid=true;
    if(!valid || sm<0 || !state.ready)return false;
    if(!mutex_try_enter(&bus_mutex,nullptr))return false;
    const bool idle=!dma_channel_is_busy((unsigned)tx) && !dma_channel_is_busy((unsigned)rx) &&
        pio_sm_is_tx_fifo_empty(bus,(unsigned)sm) && pio_sm_is_rx_fifo_empty(bus,(unsigned)sm) && gpio_get(CS);
    if(idle) {
        burst_configured=false;
        pio_sm_set_enabled(bus,(unsigned)sm,false);
        diagnostic_divider256=divider256;
        pio_sm_set_clkdiv_int_frac(bus,(unsigned)sm,divider256/256,divider256%256);
        pio_sm_clkdiv_restart(bus,(unsigned)sm);pio_sm_set_enabled(bus,(unsigned)sm,true);
    }
    mutex_exit(&bus_mutex);return idle;
}
u32 diagnostic_clock_divider256() { return sm<0?0:bus->sm[sm].clkdiv>>8; }
#endif
bool read(u32 address,void* bytes,unsigned count) {
    if(!bounds(address,bytes,count)) return false;
    if(!count) return true;
#if defined(PICO_ON_DEVICE)
    if(pending.owner==(int)get_core_num()) return false;
    mutex_enter_blocking(&bus_mutex);
    const bool ok=access(address,bytes,count,false);
    mutex_exit(&bus_mutex);
#else
    if(pending.owner>=0) return false;
    const bool ok=true;if(count) std::memcpy(bytes,memory+address,count);
#endif
    if(ok) state.read_bytes+=count;else { ++state.errors;state.ready=false; }
    return ok;
}
#if defined(PICO_ON_DEVICE)
PSRAM_COLD
#endif
bool diagnostic_read_burst(unsigned bytes) {
#if defined(PICO_ON_DEVICE)
    if((bytes!=READ_BLOCK && bytes!=32 && bytes!=64) || !state.ready || !state.qpi ||
       !mutex_try_enter(&bus_mutex,nullptr)) return false;
    read_burst_bytes=bytes;
    const bool enabled=active_read_burst()==bytes;
    if(!enabled) read_burst_bytes=READ_BLOCK;
    mutex_exit(&bus_mutex);return enabled;
#else
    return bytes==READ_BLOCK;
#endif
}
#if defined(PICO_ON_DEVICE)
PSRAM_COLD
#endif
bool diagnostic_read_clock(unsigned divider256) {
#if defined(PICO_ON_DEVICE) && MK61_PICOCALC_MANAGED_CLOCK && MK61_PICOCALC_AI_OVERCLOCK && !MK61_PICOCALC_AI_PSRAM_LATE_READ
    if(!ai_psram_read_clock::sweep_divider(divider256) || !state.ready || !state.qpi ||
       !mutex_try_enter(&bus_mutex,nullptr)) return false;
    const bool idle=ai_psram_read_clock::ai_profile(clock_get_hz(clk_sys),diagnostic_divider256) &&
        !dma_channel_is_busy((unsigned)tx) && !dma_channel_is_busy((unsigned)rx) &&
        pio_sm_is_tx_fifo_empty(bus,(unsigned)sm) && pio_sm_is_rx_fifo_empty(bus,(unsigned)sm) && gpio_get(CS);
    if(idle && read_burst_divider256!=divider256) {
        pio_sm_set_enabled(bus,(unsigned)sm,false);
        select_burst_program(false);
        pio_sm_exec(bus,(unsigned)sm,pio_encode_jmp(qpi_read_offset)|pio_encode_sideset(2,1));
        read_burst_divider256=divider256;
    }
    mutex_exit(&bus_mutex);return idle;
#else
    (void)divider256;return false;
#endif
}
bool read_begin(u32 base,const block_io::ReadSpan* spans,unsigned count) {
    if(!state.ready || pending.owner>=0 || !spans || !count || count>16 || base>CAPACITY) return false;
#if defined(PICO_ON_DEVICE)
    if(!state.qpi || clock_get_hz(clk_sys)<100000000) return false;
#endif
    const auto first=reinterpret_cast<uintptr_t>(spans[0].destination);
    if(!first || (first&3)) return false;
    unsigned total=0;
    for(unsigned i=0;i<count;++i) {
        const auto& s=spans[i];
        if(s.offset>CAPACITY-base || s.bytes>CAPACITY-base-s.offset ||
           ((base+s.offset)&15) || !s.bytes || (s.bytes&15) ||
           s.bytes>READ_BLOCK*READ_PACKETS-total ||
           reinterpret_cast<uintptr_t>(s.destination)!=first+total) return false;
        total+=s.bytes;
    }
#if defined(PICO_ON_DEVICE)
    if(first<SRAM_BASE || first>=SRAM_END || total>SRAM_END-first) return false;
    // Keeping this lock until finish excludes other PSRAM clients and clock
    // changes while DMA reads the persistent command array and writes SRAM.
    if(!mutex_try_enter(&bus_mutex,nullptr)) return false;
    const unsigned maximum=active_read_burst();
#else
    const unsigned maximum=READ_BLOCK;
#endif
    unsigned packets=0;
    for(unsigned i=0;i<count;++i)
        packets+=read_commands(pending.commands+packets,base+spans[i].offset,spans[i].bytes,maximum);
    pending.bytes=total;
    pending.target=static_cast<u8*>(spans[0].destination);
#if defined(PICO_ON_DEVICE)
    pending.owner=(int)get_core_num();
    pending.packets=packets;
    pending.burst=maximum>READ_BLOCK;
    configure_quad_read(pending.target,pending.burst);
    start_quad_read(pending.commands,packets,total);
#else
    pending.owner=0;
#endif
    return true;
}
bool read_finish() {
#if defined(PICO_ON_DEVICE)
    if(pending.owner!=(int)get_core_num()) return false;
    const bool ok=finish_quad_read(pending.commands,pending.packets,pending.bytes,pending.target,pending.burst);
    pending.owner=-1;mutex_exit(&bus_mutex);
#else
    if(pending.owner<0) return false;
    // Deliberately defer the host copy until finish, exposing premature use.
    for(unsigned i=0;i<pending.bytes/READ_BLOCK;++i)
        std::memcpy(pending.target+i*READ_BLOCK,memory+(pending.commands[i]&0xFFFFFFU),READ_BLOCK);
    const bool ok=true;pending.owner=-1;pending.target=nullptr;
#endif
    if(ok) state.read_bytes+=pending.bytes;else { ++state.errors;state.ready=false; }
    pending.bytes=0;diagnostics::feed_watchdog();return ok;
}
bool write(u32 address,const void* bytes,unsigned count) {
    if(!bounds(address,bytes,count)) return false;
    if(!count) return true;
#if defined(PICO_ON_DEVICE)
    if(pending.owner==(int)get_core_num()) return false;
    mutex_enter_blocking(&bus_mutex);
    const bool ok=access(address,const_cast<void*>(bytes),count,true);
    mutex_exit(&bus_mutex);
#else
    if(pending.owner>=0) return false;
    const bool ok=true;if(count) std::memcpy(memory+address,bytes,count);
#endif
    if(ok) state.write_bytes+=count;else { ++state.errors;state.ready=false; }
    return ok;
}
Statistics statistics() {
    Statistics result=state;
#if defined(PICO_ON_DEVICE) && MK61_PICOCALC_MANAGED_CLOCK
    const u32 div=diagnostic_clock_divider256();
    if(div)result.hz=(u32)((uint64_t(clock_get_hz(clk_sys))*256/div)/6);
#endif
    return result;
}
#if defined(PICO_ON_DEVICE)
PSRAM_COLD
#endif
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

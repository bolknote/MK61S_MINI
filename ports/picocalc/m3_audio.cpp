#include "m3_audio.hpp"
#include "m3_audio_engine.hpp"
#include "io_worker.hpp"
#include "storage.hpp"
#include "sleep_clock_lease.hpp"
#include "pico_uart1.h"
#include "hardware/clocks.h"
#include "hardware/dma.h"
#include "hardware/sync.h"
#include "hardware/structs/clocks.h"
#include "hardware/uart.h"
#include "pico/stdlib.h"
#include <new>
#include <optional>

namespace picocalc::m3_audio {
namespace {
struct Clocks {
    static uint32_t read0(){return clocks_hw->sleep_en0;}
    static uint32_t read1(){return clocks_hw->sleep_en1;}
    static void set0(uint32_t v){hw_set_bits(&clocks_hw->sleep_en0,v);}
    static void set1(uint32_t v){hw_set_bits(&clocks_hw->sleep_en1,v);}
    static void clear0(uint32_t v){hw_clear_bits(&clocks_hw->sleep_en0,v);}
    static void clear1(uint32_t v){hw_clear_bits(&clocks_hw->sleep_en1,v);}
};
struct Context {
    m3::AudioEngine engine;
    stm3_pico_uart1 uart{};
    std::optional<SleepClockLease<Clocks>> clocks;
    int rx=-1;
    uint32_t tail=0,requests=0;
    unsigned tx_at=0;
    uint8_t capabilities=0;
    std::atomic<bool> control{false};
    bool streaming=false,owned=false,tx_started=false;
};
alignas(512) uint8_t receive[512];
std::atomic<Context*> context{nullptr};
Statistics last{};
uint16_t last_sequence=0;
uint32_t micros(void*){return time_us_32();}
void tx(Context& c) {
    if(!c.engine.wire.pending)return;
    if(!c.tx_started){c.tx_started=true;c.tx_at=0;++c.requests;}
    // START_RESULT and constant-DAC packets fit the32-byte FIFO.
    // Larger AY/DAC packets continue on later worker polls. Reserving no
    // TX DMA leaves one of RP2040's12 channels for continuous PWM output.
    while(c.tx_at<c.engine.wire.tx_bytes && uart_is_writable(uart1))
        uart_get_hw(uart1)->dr=c.engine.wire.tx[c.tx_at++];
}
void pump(Context& c) {
    auto& wire=c.engine.wire;
    if(uart_get_hw(uart1)->rsr&15u) {
        ++c.uart.errors;uart_get_hw(uart1)->rsr=0;
        if(wire.pending)wire.fail(m3::Wire::IO);
        if(c.streaming)c.engine.fail(m3::Wire::IO);
    }
    const uint32_t head=UINT32_MAX-dma_hw->ch[c.rx].transfer_count;
    __dmb();
    if(head-c.tail>sizeof(receive)) {
        ++c.uart.errors;c.tail=head;
        if(wire.pending)wire.fail(m3::Wire::IO);
        if(c.streaming)c.engine.fail(m3::Wire::IO);
    }
    while(c.tail!=head){wire.feed(receive[c.tail&(sizeof(receive)-1)]);++c.tail;}
    wire.tick(time_us_32());
    if(wire.complete) {
        c.tx_started=false;
        if(c.control.load(std::memory_order_relaxed))c.control.store(false,std::memory_order_release);
    }
}
void snapshot(Context& c) {
    const auto& e=c.engine;
    last.active=c.streaming;last.error=e.error.load(std::memory_order_acquire);
    last.blocks=e.blocks;last.samples=e.samples;last.underruns=e.underruns;
    last.max_slice=e.max_slice;last.requests=c.requests;last.uart_errors=c.uart.errors;
    last.max_render_us=e.max_render_us;last.starve_stage=e.starve_stage;
    last.starve_request_us=e.starve_request_us;last.starve_ahead=e.starve_ahead;
    last.min_block_us=e.blocks?e.min_render_us:0;last.block_us=e.block_us;last.late_blocks=e.late_blocks;
    last.ready_polls=e.ready_polls;last.prime_us=e.prime_us;last.min_queued=e.primed?e.min_queued:0;
}
void release(void* raw) {
    auto& c=*(Context*)raw;snapshot(c);last.active=false;
    context.store(nullptr,std::memory_order_release);
    uart_get_hw(uart1)->dmacr=0;
    for(int channel:{c.rx})if(channel>=0){
        dma_channel_set_irq0_enabled((unsigned)channel,false);dma_channel_set_irq1_enabled((unsigned)channel,false);
        dma_channel_abort((unsigned)channel);dma_channel_acknowledge_irq0((unsigned)channel);dma_channel_acknowledge_irq1((unsigned)channel);
        dma_channel_unclaim((unsigned)channel);
    }
    c.rx=-1;stm3_pico_uart1_end(&c.uart);c.clocks.reset();
    last_sequence=c.engine.wire.sequence;
}
bool setup(Context& c) {
    bool ready=false;
    struct Args { Context* c;bool* ready; } args{&c,&ready};
    io_worker::invoke(&args,[](void* raw) {
        auto& a=*(Args*)raw;auto& c=*a.c;
        if(!stm3_pico_uart1_begin(&c.uart,micros,nullptr,clock_get_hz(clk_peri),2250000))return;
        c.rx=dma_claim_unused_channel(false);
        if(c.rx<0){stm3_pico_uart1_end(&c.uart);return;}
        for(int channel:{c.rx}) {
            dma_channel_set_irq0_enabled((unsigned)channel,false);dma_channel_set_irq1_enabled((unsigned)channel,false);
            dma_channel_acknowledge_irq0((unsigned)channel);dma_channel_acknowledge_irq1((unsigned)channel);
        }
        constexpr uint32_t memory=CLOCKS_SLEEP_EN0_CLK_SYS_DMA_BITS|CLOCKS_SLEEP_EN0_CLK_SYS_BUSFABRIC_BITS|
            CLOCKS_SLEEP_EN0_CLK_SYS_SRAM0_BITS|CLOCKS_SLEEP_EN0_CLK_SYS_SRAM1_BITS|
            CLOCKS_SLEEP_EN0_CLK_SYS_SRAM2_BITS|CLOCKS_SLEEP_EN0_CLK_SYS_SRAM3_BITS;
        c.clocks.emplace(memory,CLOCKS_SLEEP_EN1_CLK_SYS_UART1_BITS|CLOCKS_SLEEP_EN1_CLK_PERI_UART1_BITS);
        auto config=dma_channel_get_default_config((unsigned)c.rx);
        channel_config_set_transfer_data_size(&config,DMA_SIZE_8);
        channel_config_set_read_increment(&config,false);channel_config_set_write_increment(&config,true);
        channel_config_set_ring(&config,true,9);channel_config_set_dreq(&config,uart_get_dreq(uart1,false));
        dma_channel_configure((unsigned)c.rx,&config,receive,&uart_get_hw(uart1)->dr,UINT32_MAX,false);
        uart_get_hw(uart1)->dmacr=1;dma_channel_start((unsigned)c.rx);
        c.engine.wire.sequence=uint16_t(last_sequence+1);
        context.store(&c,std::memory_order_release);*a.ready=true;
    });
    return ready;
}
bool wait_control(Context& c) {
    const uint32_t start=time_us_32();
    while(c.control.load(std::memory_order_acquire)) {
        if(time_us_32()-start>120000)return false;
        sleep_us(50);
    }
    return c.engine.wire.complete && !c.engine.wire.result;
}
bool rpc(Context& c,unsigned op,const uint8_t* data,unsigned n,bool prefix=false,unsigned offset=0) {
    struct Args { Context* c;unsigned op;const uint8_t* p;unsigned n;bool prefix;unsigned offset;bool ok; } a{&c,op,data,n,prefix,offset,false};
    io_worker::invoke(&a,[](void* raw) {
        auto& a=*(Args*)raw;auto& c=*a.c;
        if(c.engine.wire.pending)return;
        a.ok=c.engine.wire.begin(uint8_t(a.op),a.p,a.n,time_us_32(),50000,a.prefix,a.offset);
        if(a.ok){c.control.store(true,std::memory_order_release);tx(c);}
    });
    return a.ok && wait_control(c);
}
bool job(Context& c,unsigned bytes,unsigned result) {
    auto& e=c.engine;
    for(unsigned at=0;at<bytes;) {
        unsigned n=bytes-at;if(n>252)n=252;
        if(!rpc(c,5,e.packet+at,n,true,at))return false;at+=n;
    }
    unsigned received=result;if(received>S3_RESULT_LIMIT)received=S3_RESULT_LIMIT;
    uint8_t args[16];m3::Wire::put32(args,e.module);m3::Wire::put32(args+4,bytes);m3::Wire::put32(args+8,10);
    m3::Wire::put32(args+12,received);
    if(!rpc(c,S3_START_RESULT,args,16) || e.wire.reply_bytes!=8+received || !m3::Wire::get32(e.wire.reply()))return false;
    e.job=m3::Wire::get32(e.wire.reply());
    const uint32_t slice=m3::Wire::get32(e.wire.reply()+4);if(slice>e.max_slice)e.max_slice=slice;
    if(slice>2000)return false;
    std::memcpy(e.packet,e.wire.reply()+8,received);
    // Long state exports use ordinary READ only after a completed response;
    // no readiness polls, and no live job remains at this point.
    for(unsigned at=received;at<result;) {
        unsigned n=result-at;if(n>252)n=252;
        m3::Wire::put32(args,e.job);m3::Wire::put32(args+4,at);m3::Wire::put32(args+8,n);
        if(!rpc(c,8,args,12) || e.wire.reply_bytes!=n)return false;
        std::memcpy(e.packet+at,e.wire.reply(),n);at+=n;
    }
    return true;
}
bool load(Context& c,const char* path,unsigned gain) {
    auto& e=c.engine;files::Entry entry{};unsigned used=0;
    if(!files::stat(path,entry) || entry.directory || entry.size<68 || entry.size>6464 ||
       !files::read_range(path,0,e.packet,64,used) || used!=64)return false;
    if(m3::Wire::get32(e.packet)!=0x314d3353 || m3::Wire::get32(e.packet+4)!=1 ||
       m3::Wire::get32(e.packet+8)!=64 || m3::Wire::get32(e.packet+12)!=entry.size ||
       m3::Wire::get32(e.packet+56)!=0x70301)return false;
    if(!rpc(c,1,nullptr,0) || e.wire.reply_bytes!=36)return false;
    const auto* hello=e.wire.reply();
    if(m3::Wire::get32(hello)!=1 || m3::Wire::get32(hello+4)!=0x70301 ||
       m3::Wire::get32(hello+8)!=6144 || m3::Wire::get32(hello+12)!=512 ||
       m3::Wire::get32(hello+16)!=0 || m3::Wire::get32(hello+28)!=2250000 ||
       (m3::Wire::get32(hello+32)&7)!=7)return false;
    m3::Wire::put32(e.packet,entry.size);
    if(!rpc(c,2,e.packet,4))return false;c.owned=true;
    for(unsigned at=0;at<entry.size;) {
        unsigned n=entry.size-at;if(n>252)n=252;
        if(!files::read_range(path,at,e.packet,n,used) || used!=n || !rpc(c,3,e.packet,n,true,at) ||
           e.wire.reply_bytes!=4 || m3::Wire::get32(e.wire.reply())!=at+n)return false;
        at+=n;
    }
    if(!rpc(c,4,nullptr,0) || e.wire.reply_bytes!=4)return false;e.module=m3::Wire::get32(e.wire.reply());
    psg_packets::config(e.request,e.packet,true,gain);
    if(!job(c,psg_packets::STATE,8) || m3::Wire::get32(e.packet)!=psg_packets::PCM || !(e.packet[7]&2))return false;
    c.capabilities=e.packet[7];return true;
}
}
bool transport_active(){return context.load(std::memory_order_acquire)!=nullptr;}
void service() {
    auto* c=context.load(std::memory_order_acquire);if(!c)return;
    pump(*c);
    if(c->streaming && !c->control.load(std::memory_order_relaxed) && !c->tx_started) {
        c->engine.step(time_us_32());
    }
    tx(*c);
}
uint32_t duty(void*){auto* c=context.load(std::memory_order_acquire);return c?c->engine.sample(time_us_32()):0x00800080u;}
bool failed(){auto* c=context.load(std::memory_order_acquire);return c && c->engine.error.load(std::memory_order_acquire);}
void fault(int error){auto* c=context.load(std::memory_order_acquire);if(c)c->engine.fail(error);}
bool open(const mk61_service_audio_psg& request,unsigned gain) {
    if(context.load(std::memory_order_acquire) || !psg_packets::valid(request) || !request.recover || gain>1000)return false;
    auto* c=new(std::nothrow) Context;if(!c)return false;
    c->engine.request=request;last={};
    if(!setup(*c)){delete c;return false;}
    if(!load(*c,request.module_path,gain)){close();return false;}
    io_worker::invoke(c,[](void* raw) {
        auto& c=*(Context*)raw;c.engine.wire.complete=false;c.streaming=true;
    });
    return true;
}
void close() {
    auto* c=context.load(std::memory_order_acquire);if(!c)return;
    if(c->streaming) {
        c->engine.stopping.store(true,std::memory_order_release);__sev();
        const uint32_t start=time_us_32();
        while(!c->engine.stopped.load(std::memory_order_acquire) && time_us_32()-start<100000)sleep_us(50);
        io_worker::invoke(c,[](void* raw){
            auto& c=*(Context*)raw;c.streaming=false;
            if(c.engine.wire.pending)c.control.store(true,std::memory_order_release);
        });
        if(c->control.load(std::memory_order_acquire))(void)wait_control(*c);
        if(c->engine.stage==m3::AudioEngine::RESULT && c->engine.wire.command==S3_START_RESULT &&
           c->engine.wire.complete && !c->engine.wire.result && c->engine.wire.reply_bytes>=8)
            c->engine.job=m3::Wire::get32(c->engine.wire.reply());
        // Recover the exact oscillator/filter state before APP code resumes.
        if(!c->engine.error.load(std::memory_order_acquire) && c->engine.stopped.load(std::memory_order_acquire)) {
            m3::Wire::put32(c->engine.packet,psg_packets::MAGIC);m3::Wire::put32(c->engine.packet+4,2);
            if(!job(*c,8,psg_packets::STATE) || !psg_packets::restore(c->engine.request,c->engine.packet,psg_packets::STATE))c->engine.fail(-30);
        }
    }
    // A foreign module is never unloaded. For an owned module, HELLO first
    // confirms whether a bounded CANCEL is needed after a transport fault.
    if(c->owned) {
        bool empty=false;
        if(rpc(*c,1,nullptr,0) && c->engine.wire.reply_bytes==36) {
            uint32_t state=m3::Wire::get32(c->engine.wire.reply()+16);
            if(state==3 && c->engine.job) {
                uint8_t args[4];m3::Wire::put32(args,c->engine.job);(void)rpc(*c,9,args,4);
            }
            // A lost START reply may leave its ID unknown. Never guess an
            // ID: let this owned100ms job reach its cooperative deadline.
            const uint32_t start=time_us_32();
            while(state==3 && time_us_32()-start<110000) {
                sleep_us(250);
                if(!rpc(*c,1,nullptr,0) || c->engine.wire.reply_bytes!=36)break;
                state=m3::Wire::get32(c->engine.wire.reply()+16);
            }
            // A read-only profile is collected only after playback, without
            // adding UART requests to the real-time path or replacing a fault.
            if((state==2 || state==4 || state==5) && (c->capabilities&8)) {
                auto* p=c->engine.packet;
                m3::Wire::put32(p,psg_packets::MAGIC);m3::Wire::put32(p+4,3);
                if(job(*c,8,32) && m3::Wire::get32(p)==0x31504153u) {
                    last.profile_valid=true;
                    last.render_samples=m3::Wire::get32(p+4);last.render_jobs=m3::Wire::get32(p+8);
                    last.render_slices=m3::Wire::get32(p+12);
                    last.render_us=m3::Wire::get32(p+16)|(uint64_t(m3::Wire::get32(p+20))<<32);
                    last.max_job_us=m3::Wire::get32(p+24);last.render_max_slice_us=m3::Wire::get32(p+28);
                }
            }
            if(state!=3 && rpc(*c,10,nullptr,0) && rpc(*c,1,nullptr,0) && c->engine.wire.reply_bytes==36)
                empty=m3::Wire::get32(c->engine.wire.reply()+16)==0;
        }
        if(!empty)++last.unload_failures;
    }
    io_worker::invoke(c,release);delete c;
}
Statistics statistics() {
    auto* c=context.load(std::memory_order_acquire);
    if(c)io_worker::invoke(c,[](void* raw){snapshot(*(Context*)raw);});
    return last;
}
}

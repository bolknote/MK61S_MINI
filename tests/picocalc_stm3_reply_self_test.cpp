#include "m3_wire.hpp"
extern "C" {
#include "stm3_runtime.h"
}
#include <array>
#include <cassert>
#include <cstdio>
#include <cstring>
#include <vector>
using picocalc::m3::Wire;

static stm3_runtime coproc;
static bool ready=true,tx_busy=false,reject_tx=false,immediate_job=false;
static uint32_t last_uart_errors=0,last_rx_ms=0,now=0,native_calls=0;
static unsigned rx_at=0,starts=0;
static std::vector<uint8_t> rx;
static const uint8_t* dma_source=nullptr;
static std::vector<uint8_t> dma_snapshot;
static uint32_t uptime_ms(){return now/1000;}
static bool stm3_uart_tx_idle(){return !tx_busy;}
static unsigned stm3_uart_read(uint8_t* byte,unsigned count){
    assert(count==1);if(rx_at==rx.size())return 0;*byte=rx[rx_at++];return 1;
}
static uint32_t stm3_uart_errors(){return 0;}
static bool stm3_uart_tx_start(const uint8_t* data,unsigned count){
    assert(!tx_busy && count);if(reject_tx)return false;
    dma_source=data;dma_snapshot.assign(data,data+count);tx_busy=true;++starts;return true;
}
#include POLL_FILE

static void enqueue(const Wire& w){rx.insert(rx.end(),w.tx,w.tx+w.tx_bytes);}
static void complete(Wire& w){
    assert(tx_busy && dma_source);
    assert(!std::memcmp(dma_source,dma_snapshot.data(),dma_snapshot.size()));
    for(auto byte:dma_snapshot)w.feed(byte);
    tx_busy=false;dma_source=nullptr;assert(w.complete);
}
static void finish(Wire& w){
    for(unsigned i=0;i<12 && !tx_busy;++i)coproc_poll();
    complete(w);assert(!w.result);
}
static void exchange(Wire& w){enqueue(w);finish(w);}
static uint32_t load(Wire& w){
    stm3_header h{};h.magic=STM3_MAGIC;h.abi=STM3_ABI;h.header_bytes=64;h.package_bytes=68;
    h.image_bytes=4;h.entry_offset=1;h.input_limit=h.output_limit=512;h.slice_us=2000;h.target=STM3_TARGET;
    uint8_t package[68]{};h.payload_crc=stm3_crc32(package+64,4);h.header_crc=stm3_crc32(&h,60);
    std::memcpy(package,&h,64);uint8_t arg[4];Wire::put32(arg,sizeof(package));
    assert(w.begin(STM3_LOAD_BEGIN,arg,4,now));exchange(w);
    assert(w.begin(STM3_LOAD_CHUNK,package,sizeof(package),now,5000,true,0));exchange(w);
    assert(w.begin(STM3_LOAD_COMMIT,nullptr,0,now));exchange(w);return Wire::get32(w.reply());
}
static void fresh(){
    tx_busy=reject_tx=immediate_job=false;ready=true;now=last_uart_errors=last_rx_ms=native_calls=0;
    starts=rx_at=0;rx.clear();dma_source=nullptr;dma_snapshot.clear();
    stm3_backend b{};b.micros=[](void*){return now;};
    b.load_address=[](void*,const void*){return 0x20001000u;};
    b.invoke=[](void*,uint32_t,uint32_t op,const stm3_api*,stm3_job* j)->uint32_t{
        if(op==STM3_CANCEL || op==STM3_FINI)return STM3_DONE;
        assert(op==STM3_INIT || op==STM3_STEP);++native_calls;
        if(op==STM3_INIT && !immediate_job)return STM3_MORE;
        for(unsigned i=0;i<j->input_bytes;++i)j->output[i]=j->input[i]^0x5a;
        j->output_bytes=j->input_bytes;return STM3_DONE;
    };
    stm3_init(&coproc,&b);
}
int main(){
    for(bool immediate:{false,true}){
        fresh();Wire w;const auto module=load(w);immediate_job=immediate;
        uint8_t arg[16];Wire::put32(arg,module);Wire::put32(arg+4,4);
        Wire::put32(arg+8,10);Wire::put32(arg+12,4);const uint8_t input[4]={1,2,3,4};
        assert(w.begin_pair(STM3_START_RESULT_INPUT,arg,sizeof(arg),input,sizeof(input),now));
        enqueue(w);coproc_poll();assert(native_calls==1);
        if(!immediate){assert(!tx_busy);coproc_poll();assert(native_calls==2);}
        // INIT and STEP never run in the same poll. A completed job should
        // start DMA before the following keyboard/RTC/PMU foreground turn.
        assert(tx_busy==bool(EXPECT_IMMEDIATE));
        if(!tx_busy){now+=1500;coproc_poll();assert(tx_busy);}
        assert(native_calls==(immediate?1u:2u));
        const auto calls=native_calls;const auto count=starts;
        // While DMA owns the cached reply, another queued request cannot
        // overwrite it, advance the native job, or begin a second transfer.
        enqueue(w);const auto pending=rx_at;coproc_poll();assert(rx_at==pending && starts==count && native_calls==calls);
        complete(w);assert(!w.result && w.reply_bytes==12);
        for(unsigned i=0;i<4;++i)assert(w.reply()[8+i]==uint8_t(input[i]^0x5a));
        // The pending duplicate reuses the exact completed reply, at most once.
        const auto reply=dma_snapshot;assert(w.replay(now));finish(w);
        assert(dma_snapshot==reply && native_calls==calls);
    }
    // A busy/rejected UART leaves a cached reply intact for retry.
    fresh();Wire w;reject_tx=true;
    assert(w.begin(STM3_HELLO,nullptr,0,now));enqueue(w);coproc_poll();
    assert(!tx_busy && coproc.tx_at<coproc.tx_bytes);reject_tx=false;
    coproc_poll();complete(w);assert(!w.result && starts==1 && !native_calls);
    // Inactive transport consumes no bytes and starts no DMA.
    fresh();ready=false;assert(w.begin(STM3_HELLO,nullptr,0,now));enqueue(w);coproc_poll();
    assert(!rx_at && !starts && !native_calls);
    std::puts(EXPECT_IMMEDIATE?"STM3 HAL: same-turn DMA, INIT/STEP separation, cached replay and DMA ownership PASS":
        "STM3 HAL baseline: reproduced one extra foreground turn before ready-reply DMA PASS");
}

#ifndef MK61_PICOCALC_M3_AUDIO_ENGINE_HPP
#define MK61_PICOCALC_M3_AUDIO_ENGINE_HPP
#include "m3_wire.hpp"
#include "psg_packets.hpp"
#include "stm3_client.h"
#include <atomic>

namespace picocalc::m3 {
// Core1 produces duties, its audio IRQ consumes them. No APP callback runs
// here. The hardware adapter keeps wire TX pinned through DMA completion.
struct AudioEngine {
    static constexpr unsigned BLOCK=96,CAPACITY=256;
    enum Stage { IDLE,WRITE,RESULT } stage=IDLE;
    Wire wire;
    mk61_service_audio_psg request{};
    uint8_t packet[512]{},duties[CAPACITY]{},cached[11]{};
    std::atomic<uint32_t> read{0},write{0};
    std::atomic<int> error{0};
    std::atomic<bool> stopping{false},stopped{false};
    uint32_t module=0,job=0,blocks=0,samples=0,max_slice=0,underruns=0;
    uint32_t render_started=0,max_render_us=0,starve_stage=0,starve_request_us=0;
    uint32_t min_render_us=UINT32_MAX,late_blocks=0,ready_polls=0,prime_started=0,prime_us=0,min_queued=CAPACITY;
    uint64_t block_us=0;
    int32_t starve_ahead=0;
    unsigned bytes=0,offset=0,inflight=0,count=0,missing=0;
    uint16_t sequence=0;
    bool primed=false,cache_valid=false,prime_waiting=false;
    unsigned queued() const { return write.load(std::memory_order_acquire)-read.load(std::memory_order_acquire); }
    void fail(int reason) {error.store(reason?reason:-20,std::memory_order_release);stopped.store(true,std::memory_order_release);}
    bool begin(unsigned command,const uint8_t* data,unsigned n,uint32_t now,bool prefix=false,unsigned at=0) {
        if(command==S3_STATUS || command==S3_READ)++ready_polls;
        if(!wire.begin(uint8_t(command),data,n,now,12000,prefix,at)){fail(-21);return false;}
        return true;
    }
    void chunk(uint32_t now) {
        inflight=bytes-offset;if(inflight>252)inflight=252;
        begin(5,packet+offset,inflight,now,true,offset);
    }
    void start(uint32_t now) {
        uint8_t args[16];Wire::put32(args,module);Wire::put32(args+4,bytes);Wire::put32(args+8,10);
        Wire::put32(args+12,8+count);
        job=0;stage=RESULT;begin(S3_START_RESULT,args,sizeof(args),now);
    }
    void step(uint32_t now) {
        if(error.load(std::memory_order_acquire))return;
        if(stage!=IDLE) {
            if(!wire.complete)return;
            wire.complete=false;
            if(wire.result){fail(wire.result);return;}
            const uint8_t* reply=wire.reply();unsigned n=wire.reply_bytes;
            if(stage==WRITE) {
                if(n){fail(-22);return;}
                offset+=inflight;
                if(offset<bytes){chunk(now);return;}
                cache_valid=bytes==sizeof(cached);if(cache_valid)std::memcpy(cached,packet,sizeof(cached));
                start(now);return;
            }
            if(n<8 || !Wire::get32(reply)){fail(-23);return;}
            job=Wire::get32(reply);
            const uint32_t slice=Wire::get32(reply+4);if(slice>max_slice)max_slice=slice;
            if(slice>2000){fail(8);return;}
            reply+=8;n-=8;
            if(n!=8+count || Wire::get32(reply)!=psg_packets::PWM ||
               reply[4]!=count || reply[5] || (unsigned(reply[6])|(unsigned(reply[7])<<8))!=sequence) {fail(-26);return;}
            const uint32_t w=write.load(std::memory_order_relaxed),r=read.load(std::memory_order_acquire);
            const uint32_t elapsed=now-render_started;if(elapsed>max_render_us)max_render_us=elapsed;
            if(elapsed<min_render_us)min_render_us=elapsed;
            block_us+=elapsed;if(elapsed>count*40)++late_blocks;
            if(w-r>CAPACITY-count){fail(-27);return;}
            for(unsigned i=0;i<count;++i)duties[(w+i)&(CAPACITY-1)]=reply[8+i];
            write.store(w+count,std::memory_order_release);++sequence;++blocks;samples+=count;stage=IDLE;
        }
        if(stopping.load(std::memory_order_acquire)){stopped.store(true,std::memory_order_release);return;}
        if(queued()>CAPACITY-BLOCK)return;
        const int n=psg_packets::prepare(request,packet,BLOCK,BLOCK);
        if(n<0){fail(-28);return;}
        if(!n)return;
        bytes=unsigned(n);count=packet[5];offset=0;
        render_started=now;
        if(bytes==sizeof(cached) && cache_valid && !std::memcmp(packet,cached,sizeof(cached))){start(now);return;}
        stage=WRITE;chunk(now);
    }
    uint32_t sample(uint32_t now=0) {
        if(!__atomic_load_n(request.running,__ATOMIC_ACQUIRE) || error.load(std::memory_order_acquire))return 0x00800080u;
        const uint32_t r=read.load(std::memory_order_relaxed),w=write.load(std::memory_order_acquire);
        if(!primed){
            if(!prime_waiting){prime_waiting=true;prime_started=now;}
            if(w-r<2*BLOCK)return 0x00800080u;
            primed=true;prime_us=now-prime_started;
        }
        if(r==w) {
            if(!underruns) {
                starve_ahead=int32_t(__atomic_load_n(request.produced,__ATOMIC_ACQUIRE)-*request.time);
                starve_stage=unsigned(stage);starve_request_us=wire.pending?now-wire.started:0;
            }
            ++underruns;if(++missing>=16)fail(-29);
            return 0x00800080u;
        }
        missing=0;const uint32_t duty=duties[r&(CAPACITY-1)];
        if(w-r-1<min_queued)min_queued=w-r-1;
        read.store(r+1,std::memory_order_release);
        return duty|(duty<<16);
    }
};
}
#endif

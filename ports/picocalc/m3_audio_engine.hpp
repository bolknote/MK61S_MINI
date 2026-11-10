#ifndef MK61_PICOCALC_M3_AUDIO_ENGINE_HPP
#define MK61_PICOCALC_M3_AUDIO_ENGINE_HPP
#include "m3_wire.hpp"
#include "psg_packets.hpp"
#include "stm3_client.h"
#include "pcm_repeat.h"
#include <atomic>

namespace picocalc::m3 {
// Core1 produces duties, its audio IRQ consumes them. No APP callback runs
// here. The hardware adapter keeps wire TX pinned through DMA completion.
struct AudioEngine {
    static constexpr unsigned BLOCK=120,CAPACITY=512,PRIME_BLOCKS=3;
    // START_RESULT returns at most244 module bytes. 118 stereo frames plus
    // the8-byte header fit in one pushed response, with no extra READ RPC.
    static constexpr unsigned STEREO_BLOCK=(S3_RESULT_LIMIT-8)/2;
    enum Stage { IDLE,WRITE,RESULT } stage=IDLE;
    Wire wire;
    mk61_service_audio_psg request{};
    psg_packets::Options options;
    uint8_t packet[512]{},cached[11]{};
    uint16_t duties[CAPACITY]{};
    std::atomic<uint32_t> read{0},write{0};
    std::atomic<int> error{0};
    std::atomic<bool> stopping{false},stopped{false};
    uint32_t module=0,job=0,blocks=0,samples=0,max_slice=0,underruns=0;
    uint32_t render_started=0,max_render_us=0,starve_stage=0,starve_request_us=0;
    uint32_t min_render_us=UINT32_MAX,late_blocks=0,ready_polls=0,prime_started=0,prime_us=0,min_queued=CAPACITY;
    uint32_t first_late_index=0,first_late_us=0,first_late_request_us=0,first_late_count=0,first_late_bytes=0,first_late_queued=0,first_late_command=0;
    uint64_t block_us=0;
    int32_t starve_ahead=0;
    unsigned bytes=0,offset=0,inflight=0,count=0,missing=0,prepared_bytes=0,prepared_count=0;
    uint16_t sequence=0;
    bool timing=false,repeat=false;
    uint32_t first_late_compute_us=0,first_late_gap_us=0;
    bool primed=false,cache_valid=false,prime_waiting=false,inline_input=false;
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
    void start(uint32_t now,bool with_input=false) {
        uint8_t args[16];Wire::put32(args,module);Wire::put32(args+4,bytes);Wire::put32(args+8,10);
        Wire::put32(args+12,8+count*options.channels());
        job=0;stage=RESULT;
        const bool ok=with_input?
            wire.begin_pair(S3_START_RESULT_INPUT,args,sizeof(args),packet,bytes,now,12000):
            wire.begin(S3_START_RESULT,args,sizeof(args),now,12000);
        if(!ok)fail(-21);
    }
    void step(uint32_t now) {
        if(error.load(std::memory_order_acquire))return;
        if(stage!=IDLE) {
            if(!wire.complete) {
                // START already copied its input into the pinned wire TX.
                // Prepare the next event packet while M3 renders this one.
                // Reserve ring space for both results, including on CLOSE
                // after the PWM consumer has stopped. A prepared packet is
                // always rendered before exporting the shared PSG state.
                const unsigned block=options.layout?STEREO_BLOCK:BLOCK;
                if(stage==RESULT && uint32_t(now-render_started)<500 && !prepared_bytes && !stopping.load(std::memory_order_acquire) &&
                   queued()<=CAPACITY-count-block) {
                    const int n=psg_packets::prepare(request,packet,block,block);
                    if(n<0){fail(-28);return;}
                    if(n){prepared_bytes=unsigned(n);prepared_count=packet[5];psg_packets::put32(packet,options.magic());}
                }
                return;
            }
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
            const bool packed=repeat && options.layout && n>=8 && Wire::get32(reply)==psg_packets::PWM_STEREO_REPEAT;
            if((packed?(n>8+count*2):(n!=8+count*options.channels() || Wire::get32(reply)!=(options.layout?psg_packets::PWM_STEREO:psg_packets::PWM))) ||
               reply[4]!=count || (!timing && reply[5]) || (unsigned(reply[6])|(timing?0u:unsigned(reply[7])<<8))!=(timing?(sequence&255u):sequence)) {fail(-26);return;}
            const uint32_t w=write.load(std::memory_order_relaxed),r=read.load(std::memory_order_acquire);
            const uint32_t elapsed=now-render_started;if(elapsed>max_render_us)max_render_us=elapsed;
            if(elapsed<min_render_us)min_render_us=elapsed;
            block_us+=elapsed;if(elapsed>count*40) {
                if(!late_blocks) {
                    first_late_compute_us=timing?unsigned(reply[5])*16:0;first_late_gap_us=timing?unsigned(reply[7])*16:0;
                    first_late_index=blocks+1;first_late_us=elapsed;first_late_request_us=now-wire.started;
                    first_late_count=count;first_late_bytes=bytes;first_late_queued=w-r;first_late_command=wire.command;
                }
                ++late_blocks;
            }
            if(w-r>CAPACITY-count){fail(-27);return;}
            if(packed) {
                if(!stm3_pcm_repeat_decode_ring(duties,CAPACITY,w,reply+8,n-8,count)){fail(-26);return;}
            } else for(unsigned i=0;i<count;++i) {
                const unsigned at=8+i*options.channels();
                duties[(w+i)&(CAPACITY-1)]=uint16_t(reply[at])|uint16_t(reply[options.layout?at+1:at])<<8;
            }
            write.store(w+count,std::memory_order_release);++sequence;++blocks;samples+=count;stage=IDLE;
        }
        if(stopping.load(std::memory_order_acquire) && !prepared_bytes){stopped.store(true,std::memory_order_release);return;}
        const unsigned block=options.layout?STEREO_BLOCK:BLOCK;
        if(queued()>CAPACITY-block)return;
        if(prepared_bytes){bytes=prepared_bytes;count=prepared_count;prepared_bytes=0;}
        else {
            const int n=psg_packets::prepare(request,packet,block,block);
            if(n<0){fail(-28);return;}
            if(!n)return;
            bytes=unsigned(n);count=packet[5];psg_packets::put32(packet,options.magic());
        }
        offset=0;
        render_started=now;
        if(bytes==sizeof(cached) && cache_valid && !std::memcmp(packet,cached,sizeof(cached))){start(now);return;}
        if(inline_input && bytes<=S3_START_RESULT_INPUT_LIMIT) {
            cache_valid=bytes==sizeof(cached);
            if(cache_valid)std::memcpy(cached,packet,sizeof(cached));
            start(now,true);return;
        }
        stage=WRITE;chunk(now);
    }
    // Foreground producer and IRQ consumer both belong to core1. During
    // an IRQ the published write cursor cannot change, so copy a ready
    // block with one read publication. Stop/error flags remain per-sample.
    // Priming, short queues and faults retain the exact scalar slow path.
    template<class Clock> void fill_samples(uint32_t* out,unsigned n,Clock clock) {
        if(!n)return;
        uint32_t r=read.load(std::memory_order_relaxed);
        const uint32_t w=write.load(std::memory_order_acquire),available=w-r;
        if(!primed || available<n || available>CAPACITY ||
           !__atomic_load_n(request.running,__ATOMIC_ACQUIRE) || error.load(std::memory_order_acquire)) {
            for(unsigned i=0;i<n;++i)out[i]=sample(clock());
            return;
        }
        const uint32_t first=r;
        for(unsigned i=0;i<n;++i) {
            if(!__atomic_load_n(request.running,__ATOMIC_ACQUIRE) || error.load(std::memory_order_acquire))out[i]=0x00800080u;
            else {const uint32_t duty=duties[r++&(CAPACITY-1)];out[i]=(duty&255)|((duty>>8)<<16);}
        }
        if(r!=first){missing=0;if(w-r<min_queued)min_queued=w-r;read.store(r,std::memory_order_release);}
    }
    uint32_t sample(uint32_t now=0) {
        if(!__atomic_load_n(request.running,__ATOMIC_ACQUIRE) || error.load(std::memory_order_acquire))return 0x00800080u;
        const uint32_t r=read.load(std::memory_order_relaxed),w=write.load(std::memory_order_acquire);
        if(!primed){
            if(!prime_waiting){prime_waiting=true;prime_started=now;}
            if(w-r<PRIME_BLOCKS*(options.layout?STEREO_BLOCK:BLOCK))return 0x00800080u;
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
        return (duty&255)|((duty>>8)<<16);
    }
};
}
#endif

#include "m3_audio_engine.hpp"
extern "C" {
#include "stm3_runtime.h"
}
#include <array>
#include <cassert>
#include <cstdio>
using picocalc::m3::AudioEngine;
using picocalc::m3::Wire;
struct Server {
    stm3_runtime runtime{};
    uint32_t now=0,cost=0,generated=0,invocations=0,writes=0,legacy_jobs=0,completions=0,inline_completions=0;
    uint32_t request_wire_bytes=0,response_wire_bytes=0;
    uint16_t sequence=0;
    bool stereo=false,timing=false,repeat=false;
    uint16_t sent_sequence=0;bool sent=false;
    Server() {
        stm3_backend backend{};backend.context=this;
        backend.micros=[](void* p){return static_cast<Server*>(p)->now;};
        backend.load_address=[](void*,const void*){return uint32_t(0x20001000);};
        backend.invoke=[](void* raw,uint32_t,uint32_t op,const stm3_api*,stm3_job* job)->uint32_t {
            auto& s=*static_cast<Server*>(raw);
            if(op==STM3_FINI || op==STM3_CANCEL)return STM3_DONE;
            s.now+=s.cost;
            const unsigned n=job->input[5];
            assert(job->input_bytes>=11 && job->input[4]==1 && n && n<=AudioEngine::BLOCK);
            if(op==STM3_INIT) {
                ++s.invocations;Wire::put32(job->output,s.stereo?picocalc::psg_packets::PWM_STEREO:picocalc::psg_packets::PWM);
                job->output[4]=uint8_t(n);job->output[5]=s.timing?100:0;
                job->output[6]=uint8_t(s.sequence);job->output[7]=s.timing?20:uint8_t(s.sequence>>8);++s.sequence;
                job->output_bytes=8+n*(s.stereo?2:1);return STM3_MORE;
            }
            assert(op==STM3_STEP);
            unsigned end=job->progress+16;if(end>n)end=n;
            for(unsigned i=job->progress;i<end;++i) {
                const uint8_t value=s.repeat?uint8_t(64+((s.generated+i)/16)%128):uint8_t(s.generated+i);
                job->output[8+i*(s.stereo?2:1)]=value;
                if(s.stereo)job->output[9+2*i]=uint8_t(value^0xa5);
            }
            job->progress=end;
            if(end!=n)return STM3_MORE;
            if(s.repeat && s.stereo) {
                const unsigned used=stm3_pcm_repeat_encode(job->output+256,job->output+8,n);
                if(used && used<2*n){std::memcpy(job->output+8,job->output+256,used);Wire::put32(job->output,picocalc::psg_packets::PWM_STEREO_REPEAT);job->output_bytes=8+used;}
            }
            s.generated+=n;return STM3_DONE;
        };
        stm3_init(&runtime,&backend);
    }
    void exchange(Wire& w) {
        if(!sent || sent_sequence!=w.sequence) {
            sent=true;sent_sequence=w.sequence;
            if(w.command==5)++writes;
            if(w.command==6 || w.command==7 || w.command==8)++legacy_jobs;
            if(w.command==STM3_START_RESULT || w.command==STM3_START_RESULT_INPUT)++completions;
            if(w.command==STM3_START_RESULT_INPUT)++inline_completions;
            request_wire_bytes+=w.tx_bytes;
            for(unsigned i=0;i<w.tx_bytes;++i)stm3_feed(&runtime,w.tx[i]);
        }
        uint8_t out[272];const unsigned n=stm3_transmit(&runtime,out,sizeof(out));
        response_wire_bytes+=n;
        for(unsigned i=0;i<n;++i)w.feed(out[i]);
        if(n)assert(!w.pending && w.complete);
    }
    uint32_t load() {
        Wire w;stm3_header h{};h.magic=STM3_MAGIC;h.abi=STM3_ABI;h.header_bytes=64;h.package_bytes=68;
        h.image_bytes=4;h.entry_offset=1;h.input_limit=h.output_limit=512;h.slice_us=2000;h.target=STM3_TARGET;
        std::array<uint8_t,68> package{};h.payload_crc=stm3_crc32(package.data()+64,4);h.header_crc=stm3_crc32(&h,60);
        std::memcpy(package.data(),&h,64);uint8_t count[4];Wire::put32(count,68);
        assert(w.begin(2,count,4,now));exchange(w);assert(!w.result);
        assert(w.begin(3,package.data(),68,now,5000,true,0));exchange(w);assert(!w.result);
        assert(w.begin(4,nullptr,0,now));exchange(w);assert(!w.result);
        return Wire::get32(w.reply());
    }
};
struct Producer {
    uint32_t read=0xfffffff0u,write=0xfffffff0u,produced=0,time=0;
    uint8_t running=1,dac[3]{0,128,128},events[2048]{};
    int32_t dc_in=0,dc_out=0;
    mk61_service_audio_psg request{};
    Producer() {
        request.events=events;request.event_capacity=256;request.read=&read;request.write=&write;
        request.produced=&produced;request.time=&time;request.running=&running;request.dac=dac;
        request.dc_input=&dc_in;request.dc_output=&dc_out;
    }
};
int main() {
    {
        // Actual pushed transport CRC/sequence, compressed payload, ring wrap,
        // both PCM channels and both 16-bit sequence wraps remain exact.
        Server s;s.stereo=s.repeat=true;AudioEngine e;Producer p;int32_t filters[6]{};
        e.options={1,0,filters,true};e.repeat=true;e.module=s.load();e.request=p.request;e.inline_input=true;
        e.sequence=s.sequence=65534;e.wire.sequence=65530;
        const unsigned total=8*AudioEngine::STEREO_BLOCK;p.produced=total*140;unsigned consumed=0;
        for(unsigned turn=0;turn<30000 && consumed<total;++turn) {
            e.step(s.now);if(e.wire.pending)s.exchange(e.wire);if(!(turn%10))stm3_tick(&s.runtime);
            s.now+=40;const uint32_t before=e.read.load();const uint32_t actual=e.sample(s.now);
            if(e.read.load()!=before){const unsigned value=64+(consumed/16)%128;assert(actual==(value|((value^0xa5)<<16)));++consumed;}
            if(e.error.load())std::fprintf(stderr,"repeat error=%d turn=%u consumed=%u blocks=%u seq=%u wire=%u result=%d\n",e.error.load(),turn,consumed,e.blocks,e.sequence,e.wire.sequence,e.wire.result);
            assert(!e.error.load());
        }
        assert(consumed==total && e.blocks==8 && e.sequence==6 && !e.underruns && !e.ready_polls);
        assert(s.response_wire_bytes<8*270);e.stopping.store(true);e.step(s.now);assert(e.stopped.load());
    }
    {
        const auto check=[](const uint8_t* payload,unsigned bytes,unsigned frames,bool capability,bool valid) {
            AudioEngine e;Producer p;int32_t filters[6]{};e.options={1,0,filters,true};e.request=p.request;
            e.repeat=capability;e.stage=AudioEngine::RESULT;e.count=frames;e.wire.complete=true;e.wire.reply_bytes=16+bytes;
            uint8_t* r=e.wire.frame+12;Wire::put32(r,1);Wire::put32(r+4,0);Wire::put32(r+8,picocalc::psg_packets::PWM_STEREO_REPEAT);
            r[12]=uint8_t(frames);r[13]=r[14]=r[15]=0;std::memcpy(r+16,payload,bytes);e.step(100);
            if(valid){assert(!e.error.load() && e.samples==frames && e.write.load()==frames);for(unsigned i=0;i<frames;++i)assert(e.duties[i]==0x8080);}
            else assert(e.error.load()==-26 && !e.write.load());
        };
        const uint8_t correct[]={63,55},extra[]={63,55,0},truncated[]={64},escape[]={1,0},overrun[]={63};
        check(correct,2,118,true,true);check(correct,2,118,false,false);check(extra,3,118,true,false);
        check(truncated,1,1,true,false);check(escape,2,1,true,false);check(overrun,1,1,true,false);
    }
    {
        Server s;s.stereo=s.timing=true;AudioEngine e;Producer p;int32_t filters[6]{};
        e.options={1,0,filters,true};e.timing=true;e.module=s.load();e.request=p.request;e.inline_input=true;
        e.sequence=s.sequence=300;p.produced=AudioEngine::STEREO_BLOCK*140;e.step(0);
        for(unsigned turn=0;turn<100 && !e.wire.complete;++turn){s.exchange(e.wire);stm3_tick(&s.runtime);}
        assert(e.wire.complete);e.step(6000);
        assert(!e.error.load() && e.blocks==1 && e.first_late_index==1);
        assert(e.first_late_compute_us==1600 && e.first_late_gap_us==320);
        assert(e.samples==AudioEngine::STEREO_BLOCK && e.sequence==301);
    }

    for(unsigned layout=0;layout<=2;++layout) {
        // CLOSE can stop PWM while the next input is already prepared.
        // Drain that input once: producer cursors must match the exported
        // oscillator state, and both results must fit without a consumer.
        Server s;s.stereo=layout!=0;AudioEngine e;Producer p;int32_t filters[6]{};
        e.options={layout,0,filters,true};e.module=s.load();e.wire.sequence=100;e.request=p.request;e.inline_input=true;
        const unsigned block=layout?AudioEngine::STEREO_BLOCK:AudioEngine::BLOCK;
        e.write.store(AudioEngine::CAPACITY-2*block);p.produced=10*block*140;
        bool prefetched=false;
        for(unsigned turn=0;turn<2000 && !e.stopped.load();++turn) {
            e.step(s.now);
            if(e.prepared_bytes) {
                assert(e.stage==AudioEngine::RESULT && e.wire.pending && p.time==2*block*140);
                prefetched=true;e.stopping.store(true);
            }
            if(e.wire.pending)s.exchange(e.wire);
            if(!(turn%10))stm3_tick(&s.runtime);s.now+=40;
            assert(!e.error.load());
        }
        assert(prefetched && e.stopped.load() && e.blocks==2 && s.invocations==2 && !e.prepared_bytes);
        assert(e.queued()==AudioEngine::CAPACITY && p.time==e.samples*140 && !e.ready_polls && !s.legacy_jobs);
    }
    for(unsigned layout=1;layout<=2;++layout) {
        Server s;s.stereo=true;AudioEngine e;Producer p;
        int32_t filters[6]{};e.options={layout,layout-1,filters,true};
        e.module=s.load();e.wire.sequence=100;e.request=p.request;e.inline_input=true;
        e.read.store(0xfffffff0u);e.write.store(0xfffffff0u);
        constexpr unsigned samples=80*AudioEngine::STEREO_BLOCK;p.produced=samples*140;unsigned consumed=0;
        for(unsigned turn=0;turn<samples*8 && consumed<samples;++turn) {
            e.step(s.now);if(e.wire.pending)s.exchange(e.wire);
            if(!(turn%10))stm3_tick(&s.runtime);s.now+=40;
            const uint32_t before=e.read.load(),sample=e.sample(s.now);
            if(e.read.load()!=before) {
                assert(sample==(uint8_t(consumed)|(uint32_t(uint8_t(consumed^0xa5))<<16)));++consumed;
            }
            assert(!e.error.load());
        }
        assert(consumed==samples && e.blocks==80 && e.samples==samples && !e.underruns && !e.ready_polls && !s.legacy_jobs);
        assert(!s.writes && e.count==AudioEngine::STEREO_BLOCK && 8+2*e.count<=S3_RESULT_LIMIT);
        e.stopping.store(true);e.step(s.now);assert(e.stopped.load());
    }
    {
        Server s;AudioEngine e;Producer p;e.module=s.load();e.wire.sequence=100;e.request=p.request;e.inline_input=true;
        s.request_wire_bytes=s.response_wire_bytes=0;
        e.read.store(0xfffffff0u);e.write.store(0xfffffff0u);
        constexpr unsigned samples=80*AudioEngine::BLOCK;p.produced=samples*140;unsigned consumed=0;
        for(unsigned turn=0;turn<samples*8 && consumed<samples;++turn) {
            e.step(s.now);
            if(e.wire.pending)s.exchange(e.wire);
            if(!(turn%10))stm3_tick(&s.runtime);
            s.now+=40;
            const uint32_t before=e.read.load();const uint32_t sample=e.sample(s.now);
            if(e.read.load()!=before) {
                const uint32_t duty=uint8_t(consumed++);assert(sample==(duty|(duty<<16)));
            }
            assert(!e.error.load());
        }
        assert(consumed==samples && e.samples==samples && e.blocks==80 && s.invocations==80);
        assert(!s.writes && s.completions==80 && s.inline_completions==1 && !s.legacy_jobs &&
               p.time==p.produced && !e.underruns);
        assert(!e.ready_polls && e.block_us && e.min_render_us<=e.max_render_us && e.prime_us);
        e.stopping.store(true);e.step(s.now);assert(e.stopped.load() && !e.wire.pending);
    }
    {
        // A changing PSG packet is copied atomically with START_RESULT. It
        // must not pay for or depend on a preceding WRITE acknowledgement.
        Server s;AudioEngine e;Producer p;e.module=s.load();e.wire.sequence=100;e.request=p.request;e.inline_input=true;
        s.request_wire_bytes=s.response_wire_bytes=0;
        auto* event=p.events+(p.read&(p.request.event_capacity-1))*8;
        Wire::put32(event,140);event[4]=0;event[5]=0;event[6]=1;p.write=p.read+1;
        p.produced=AudioEngine::BLOCK*140;
        for(unsigned turn=0;turn<500 && !e.blocks;++turn) {
            e.step(s.now);if(e.wire.pending)s.exchange(e.wire);
            if(!(turn%10))stm3_tick(&s.runtime);s.now+=40;
        }
        assert(e.blocks==1 && e.samples==AudioEngine::BLOCK && !s.writes &&
               s.inline_completions==1 && p.read==p.write && !e.error.load());
        const uint32_t fused_bytes=s.request_wire_bytes+s.response_wire_bytes;

        Server legacy;AudioEngine old;Producer old_p;old.module=legacy.load();old.wire.sequence=100;old.request=old_p.request;
        legacy.request_wire_bytes=legacy.response_wire_bytes=0;
        auto* old_event=old_p.events+(old_p.read&(old_p.request.event_capacity-1))*8;
        Wire::put32(old_event,140);old_event[4]=0;old_event[5]=0;old_event[6]=1;old_p.write=old_p.read+1;
        old_p.produced=AudioEngine::BLOCK*140;
        for(unsigned turn=0;turn<500 && !old.blocks;++turn) {
            old.step(legacy.now);if(old.wire.pending)legacy.exchange(old.wire);
            if(!(turn%10))stm3_tick(&legacy.runtime);legacy.now+=40;
        }
        const uint32_t legacy_bytes=legacy.request_wire_bytes+legacy.response_wire_bytes;
        std::printf("M3 fused input: wire_bytes=%u legacy_bytes=%u legacy_writes=%u blocks=%u error=%d\n",
                    fused_bytes,legacy_bytes,legacy.writes,old.blocks,old.error.load());
        assert(old.blocks==1 && legacy.writes==1 && legacy.completions==1 &&
               !legacy.inline_completions && fused_bytes<legacy_bytes && !old.error.load());
    }
    {
        // A slow block can exceed its deadline while priming, before there
        // is a playback underrun. Preserve that latency in the diagnostics.
        Server s;AudioEngine e;Producer p;e.module=s.load();e.wire.sequence=100;e.request=p.request;
        p.produced=AudioEngine::BLOCK*140;
        for(unsigned turn=0;turn<300 && !e.blocks;++turn) {
            e.step(s.now);if(e.wire.pending)s.exchange(e.wire);
            if(!(turn%20))stm3_tick(&s.runtime);
            s.now+=40;
        }
        assert(e.blocks==1 && e.late_blocks==1 && e.min_render_us>AudioEngine::BLOCK*40 && e.block_us==e.max_render_us);
        assert(e.first_late_index==1 && e.first_late_us==e.max_render_us);
        assert(e.first_late_count==AudioEngine::BLOCK && e.first_late_bytes>=11);
        assert(e.first_late_request_us<=e.first_late_us && e.first_late_command==S3_START_RESULT);
        assert(!e.underruns && !e.error.load() && !e.ready_polls);
    }
    {
        // PMU occupies the STM32 foreground while Pico's PWM keeps draining.
        // Pause UART dispatch and job turns, not the module invocation clock:
        // fast native synthesis alone must not hide a scheduling stall.
        const auto exercise=[](unsigned gap_us,bool service_during_gap) {
            Server s;AudioEngine e;Producer p;e.module=s.load();e.wire.sequence=100;e.request=p.request;
            constexpr unsigned samples=20*AudioEngine::BLOCK;p.produced=samples*140;
            unsigned consumed=0;uint32_t gap_end=0;bool injected=false;
            for(unsigned turn=0;turn<30000 && consumed<samples && !e.error.load();++turn) {
                if(!injected && consumed>=400 && e.stage==AudioEngine::RESULT && s.runtime.job.progress>=32) {
                    injected=true;gap_end=s.now+gap_us;
                }
                const bool blocked=injected && s.now<gap_end && !service_during_gap;
                e.step(s.now);
                if(!blocked) {
                    if(e.wire.pending)s.exchange(e.wire);
                    if(!(turn%12))stm3_tick(&s.runtime);
                }
                s.now+=40;
                const uint32_t before=e.read.load();const uint32_t value=e.sample(s.now);
                if(e.read.load()!=before) {
                    const uint32_t duty=uint8_t(consumed++);assert(value==(duty|(duty<<16)));
                }
            }
            assert(injected && e.max_slice==0 && !e.ready_polls && !s.legacy_jobs);
            std::printf("PMU foreground gap=%uus service_M3=%u: samples=%u underruns=%u late=%u block_max_us=%u error=%d\n",
                        gap_us,service_during_gap,consumed,e.underruns,e.late_blocks,e.max_render_us,e.error.load());
            if(service_during_gap || !gap_us) {
                assert(consumed==samples && !e.error.load() && !e.underruns && !e.late_blocks);
            } else if(gap_us<10000) {
                assert(consumed==samples && e.late_blocks==1 && !e.underruns && !e.error.load());
            } else {
                assert(e.error.load()==STM3_E_TIME && consumed<samples);
            }
        };
        exercise(0,false);
        exercise(5000,false);
        exercise(12000,false);
        exercise(12000,true);
    }
    {
        Server s;AudioEngine e;Producer p;e.module=s.load();e.wire.sequence=100;e.request=p.request;
        p.produced=AudioEngine::BLOCK*140;s.cost=2001;
        for(unsigned turn=0;turn<20;++turn) {
            e.step(s.now);if(e.wire.pending)s.exchange(e.wire);s.now+=40;
        }
        assert(e.error.load()==STM3_E_TIME && e.stopped.load() && !e.samples && !e.queued() && s.invocations==1);
        assert(e.sample()==0x00800080u);
    }
    {
        // A deferred STEP fault arrives directly, without a STATUS poll.
        Server s;AudioEngine e;Producer p;e.module=s.load();e.wire.sequence=100;e.request=p.request;
        p.produced=AudioEngine::BLOCK*140;
        for(unsigned turn=0;turn<200 && !e.error.load();++turn) {
            e.step(s.now);if(e.wire.pending)s.exchange(e.wire);
            if(s.runtime.state==STM3_RUNNING){s.cost=2001;stm3_tick(&s.runtime);}
            s.now+=40;
        }
        assert(e.error.load()==STM3_E_TIME && !e.samples && !e.queued() && s.invocations==1);
    }
    {
        Server s;AudioEngine e;Producer p;e.module=s.load();e.wire.sequence=100;e.request=p.request;
        p.produced=AudioEngine::BLOCK*140;e.step(s.now);assert(e.stage==AudioEngine::WRITE);
        e.stopping.store(true);
        for(unsigned turn=0;turn<100 && !e.stopped.load();++turn) {
            if(e.wire.pending)s.exchange(e.wire);stm3_tick(&s.runtime);s.now+=40;e.step(s.now);
        }
        assert(e.stopped.load() && e.samples==AudioEngine::BLOCK && e.blocks==1 && !e.wire.pending && !e.error.load());
    }
    std::puts("M3 audio engine: exact duties, no readiness polls, deferred completion, PMU foreground stalls versus continued service, packet reuse, cursor wrap, drain-on-close and E_TIME PASS");
}

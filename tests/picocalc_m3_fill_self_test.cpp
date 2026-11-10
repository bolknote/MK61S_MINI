#include "m3_audio_engine.hpp"
#include "pwm_duty_ring.hpp"
#include "audio_irq_priority.hpp"
#include <array>
#include <cassert>
#include <cstdio>
using picocalc::m3::AudioEngine;
using picocalc::audio_stream::DutyRing;
struct Fixture {
    AudioEngine e;
    uint8_t running=1;uint32_t produced=10000,time=123;
    Fixture(uint32_t r,unsigned available,bool primed,unsigned layout,unsigned state) {
        e.request.running=&running;e.request.produced=&produced;e.request.time=&time;
        e.options.layout=layout;e.primed=primed;e.missing=state%16;e.min_queued=512;
        e.read.store(r);e.write.store(r+available);e.wire.pending=true;e.wire.started=0xffffff00;
        e.stage=AudioEngine::RESULT;
        if(state==1)running=0;if(state==2)e.error.store(-4);
        for(unsigned i=0;i<512;++i)e.duties[(r+i)&511]=uint16_t(((i*37+3)&255)|(((i*73+99)&255)<<8));
    }
};
static unsigned cases=0,fast=0;
static void check(unsigned count,unsigned available,bool primed,unsigned layout,unsigned state,uint32_t r) {
    Fixture a(r,available,primed,layout,state),b(r,available,primed,layout,state);
    std::array<uint32_t,66> scalar,bulk;scalar.fill(0xcafef00d);bulk=scalar;
    const uint32_t now=0xfffffff0;unsigned scalar_clocks=0,bulk_clocks=0;
    for(unsigned i=0;i<count;++i){++scalar_clocks;scalar[i+1]=a.e.sample(now);}
    b.e.fill_samples(bulk.data()+1,count,[&]{++bulk_clocks;return now;});
    assert(scalar==bulk && scalar_clocks==count);
    assert(a.e.read.load()==b.e.read.load() && a.e.write.load()==b.e.write.load());
    assert(a.e.error.load()==b.e.error.load() && a.e.stopped.load()==b.e.stopped.load());
    assert(a.e.primed==b.e.primed && a.e.prime_waiting==b.e.prime_waiting && a.e.prime_started==b.e.prime_started && a.e.prime_us==b.e.prime_us);
    assert(a.e.missing==b.e.missing && a.e.underruns==b.e.underruns && a.e.min_queued==b.e.min_queued);
    assert(a.e.starve_ahead==b.e.starve_ahead && a.e.starve_stage==b.e.starve_stage && a.e.starve_request_us==b.e.starve_request_us);
    if(count && primed && available>=count && available<=512 && state!=1 && state!=2){assert(!bulk_clocks);++fast;}
    ++cases;
}
struct Irq {
    unsigned current=1,calls=0;std::array<unsigned,32> priorities;
    Irq(){priorities.fill(128);}
    unsigned core()const{return current;}
    unsigned priority(unsigned n)const{return priorities[n];}
    void set_priority(unsigned n,unsigned p){priorities[n]=p;++calls;}
};
static void irq_tests() {
    using picocalc::audio_stream::AudioIrqPriority;
    Irq irq;AudioIrqPriority lease;
    assert(!lease.acquire(irq,2,0) && !irq.calls);
    irq.current=0;assert(!lease.acquire(irq,2,1) && !irq.calls);
    irq.current=1;assert(lease.acquire(irq,2,1) && irq.priorities[2]==0);
    assert(!lease.acquire(irq,2,1));irq.current=0;assert(!lease.release(irq) && lease.active);
    irq.current=1;assert(lease.release(irq) && irq.priorities[2]==128 && !lease.active);
    const auto calls=irq.calls;assert(lease.release(irq) && calls==irq.calls);
    for(unsigned i=0;i<32;++i)assert(irq.priorities[i]==128);
    // Deterministic NVIC ordering: a same-priority750us handler straddles
    // the refill deadline. Highest-priority audio preempts it. Global IRQ
    // masking and an overlong consumer still trip the unchanged guard.
    for(bool masked:{false,true})for(bool prioritize:{false,true}) {
        Irq p;AudioIrqPriority own;if(prioritize)assert(own.acquire(p,2,1));
        DutyRing ring;std::array<uint32_t,64> buffer{};unsigned source=0,now=0;
        ring.prime_block(buffer.data(),[&](uint32_t* out,unsigned n){for(unsigned i=0;i<n;++i)out[i]=source++;});
        now=1280;const bool preempts=!masked && p.priorities[2]<p.priorities[1];if(!preempts)now+=750;
        const auto saved=buffer;const unsigned previous=source;
        auto result=ring.refill_block(buffer.data(),[&]{return now/40;},[&](uint32_t* out,unsigned n){for(unsigned i=0;i<n;++i)out[i]=source++;now+=100;});
        if(preempts)assert(result==DutyRing::REFILLED && ring.filled==32 && source==previous+32);
        else assert(result==DutyRing::LATE && !ring.filled && saved==buffer && source==previous);
        if(prioritize)assert(own.release(p));
    }
    DutyRing ring;std::array<uint32_t,64> buffer{};unsigned now=1280;
    ring.prime_block(buffer.data(),[](uint32_t* p,unsigned n){for(unsigned i=0;i<n;++i)p[i]=0;});
    assert(ring.refill_block(buffer.data(),[&]{return now/40;},[&](uint32_t* p,unsigned n){for(unsigned i=0;i<n;++i)p[i]=1;now+=1280;})==DutyRing::LATE && !ring.filled);
}
int main() {
    AudioEngine empty;empty.fill_samples(nullptr,0,[]{assert(false);return 0;});
    for(unsigned count=0;count<=64;++count)for(unsigned available=0;available<=512;++available)
        check(count,available,true,1,0,0xfffffff0+count);
    for(unsigned count:{0u,1u,16u,31u,32u,33u,63u,64u})for(unsigned available:{0u,1u,15u,16u,31u,32u,33u,64u,118u,353u,354u,359u,360u,511u,512u,513u})
        for(unsigned layout=0;layout<3;++layout)for(bool primed:{false,true})for(unsigned state=0;state<4;++state)
            check(count,available,primed,layout,state,0xfffffff0+available);
    irq_tests();printf("PWM bulk consumer: %u exact scalar-equivalence states (%u fast), sample/clock/sequence bounds, prime/mute/underrun/wrap; IRQ preemption, restore/wrong-core and unchanged640us/overrun faults PASS\n",cases,fast);
}

#include "audio_diagnostic_storage.hpp"
#include <array>
#include <cassert>
#include <cstdint>
#include <cstdio>
#include <cstring>
#include <initializer_list>
#include "fixtures/audio_alarm_reference.hpp"
using namespace picocalc;
struct Fixture {
    uint32_t target=1280,remaining=UINT32_MAX-32,filled=32,fraction=0x11388,armed=0,now=1280;
    struct Port {
        Fixture&f;
        uint32_t target()const{return f.target;}uint32_t head()const{return UINT32_MAX-f.remaining;}
        uint32_t filled()const{return f.filled;}uint32_t fraction()const{return f.fraction;}uint32_t armed()const{return f.armed;}
    };
};
static uint32_t random_word(uint32_t&seed){seed^=seed<<13;seed^=seed>>17;seed^=seed<<5;return seed;}
static unsigned compare_case(uint32_t origin,uint32_t sequence,uint32_t callbacks,int delay,unsigned cause){
    Fixture f;AudioAlarmTrace compact;LegacyAlarmTrace legacy;
    compact.configure(2);legacy.configure({&f.target,&f.remaining,&f.filled,&f.fraction,&f.armed},2);
    compact.sequence=legacy.sequence=sequence;
    auto enter=[&]{uint32_t t=f.now;compact.enter(Fixture::Port{f},[&]{return t++;});t=f.now;legacy.enter([&]{return t++;});};
    auto after=[&]{uint32_t t=f.now;compact.after(Fixture::Port{f},[&]{return t++;});t=f.now;legacy.after([&]{return t++;});};
    f.now=origin+1280;f.target=f.now;enter();compact.fire.callbacks=legacy.callbacks=callbacks;
    compact.planned(delay);legacy.planned(delay);
    f.target=origin+(cause?3240:2560);f.armed=2;after();
    f.now=origin+3240;f.remaining=UINT32_MAX-81;f.armed=0;enter();compact.callback();legacy.callback();
    compact.fault(f.now+19,81,32);legacy.fault(f.now+19,81,32);
    const auto a=compact.snapshot();const auto b=legacy.snapshot();
    static_assert(sizeof(a)==sizeof(b));assert(std::memcmp(&a,&b,sizeof(a))==0);
    f.target+=1280;f.now+=999;enter();compact.callback();legacy.callback();after();
    compact.fault(0,0,0);legacy.fault(0,0,0);
    const auto a2=compact.snapshot();const auto b2=legacy.snapshot();assert(std::memcmp(&a2,&b2,sizeof(a2))==0);
    return 1;
}
void handler(){}
int main(){
    unsigned cases=0;uint32_t seed=0x52414d;
    for(uint32_t origin:{0u,1u,0xfffff000u,0xffffff00u})
    for(uint32_t sequence:{0u,1u,0xfffffffeu,0xffffffffu})
    for(uint32_t callbacks:{0u,1u,2u,0xffffffffu})
    for(int delay:{0,-40,-1280})for(unsigned cause=0;cause<2;++cause)
        cases+=compare_case(origin,sequence,callbacks,delay,cause);
    // Real union lifetimes, exact retained data and array bounds. Hardware
    // owners are modeled as quiesced at these storage API boundaries.
    for(unsigned n=0;n<1024;++n){
        AudioSynthStorage local;RemotePwmStorage remote;
        local.begin_remote();local.remote.alarm.configure(1u<<(n&3));
        local.remote.irq.pc=random_word(seed);local.remote.irq.fault_pc=random_word(seed);
        local.remote.irq.next=handler;local.remote.priority.previous=128;
        local.remote.alarm.start_before=random_word(seed);local.remote.alarm.start_after=local.remote.alarm.start_before+1;
        local.remote.alarm.start_fraction=0x11388;
        Fixture f;local.remote.alarm.enter(Fixture::Port{f},[&]{return f.now;});
        local.remote.alarm.callback();local.remote.alarm.planned(-1280);
        f.target+=1280;f.armed=15;local.remote.alarm.after(Fixture::Port{f},[&]{return f.now;});
        f.now+=1960;f.remaining=UINT32_MAX-81;local.remote.alarm.enter(Fixture::Port{f},[&]{return f.now;});
        local.remote.alarm.callback();if(n&1)local.remote.alarm.fault(f.now,81,32);
        const auto saved=local.remote.alarm.snapshot();const auto pc=local.remote.irq.pc,fault=local.remote.irq.fault_pc;
        remote.begin_pwm();for(unsigned i=0;i<64;++i)remote.samples[i]=random_word(seed);
        remote.retain(local.remote);local.begin_local();
        for(unsigned a=0;a<2;++a)for(unsigned i=0;i<16;++i)local.samples[a][i]=random_word(seed);
        const auto actual=remote.retained.alarm.snapshot();assert(std::memcmp(&saved,&actual,sizeof(saved))==0);
        assert(remote.retained.irq.pc==pc && remote.retained.irq.fault_pc==fault && remote.retained.irq.next==handler);
        assert(remote.retained.priority.previous==128);
        // Next remote start constructs its own state before the remote PWM
        // array overwrites the previous retained record.
        local.begin_remote();assert(!local.remote.alarm.snapshot().valid && !local.remote.irq.active && !local.remote.priority.active);
        remote.begin_pwm();for(unsigned i=0;i<64;++i)remote.samples[i]=0x00800080;
        for(unsigned i=0;i<64;++i)assert(remote.samples[i]==0x00800080);++cases;
    }
    AudioAlarmTrace inactive;unsigned reads=0;Fixture f;
    inactive.enter(Fixture::Port{f},[&]{++reads;return 0u;});inactive.after(Fixture::Port{f},[&]{++reads;return 0u;});
    inactive.callback();inactive.planned(-1280);inactive.fault(1,49,0);assert(!reads && !inactive.snapshot().valid);++cases;
    std::printf("PASS %u compact/reference and storage cases: exact fault tuples, full32bit counters, time/sequence wrap, 0/-40/-1280 intervals, freeze, 1024 remote/local/retained/restart transitions; modeled quiesced owners, ASan/UBSan.\n",cases);
}

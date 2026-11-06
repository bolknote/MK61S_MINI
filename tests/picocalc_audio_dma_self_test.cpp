// Reuse the core-1 executor, timer/key-click and clock fixtures. Its legacy
// main remains compiled, while this main exercises the actual DMA branch.
#define main legacy_audio_test_main
#include "picocalc_audio_self_test.cpp"
#undef main
#include <array>
#include <vector>
namespace {
struct Channel {
    bool claimed=false,busy=false,irq=false;
    dma_channel_config config{};
    uintptr_t read=0;
    volatile uint32_t* target=nullptr;
    unsigned reload=0,left=0;
};
std::array<Channel,12> channels;
fake_dma_hw dma_registers;
fake_pwm_hw pwm_registers;
bool timer_claimed=false,force_timer_failure=false;
int channel_budget=12;
unsigned numerator=0,denominator=0;
void(*dma_handler)()=nullptr;
std::vector<uint32_t> wire;
unsigned aborts=0;
enum class RefillRace { NONE,READ_ADDR,COUNT,ENABLE };
RefillRace refill_race=RefillRace::NONE;
void trigger(unsigned channel) {
    auto& c=channels[channel];assert(c.claimed);
    // RP2040 trigger writes/chains are ignored while EN is clear or BUSY.
    if(!c.config.enabled || c.busy) return;
    c.left=c.reload;c.busy=c.left!=0;
}
void dma_sample() {
    assert(numerator==1 && denominator==clock_get_hz(clk_sys)/25000);
    unsigned active=12;
    for(unsigned i=0;i<channels.size();++i) if(channels[i].busy && channels[i].config.enabled) { assert(active==12);active=i; }
    assert(active!=12);auto& c=channels[active];
    assert(c.config.ring==6 && c.config.size==DMA_SIZE_32 && c.config.read_increment && !c.config.write_increment);
    const uint32_t value=*(const uint32_t*)c.read;*c.target=value;wire.push_back(value);
    c.read=(c.read&~uintptr_t(63))|((c.read+4)&63);
    if(!--c.left) { c.busy=false;if(c.irq) dma_registers.ints1|=1U<<active;trigger(c.config.chain); }
}
void complete(unsigned n=16) { for(unsigned i=0;i<n;++i) dma_sample(); }
void inject_race(RefillRace point) {
    if(refill_race!=point) return;
    refill_race=RefillRace::NONE;complete();
}
void dispatch_irq() {
    std::thread irq([] { std::lock_guard<std::mutex> lock(executor);core1=true;assert(dma_handler);dma_handler(); });irq.join();
}
void resources_released() {
    assert(!timer_claimed && !dma_handler && !numerator);
    for(const auto& c:channels) assert(!c.claimed && !c.busy && !c.irq);
}
struct Ramp { unsigned calls=0;bool late=false; };
uint32_t ramp(void* raw) {
    assert(core1);auto& r=*(Ramp*)raw;
    if(r.late && r.calls==32) complete(); // Peer finishes while this block is paused/refilled.
    const int16_t l=(int16_t)(r.calls*197),right=(int16_t)-l;++r.calls;
    return (uint16_t)l|(uint32_t((uint16_t)right)<<16);
}
uint32_t expected(unsigned i) {
    const int16_t l=(int16_t)(i*197),r=(int16_t)-l;
    return uint16_t(128+(int32_t(l)*1000)/512000)|(uint32_t(uint16_t(128+(int32_t(r)*1000)/512000))<<16);
}
}
fake_dma_hw* dma_hw=&dma_registers;
fake_pwm_hw* pwm_hw=&pwm_registers;
unsigned clock_get_hz(unsigned clock) {
    assert(clock==clk_sys);
#if MK61_PICOCALC_AUTOMATIC_AUDIO_CLOCK
    return clock_mhz*1000000;
#else
    return TEST_CLOCK_MHZ*1000000;
#endif
}
int dma_claim_unused_channel(bool required) {
    assert(core1 && !required);
    if(channel_budget<=0)return -1;
    --channel_budget;
    for(unsigned i=0;i<channels.size();++i) if(!channels[i].claimed) { channels[i]={};channels[i].claimed=true;return (int)i; }
    return -1;
}
int dma_claim_unused_timer(bool required) { assert(core1 && !required && !timer_claimed);if(force_timer_failure)return -1;timer_claimed=true;return 2; }
void dma_channel_unclaim(unsigned n) { assert(core1 && channels[n].claimed && !channels[n].busy);channels[n].claimed=false;++channel_budget; }
void dma_timer_unclaim(unsigned n) { assert(core1 && n==2 && timer_claimed && !numerator);timer_claimed=false; }
void dma_timer_set_fraction(unsigned n,uint16_t x,uint16_t y) { assert(core1 && n==2 && timer_claimed);numerator=x;denominator=y; }
unsigned dma_get_timer_dreq(unsigned n) { assert(n==2);return 61; }
dma_channel_config dma_channel_get_default_config(unsigned n) { dma_channel_config c;c.channel=c.chain=n;return c; }
void channel_config_set_enable(dma_channel_config* c,bool v) { c->enabled=v; }
void channel_config_set_chain_to(dma_channel_config* c,unsigned n) { c->chain=n; }
void channel_config_set_transfer_data_size(dma_channel_config* c,unsigned n) { c->size=n; }
void channel_config_set_read_increment(dma_channel_config* c,bool v) { c->read_increment=v; }
void channel_config_set_write_increment(dma_channel_config* c,bool v) { c->write_increment=v; }
void channel_config_set_dreq(dma_channel_config* c,unsigned n) { c->dreq=n; }
void channel_config_set_ring(dma_channel_config* c,bool writing,unsigned n) { assert(!writing);c->ring=n; }
void dma_channel_set_irq1_enabled(unsigned n,bool enabled) { assert(core1);channels[n].irq=enabled; }
void dma_channel_set_config(unsigned n,const dma_channel_config* config,bool start) {
    assert(core1 && !start);if(config->enabled) inject_race(RefillRace::ENABLE);channels[n].config=*config;
}
void dma_channel_set_read_addr(unsigned n,const volatile void* p,bool start) {
    assert(core1 && !start && !channels[n].busy);inject_race(RefillRace::READ_ADDR);channels[n].read=(uintptr_t)p;
}
void dma_channel_set_trans_count(unsigned n,uint32_t count,bool start) {
    assert(core1 && !start && !channels[n].busy);inject_race(RefillRace::COUNT);channels[n].reload=channels[n].left=count;
}
void dma_channel_configure(unsigned n,const dma_channel_config* config,volatile void* target,const volatile void* source,unsigned count,bool start) {
    assert(core1 && !start && ((uintptr_t)source&63)==0);
    auto& c=channels[n];c.config=*config;c.read=(uintptr_t)source;c.target=(volatile uint32_t*)target;c.reload=c.left=count;
}
void dma_start_channel_mask(uint32_t mask) { assert(core1);for(unsigned i=0;i<channels.size();++i) if(mask&(1U<<i))trigger(i); }
void dma_channel_abort(unsigned n) { assert(core1 && !channels[n].config.enabled && !channels[n].irq);channels[n].busy=false;++aborts; }
void dma_channel_acknowledge_irq1(unsigned n) { assert(core1);dma_registers.ints1&=~(1U<<n); }
bool dma_channel_is_busy(unsigned n) { return channels[n].busy; }
void irq_add_shared_handler(unsigned irq,void(*f)(),unsigned) { assert(core1 && irq==DMA_IRQ_1 && !dma_handler);dma_handler=f; }
void irq_remove_handler(unsigned irq,void(*f)()) { assert(core1 && irq==DMA_IRQ_1 && dma_handler==f);dma_handler=nullptr; }
void irq_set_enabled(unsigned irq,bool enabled) { assert(core1 && irq==DMA_IRQ_1 && enabled); }
int main() {
    using namespace picocalc::audio_stream;
    Ramp state;mk61_service_audio_synth request{ramp,&state,25000,100};
    assert(synth(request,10) && active() && synth_statistics().dma && state.calls==32);
    assert(pools==0 && !alarm); // DMA synthesis consumes no25kHz timer alarm.
    for(unsigned block=0;block<100;++block) {
        complete();dispatch_irq();
        assert(state.calls==32+(block+1)*16 && !synth_statistics().underruns);
    }
    assert(wire.size()==1600);
    for(unsigned i=0;i<wire.size();++i) assert(wire[i]==expected(i));
    // A shared DMA interrupt must preserve another owner's pending bit.
    dma_registers.ints1|=1U<<11;dispatch_irq();assert(dma_registers.ints1==(1U<<11));
    close();resources_released();assert(dma_registers.ints1==(1U<<11) && !enabled && !active());
    dma_registers.ints1=0;
    for(int budget:{0,1,2}) {
        channel_budget=budget;force_timer_failure=budget==2;state={};
        assert(synth(request,10) && active() && !synth_statistics().dma && state.calls==0);
        sample();assert(state.calls==1);close();resources_released();
        assert(channel_budget==budget);
    }
    force_timer_failure=false;channel_budget=12;
    // IRQ missed for two whole blocks: never read beyond either ring,
    // silence and count the failed refill, retain ownership until close.
    state={};assert(synth(request,10));complete(32);dispatch_irq();
    assert(!synth_statistics().dma && synth_statistics().underruns==1 && active());
    assert(!numerator && left_level==128 && right_level==128 && state.calls==32);
    mk61_service_audio status{};assert(call(MK61_AUDIO_STATUS,&status,10) && status.underruns==1);
    close();resources_released();
    state={};state.late=true;assert(synth(request,10));complete();dispatch_irq();
    assert(!synth_statistics().dma && synth_statistics().underruns==1);close();resources_released();
    // Peer completion after the final pending-IRQ check may lose its chain
    // trigger while this channel is disabled. Each register-update window
    // must be detected rather than leaving two idle channels marked active.
    for(auto point:{RefillRace::READ_ADDR,RefillRace::COUNT,RefillRace::ENABLE}) {
        state={};assert(synth(request,10));complete();refill_race=point;dispatch_irq();
        assert(refill_race==RefillRace::NONE);
        assert(!synth_statistics().dma && synth_statistics().underruns==1);
        assert(!numerator && state.calls==48);close();resources_released();
    }
    // close() must join a running block callback before releasing its APP.
    Synth blocked;request={render,&blocked,25000,100};assert(synth(request,10));
    blocked.block=true;blocked.entered.store(false);complete();
    std::thread irq([] { std::lock_guard<std::mutex> lock(executor);core1=true;dma_handler(); });
    while(!blocked.entered.load(std::memory_order_acquire)) std::this_thread::yield();
    std::atomic<bool> closed{false};std::thread closer([&] { close();closed.store(true,std::memory_order_release); });
    assert(!closed.load());blocked.release.store(true,std::memory_order_release);irq.join();closer.join();
    assert(closed.load() && !active() && !enabled);resources_released();
    // Key clicks retain the finite timer path; synth reopen returns to DMA.
    assert(key_click() && !synth_statistics().dma);sample();stop_key_click();
    assert(!key_click_statistics().active && !enabled);
    state={};request={ramp,&state,25000,100};assert(synth(request,10) && synth_statistics().dma);close();resources_released();
    assert(aborts>0);
#if MK61_PICOCALC_AUTOMATIC_AUDIO_CLOCK
    assert(clock_mhz==125 && boosts==restores);
#endif
    puts("DMA synth PASS:25kHz exact pacing,1600 ordered stereo samples,640us blocks, shared IRQ isolation, resource fallback, late IRQ silence, APP unload and reopen");
}

#include "pico/stdlib.h"
#include <atomic>
#include <cassert>
#include <cstdio>
#include <mutex>
#include <thread>
#include <vector>
#include "audio.hpp"
#include "cosmic_clock.hpp"
static thread_local bool core1=false;
#if MK61_PICOCALC_AUTOMATIC_AUDIO_CLOCK
#include "cosmic_clock_plan.hpp"
static unsigned clock_mhz=125,boosts=0,restores=0;
static bool clock_failure=false;
namespace picocalc::audio_stream { bool active(); }
namespace picocalc::cosmic_clock {
bool audio_begin() {
    assert(!core1 && !audio_stream::active() && clock_mhz==125);
    if(clock_failure)return false;
    clock_mhz=200;++boosts;return true;
}
void audio_end() {
    assert(!core1 && !audio_stream::active());
    if(clock_mhz==200){clock_mhz=125;++restores;}
}
uint32_t pwm_divider16(){return find(clock_mhz)->pwm_div16;}
}
#endif
#if defined(TEST_CLOCK_MHZ)
#include "cosmic_clock_plan.hpp"
namespace picocalc::cosmic_clock {
uint32_t pwm_divider16() { return find(TEST_CLOCK_MHZ)->pwm_div16; }
}
#endif
#define MK61_PICOCALC_SCRIPT_HPP
#define MK61_TEST_M3_AUDIO_BACKEND 1
namespace picocalc::script { void tone(unsigned,unsigned,unsigned=100);audio::Plan tone_status(); }
#include "../ports/picocalc/audio_stream.cpp"
namespace picocalc::m3_audio {
static bool available=false,opened=false,broken=false;
bool open(const mk61_service_audio_psg&,unsigned,const mk61_service_audio_psg_config*){assert(!core1);opened=available;broken=false;return opened;}
void close(){assert(!core1);opened=false;broken=false;}
bool failed(){return opened && broken;}
void fault(int){broken=true;}
uint32_t duty(void*){assert(core1 && opened);return 0x00800080u;}
bool transport_active(){return opened;}
void service(){}
Statistics statistics(){return {};}
}
static std::mutex executor;
static repeating_timer* alarm;
static unsigned pools,pool_destroys,cancels,left_level,right_level,disabled,pwm_wrap;
static bool pool_live;
static bool enabled;
static bool timer_failure;
static fake_pwm_hw pwm_registers;
fake_pwm_hw* pwm_hw=&pwm_registers;
static uint32_t test_time=UINT32_MAX-50, fade_started, off_level;
static bool capture_fade;
static std::vector<uint32_t> fade_levels;
uint32_t time_us_32() { return test_time; }
void busy_wait_us_32(uint32_t us) { assert(core1);test_time+=us; }
alarm_pool_t* alarm_pool_create_with_unused_hardware_alarm(unsigned n) {
    assert(core1 && n==2 && !pool_live);static alarm_pool_t pool;++pools;pool_live=true;return &pool;
}
void alarm_pool_destroy(alarm_pool_t* pool) {
    assert(core1 && pool && pool_live && (!alarm || !alarm->callback));
    pool_live=false;++pool_destroys;
}
bool alarm_pool_add_repeating_timer_us(alarm_pool_t*,int64_t delay,repeating_timer_callback_t cb,void*,repeating_timer* timer) {
    assert(core1 && delay==-40);alarm=timer;
    timer->callback=timer_failure?nullptr:cb;return !timer_failure;
}
bool cancel_repeating_timer(repeating_timer* t) { assert(core1 && t==alarm);t->callback=nullptr;++cancels;return true; }
void gpio_init(unsigned) { assert(core1); }
void gpio_set_dir(unsigned,bool) { assert(core1); }
void gpio_put(unsigned,bool value) { assert(core1 && !value);++disabled; }
void gpio_set_function(unsigned,unsigned) { assert(core1); }
unsigned pwm_gpio_to_slice_num(unsigned pin) { assert(pin==26);return 5; }
void pwm_set_both_levels(unsigned slice,uint16_t left,uint16_t right) {
    assert(core1 && slice==5);left_level=left;right_level=right;
    const uint32_t levels=left|(uint32_t(right)<<16);
    pwm_hw->slice[slice].cc=levels;
    if(capture_fade) fade_levels.push_back(levels);
}
void pwm_set_enabled(unsigned slice,bool value) {
    assert(core1);
    if(capture_fade && enabled && !value) off_level=pwm_hw->slice[slice].cc;
    enabled=value;
}
void pwm_set_clkdiv_int_frac4(unsigned slice,unsigned whole,unsigned fraction) {
    assert(core1 && slice==5);
#if MK61_PICOCALC_AUTOMATIC_AUDIO_CLOCK
    const auto* plan=picocalc::cosmic_clock::find(clock_mhz);
    assert(whole==plan->pwm_div16/16 && fraction==plan->pwm_div16%16);
#elif defined(TEST_CLOCK_MHZ)
    const auto* plan=picocalc::cosmic_clock::find(TEST_CLOCK_MHZ);
    assert(whole==plan->pwm_div16/16 && fraction==plan->pwm_div16%16);
#else
    assert(whole==1 && fraction==0);
#endif
}
void pwm_set_wrap(unsigned,unsigned n) { assert(core1 && (n==255 || n==1023));pwm_wrap=n; }
static picocalc::audio::Plan existing_tone;
namespace picocalc::script {
void tone(unsigned f,unsigned ms,unsigned) { assert(!audio_stream::active() && !f && !ms);existing_tone={}; }
audio::Plan tone_status() { return existing_tone; }
}
namespace picocalc::io_worker {
void service(bool) { assert(core1); }
void invoke(void* ctx,void (*fn)(void*)) {
    std::thread worker([=] { std::lock_guard<std::mutex> lock(executor);core1=true;fn(ctx); });worker.join();
}
}
static void trace_close() {
    assert(enabled);
    fade_started=time_us_32();off_level=UINT32_MAX;
    fade_levels={pwm_hw->slice[5].cc};capture_fade=true;
}
static void check_fade() {
    capture_fade=false;
    assert(!enabled && off_level==0 && fade_levels.size()>2 && fade_levels.back()==0);
    const auto elapsed=time_us_32()-fade_started;
    assert(elapsed>=20000 && elapsed<35000);
    for(unsigned i=1;i<fade_levels.size();++i) for(unsigned shift:{0u,16u}) {
        const unsigned before=uint16_t(fade_levels[i-1]>>shift);
        const unsigned after=uint16_t(fade_levels[i]>>shift);
        assert(after<=before && before-after<=4*(pwm_wrap+1)/256);
    }
}
static bool sample() {
    bool again=false;
    std::thread irq([&] { std::lock_guard<std::mutex> lock(executor);core1=true;
        assert(alarm && alarm->callback);again=alarm->callback(alarm);
        if(!again) alarm->callback=nullptr;
    });irq.join();return again;
}
struct Synth { std::atomic<bool> entered{false},release{false};bool block=false;unsigned calls=0,recoveries=0; };
static uint32_t render(void* raw) {
    auto& s=*(Synth*)raw;assert(core1);++s.calls;s.entered.store(true,std::memory_order_release);
    while(s.block && !s.release.load(std::memory_order_acquire)) std::this_thread::yield();
    return 0x80007FFF;
}
int main() {
    using namespace picocalc::audio_stream;
    using picocalc::audio::KeyClick;
    mk61_service_audio r{};r.rate=25000;r.volume=100;assert(call(MK61_AUDIO_OPEN,&r,10));
    assert(active() && enabled && pools==1);sample();assert(left_level==128 && right_level==128);
    const int16_t data[]={32767,-32768};r.samples=data;r.count=2;assert(call(MK61_AUDIO_WRITE,&r,10) && r.count==2);
    sample();assert(left_level==191 && right_level==191);sample();assert(left_level==64 && right_level==64);
    sample();assert(left_level==128);assert(call(MK61_AUDIO_STATUS,&r,10) && r.underruns==1);
    trace_close();close();check_fade();
    assert(!active() && !enabled && cancels==1 && disabled==2 && !pool_live && pool_destroys==1);
    Synth state;mk61_service_audio_synth request{render,&state,25000,100};assert(synth(request,10));
#if MK61_PICOCALC_AUTOMATIC_AUDIO_CLOCK
    assert(clock_mhz==200 && boosts==1 && !restores);
#endif
    sample();assert(state.calls==1 && left_level==191 && right_level==64);
    assert(call(MK61_AUDIO_STATUS,&r,10) && !r.queued);request.rate=44100;assert(!synth(request,10));assert(active());
    // Closing on core 0 waits for an in-flight core-1 callback. Its context
    // may be released as soon as close returns, including APP code/data.
    state.block=true;state.entered.store(false);std::atomic<bool> closed{false};
    std::thread irq([] { std::lock_guard<std::mutex> lock(executor);core1=true;assert(alarm->callback(alarm)); });
    while(!state.entered.load(std::memory_order_acquire)) std::this_thread::yield();
    trace_close();
    std::thread closer([&] { close();closed.store(true,std::memory_order_release); });
    assert(!closed.load());state.release.store(true,std::memory_order_release);irq.join();closer.join();
    assert(closed.load() && !active() && !enabled && !alarm->callback && cancels==2 && !pool_live && pool_destroys==pools);
    check_fade();
    close();assert(cancels==2);
    existing_tone.wrap=100;assert(!key_click());existing_tone={};
    existing_tone.software=true;assert(!key_click());existing_tone={};
    assert(key_click() && !active() && enabled && left_level==0 && pool_live);
    for(unsigned n=0;n<KeyClick::SAMPLES;++n) {
        assert(sample()==(n+1<KeyClick::SAMPLES));
        assert(left_level==right_level && left_level<=63);
        if(n==0 || n+1==KeyClick::SAMPLES) assert(!left_level);
    }
    auto clicks=key_click_statistics();
    assert(!clicks.active && clicks.started==1 && clicks.completed==1 && !enabled && !alarm->callback && pool_live);
    // A finished key click can leave the pool idle; the next APP loader
    // explicitly closes it before allocating its image.
    close();assert(!pool_live && pool_destroys==pools);
    assert(key_click());sample();assert(key_click()); // Retrigger restarts the finite impulse.
    for(unsigned n=0;n<KeyClick::SAMPLES;++n) sample();
    clicks=key_click_statistics();assert(clicks.started==3 && clicks.completed==2 && !clicks.active);
    assert(key_click());sample();stop_key_click();
    assert(!key_click_statistics().active && !enabled && !alarm->callback);
    assert(key_click());r={};r.rate=25000;r.volume=100;
    assert(call(MK61_AUDIO_OPEN,&r,10) && active() && !key_click_statistics().active);
    const auto before=key_click_statistics().started;
    assert(!key_click());stop_key_click();assert(active() && key_click_statistics().started==before);
    sample();assert(left_level==128 && right_level==128);close();
    timer_failure=true;assert(!key_click() && !enabled && !key_click_statistics().active);
    timer_failure=false;assert(key_click());close();assert(!enabled && !alarm->callback && !pool_live && pool_destroys==pools);
    request.rate=25000;timer_failure=true;
    assert(!synth(request,10) && !active() && !enabled);
    timer_failure=false;
#if MK61_PICOCALC_AUTOMATIC_AUDIO_CLOCK
    assert(clock_mhz==125 && boosts==2 && restores==2);
    clock_failure=true;assert(!synth(request,10) && !active());
    assert(clock_mhz==125 && boosts==restores);
#endif
    // Strict remote playback never boosts or silently recovers into local
    // audio. Ordinary remote playback retains its established local fallback.
    uint8_t bodies[2][132]{},events[8]{},running=1,dac[3]{0,128,128};
    uint32_t read=0,write=0,produced=0,time=0;int32_t dc_in=0,dc_out=0;
    mk61_service_audio_psg psg_request{};psg_request.local=request;psg_request.module_path="AY.S3M";
    psg_request.psg[0]=bodies[0];psg_request.psg[1]=bodies[1];psg_request.psg_bytes=132;
    psg_request.events=events;psg_request.event_capacity=1;psg_request.read=&read;psg_request.write=&write;
    psg_request.produced=&produced;psg_request.time=&time;psg_request.running=&running;psg_request.dac=dac;
    psg_request.dc_input=&dc_in;psg_request.dc_output=&dc_out;
    psg_request.recover=[](void* raw){assert(!core1 && !picocalc::m3_audio::opened);++((Synth*)raw)->recoveries;};
    const auto old_fallbacks=synth_statistics().fallbacks;
#if MK61_PICOCALC_AUTOMATIC_AUDIO_CLOCK
    clock_failure=false;const unsigned old_boosts=boosts;
#endif
    assert(!psg(psg_request,10,true) && !active());
    picocalc::m3_audio::available=true;
    assert(psg(psg_request,10,true)==2 && active());sample();
    assert(left_level==128 && right_level==128);
    trace_close();close();check_fade();
    assert(!active() && !picocalc::m3_audio::opened);
    assert(psg(psg_request,10,true)==2 && active());sample();
    picocalc::m3_audio::broken=true;poll();
    assert(!active() && !picocalc::m3_audio::opened && state.recoveries==1);
    assert(synth_statistics().fallbacks==old_fallbacks);
#if MK61_PICOCALC_AUTOMATIC_AUDIO_CLOCK
    assert(clock_mhz==125 && boosts==old_boosts);
#endif
    assert(psg(psg_request,10)==2 && active());picocalc::m3_audio::broken=true;poll();
    assert(active() && state.recoveries==2 && synth_statistics().fallbacks==old_fallbacks+1);
#if MK61_PICOCALC_AUTOMATIC_AUDIO_CLOCK
    assert(clock_mhz==200 && boosts==old_boosts+1);
#endif
    close();assert(!active());
    // Preparing allocates the required queue and timer pool without starting
    // playback. UI key sounds cannot destroy the reserved queue.
    r={};r.rate=25000;r.volume=100;
    assert(call(MK61_AUDIO_PREPARE,&r,10) && !active() && !enabled && prepared_queue);
    auto* reserved=prepared_queue;const auto creates_before_open=pools,destroys_before_open=pool_destroys;
    assert(key_click());sample();stop_key_click();assert(prepared_queue==reserved);
    assert(call(MK61_AUDIO_OPEN,&r,10) && active() && !prepared_queue && queue==reserved);
    assert(pool_live && pools==creates_before_open && pool_destroys==destroys_before_open);
    sample();close();assert(!queue && !prepared_queue && !active() && !pool_live && pool_destroys==pools);
    assert(call(MK61_AUDIO_PREPARE,&r,10) && prepared_queue && pool_live);close();assert(!prepared_queue && !pool_live);
    assert(call(MK61_AUDIO_PREPARE,&r,10));timer_failure=true;
    assert(!call(MK61_AUDIO_OPEN,&r,10) && !prepared_queue && !queue && !active() && !pool_live);
    timer_failure=false;
    request={[](void*) -> uint32_t { return 0x80000080u; },nullptr,25000,100};
    assert(synth(request,10,true) && pwm_wrap==1023 && left_level==512 && right_level==512);
    sample();assert(left_level==513 && right_level==256);
    assert(call(MK61_AUDIO_STATUS,&r,10) && r.rate==25000);
    trace_close();close();check_fade();
    assert(key_click() && pwm_wrap==255);stop_key_click();close();
    puts("Core-1 PCM/synth ownership, stereo shutdown ramp, remote recovery, finite clicks and APP unload: PASS");
    return 0;
}

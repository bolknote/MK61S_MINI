#include "pico/stdlib.h"
#include <atomic>
#include <cassert>
#include <cstdio>
#include <mutex>
#include <thread>
#include "audio.hpp"
#if defined(TEST_CLOCK_MHZ)
#include "cosmic_clock_plan.hpp"
namespace picocalc::cosmic_clock {
uint32_t pwm_divider16() { return find(TEST_CLOCK_MHZ)->pwm_div16; }
}
#endif
#define MK61_PICOCALC_SCRIPT_HPP
namespace picocalc::script { void tone(unsigned,unsigned,unsigned=100);audio::Plan tone_status(); }
#include "../ports/picocalc/audio_stream.cpp"
static thread_local bool core1=false;
static std::mutex executor;
static repeating_timer* alarm;
static unsigned pools,cancels,left_level,right_level,disabled;
static bool enabled;
static bool timer_failure;
alarm_pool_t* alarm_pool_create_with_unused_hardware_alarm(unsigned n) {
    assert(core1 && n==2);static alarm_pool_t pool;++pools;return &pool;
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
void pwm_set_both_levels(unsigned slice,uint16_t left,uint16_t right) { assert(core1 && slice==5);left_level=left;right_level=right; }
void pwm_set_enabled(unsigned,bool value) { assert(core1);enabled=value; }
void pwm_set_clkdiv_int_frac4(unsigned slice,unsigned whole,unsigned fraction) {
    assert(core1 && slice==5);
#if defined(TEST_CLOCK_MHZ)
    const auto* plan=picocalc::cosmic_clock::find(TEST_CLOCK_MHZ);
    assert(whole==plan->pwm_div16/16 && fraction==plan->pwm_div16%16);
#else
    assert(whole==1 && fraction==0);
#endif
}
void pwm_set_wrap(unsigned,unsigned n) { assert(core1 && n==255); }
static picocalc::audio::Plan existing_tone;
namespace picocalc::script {
void tone(unsigned f,unsigned ms,unsigned) { assert(!audio_stream::active() && !f && !ms);existing_tone={}; }
audio::Plan tone_status() { return existing_tone; }
}
namespace picocalc::io_worker {
void invoke(void* ctx,void (*fn)(void*)) {
    std::thread worker([=] { std::lock_guard<std::mutex> lock(executor);core1=true;fn(ctx); });worker.join();
}
}
static bool sample() {
    bool again=false;
    std::thread irq([&] { std::lock_guard<std::mutex> lock(executor);core1=true;
        assert(alarm && alarm->callback);again=alarm->callback(alarm);
        if(!again) alarm->callback=nullptr;
    });irq.join();return again;
}
struct Synth { std::atomic<bool> entered{false},release{false};bool block=false;unsigned calls=0; };
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
    close();assert(!active() && !enabled && cancels==1 && disabled==2);
    Synth state;mk61_service_audio_synth request{render,&state,25000,100};assert(synth(request,10));
    sample();assert(state.calls==1 && left_level==191 && right_level==64);
    assert(call(MK61_AUDIO_STATUS,&r,10) && !r.queued);request.rate=44100;assert(!synth(request,10));assert(active());
    // Closing on core 0 waits for an in-flight core-1 callback. Its context
    // may be released as soon as close returns, including APP code/data.
    state.block=true;state.entered.store(false);std::atomic<bool> closed{false};
    std::thread irq([] { std::lock_guard<std::mutex> lock(executor);core1=true;assert(alarm->callback(alarm)); });
    while(!state.entered.load(std::memory_order_acquire)) std::this_thread::yield();
    std::thread closer([&] { close();closed.store(true,std::memory_order_release); });
    assert(!closed.load());state.release.store(true,std::memory_order_release);irq.join();closer.join();
    assert(closed.load() && !active() && !enabled && !alarm->callback && cancels==2 && pools==1);
    close();assert(cancels==2);
    existing_tone.wrap=100;assert(!key_click());existing_tone={};
    existing_tone.software=true;assert(!key_click());existing_tone={};
    assert(key_click() && !active() && enabled && left_level==0 && pools==1);
    for(unsigned n=0;n<KeyClick::SAMPLES;++n) {
        assert(sample()==(n+1<KeyClick::SAMPLES));
        assert(left_level==right_level && left_level<=63);
        if(n==0 || n+1==KeyClick::SAMPLES) assert(!left_level);
    }
    auto clicks=key_click_statistics();
    assert(!clicks.active && clicks.started==1 && clicks.completed==1 && !enabled && !alarm->callback);
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
    timer_failure=false;assert(key_click());close();assert(!enabled && !alarm->callback && pools==1);
    puts("Core-1 PCM/synth ownership, finite key clicks, retrigger, priority, timer failure and APP unload: PASS");
}

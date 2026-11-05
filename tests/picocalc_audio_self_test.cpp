#include "pico/stdlib.h"
#include <atomic>
#include <cassert>
#include <cstdio>
#include <mutex>
#include <thread>
#define MK61_PICOCALC_SCRIPT_HPP
namespace picocalc::script { void tone(unsigned,unsigned,unsigned=100); }
#include "../ports/picocalc/audio_stream.cpp"
static thread_local bool core1=false;
static std::mutex executor;
static repeating_timer* alarm;
static unsigned pools,cancels,left_level,right_level,disabled;
static bool enabled;
alarm_pool_t* alarm_pool_create_with_unused_hardware_alarm(unsigned n) {
    assert(core1 && n==2);static alarm_pool_t pool;++pools;return &pool;
}
bool alarm_pool_add_repeating_timer_us(alarm_pool_t*,int64_t delay,repeating_timer_callback_t cb,void*,repeating_timer* timer) {
    assert(core1 && delay==-40);timer->callback=cb;alarm=timer;return true;
}
bool cancel_repeating_timer(repeating_timer* t) { assert(core1 && t==alarm);t->callback=nullptr;++cancels;return true; }
void gpio_init(unsigned) { assert(core1); }
void gpio_set_dir(unsigned,bool) { assert(core1); }
void gpio_put(unsigned,bool value) { assert(core1 && !value);++disabled; }
void gpio_set_function(unsigned,unsigned) { assert(core1); }
unsigned pwm_gpio_to_slice_num(unsigned pin) { assert(pin==26);return 5; }
void pwm_set_both_levels(unsigned slice,uint16_t left,uint16_t right) { assert(core1 && slice==5);left_level=left;right_level=right; }
void pwm_set_enabled(unsigned,bool value) { assert(core1);enabled=value; }
void pwm_set_clkdiv_int_frac4(unsigned,unsigned,unsigned) { assert(core1); }
void pwm_set_wrap(unsigned,unsigned n) { assert(core1 && n==255); }
namespace picocalc::script { void tone(unsigned f,unsigned ms,unsigned) { assert(!audio_stream::active() && !f && !ms); } }
namespace picocalc::io_worker {
void invoke(void* ctx,void (*fn)(void*)) {
    std::thread worker([=] { std::lock_guard<std::mutex> lock(executor);core1=true;fn(ctx); });worker.join();
}
}
static void sample() {
    std::thread irq([] { std::lock_guard<std::mutex> lock(executor);core1=true;assert(alarm && alarm->callback);assert(alarm->callback(alarm)); });irq.join();
}
struct Synth { std::atomic<bool> entered{false},release{false};bool block=false;unsigned calls=0; };
static uint32_t render(void* raw) {
    auto& s=*(Synth*)raw;assert(core1);++s.calls;s.entered.store(true,std::memory_order_release);
    while(s.block && !s.release.load(std::memory_order_acquire)) std::this_thread::yield();
    return 0x80007FFF;
}
int main() {
    using namespace picocalc::audio_stream;
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
    close();assert(cancels==2);puts("Core-1 PCM/synth timer ownership, PWM range, silence and draining before APP unload: PASS");
}

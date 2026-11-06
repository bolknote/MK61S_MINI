#include "audio_stream.hpp"
#include "pcm_queue.hpp"
#include "key_click.hpp"
#include "script.hpp"
#include "io_worker.hpp"
#include "hardware/pwm.h"
#include "pico/stdlib.h"
#include <new>
namespace picocalc::audio_stream {
namespace {
Queue* queue=nullptr;
repeating_timer timer{};
alarm_pool_t* pool=nullptr;
mk61_service_audio_synth generator{};
enum class Playback : uint8_t { IDLE, STREAM, KEY_CLICK };
std::atomic<Playback> playback{Playback::IDLE};
std::atomic<uint32_t> clicks_started{0},clicks_completed{0};
audio::KeyClick click;
unsigned gain=0;
void silence_pwm() {
    pwm_set_enabled(pwm_gpio_to_slice_num(26),false);
    for(unsigned pin=26;pin<=27;++pin) { gpio_init(pin);gpio_set_dir(pin,GPIO_OUT);gpio_put(pin,false); }
}
bool tick(repeating_timer*) {
    const auto mode=playback.load(std::memory_order_acquire);
    if(mode==Playback::IDLE) return false;
    if(mode==Playback::KEY_CLICK) {
        const uint16_t level=(uint16_t)((uint32_t)click.next()/512u);
        pwm_set_both_levels(pwm_gpio_to_slice_num(26),level,level);
        if(!click.done()) return true;
        silence_pwm();
        clicks_completed.store(clicks_completed.load(std::memory_order_relaxed)+1,std::memory_order_release);
        playback.store(Playback::IDLE,std::memory_order_release);
        return false;
    }
    int32_t left,right;
    if(generator.sample) {
        const uint32_t samples=generator.sample(generator.context);
        left=(int16_t)samples;right=(int16_t)(samples>>16);
    } else left=right=queue->pop();
    // Match the existing conservative speaker duty range. The PCM center
    // is 50%, with at most +/-25% excursion.
    const int32_t l=128+(left*(int32_t)gain)/512000,r=128+(right*(int32_t)gain)/512000;
    pwm_set_both_levels(pwm_gpio_to_slice_num(26),(uint16_t)l,(uint16_t)r);
    return true;
}
bool start_timer() {
    if(!pool) pool=alarm_pool_create_with_unused_hardware_alarm(2);
    return pool && alarm_pool_add_repeating_timer_us(pool,-40,tick,nullptr,&timer);
}
void stop(void*) {
    if(playback.load(std::memory_order_acquire)==Playback::IDLE) return;
    cancel_repeating_timer(&timer);
    generator={};playback.store(Playback::IDLE,std::memory_order_release);
    silence_pwm();
    auto* old=queue;queue=nullptr;delete old;
}
void prepare_pwm(uint16_t center=128) {
    for(unsigned pin=26;pin<=27;++pin) gpio_set_function(pin,GPIO_FUNC_PWM);
    const unsigned slice=pwm_gpio_to_slice_num(26);
    pwm_set_enabled(slice,false);pwm_set_clkdiv_int_frac4(slice,1,0);pwm_set_wrap(slice,255);
    pwm_set_both_levels(slice,center,center);pwm_set_enabled(slice,true);
}
}
bool active() { return playback.load(std::memory_order_acquire)==Playback::STREAM; }
void close() { if(playback.load(std::memory_order_acquire)!=Playback::IDLE) io_worker::invoke(nullptr,stop); }
void stop_key_click() {
    if(playback.load(std::memory_order_acquire)==Playback::KEY_CLICK) io_worker::invoke(nullptr,stop);
}
KeyClickStatistics key_click_statistics() {
    return {clicks_started.load(std::memory_order_acquire),clicks_completed.load(std::memory_order_acquire),
            playback.load(std::memory_order_acquire)==Playback::KEY_CLICK};
}
bool key_click() {
    const auto tone=script::tone_status();
    if(active() || tone.wrap || tone.software) return false;
    bool ok=false;
    io_worker::invoke(&ok,[](void* raw) {
        if(active()) return;
        stop(nullptr);click.reset();prepare_pwm(0);
        playback.store(Playback::KEY_CLICK,std::memory_order_release);
        *(bool*)raw=start_timer();
        if(*(bool*)raw) clicks_started.store(clicks_started.load(std::memory_order_relaxed)+1,std::memory_order_release);
        else stop(nullptr);
    });
    return ok;
}
uint32_t synth(const mk61_service_audio_synth& r,unsigned master) {
    if(!r.sample || r.rate!=25000 || r.volume>100 || master>10) return 0;
    close();script::tone(0,0);generator=r;gain=master*r.volume;
    bool ok=false;
    io_worker::invoke(&ok,[](void* raw) {
        prepare_pwm();playback.store(Playback::STREAM,std::memory_order_release);
        *(bool*)raw=start_timer();if(!*(bool*)raw) stop(nullptr);
    });
    return ok;
}
uint32_t call(uint32_t operation,mk61_service_audio* request,unsigned master) {
    if(operation==MK61_AUDIO_CLOSE) { close();return 1; }
    if(!request) return 0;
    auto& r=*request;
    if(operation==MK61_AUDIO_OPEN) {
        if(r.rate!=25000 || r.volume>100 || master>10 || r.samples || r.count) return 0;
        close();script::tone(0,0);
        queue=new(std::nothrow) Queue;
        if(!queue) return 0;
        gain=master*r.volume;
        bool ok=false;
        io_worker::invoke(&ok,[](void* raw) {
            prepare_pwm();playback.store(Playback::STREAM,std::memory_order_release);
            *(bool*)raw=start_timer();if(!*(bool*)raw) stop(nullptr);
        });
        if(!ok) return 0;
    } else if(operation==MK61_AUDIO_WRITE) {
        if(!queue || r.count>Queue::CAPACITY || (!r.samples && r.count)) return 0;
        r.count=queue->push(r.samples,r.count);
    } else if(operation!=MK61_AUDIO_STATUS || !active()) return 0;
    if(!queue) { r.rate=25000;r.queued=r.underruns=0;return 1; }
    r.rate=25000;r.queued=queue->queued();r.underruns=queue->underruns.load(std::memory_order_relaxed);return 1;
}
}

#include "audio_stream.hpp"
#include "pcm_queue.hpp"
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
std::atomic<bool> running{false};
unsigned gain=0;
bool tick(repeating_timer*) {
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
    if(!running.load(std::memory_order_acquire)) return;
    cancel_repeating_timer(&timer);
    generator={};running.store(false,std::memory_order_release);
    pwm_set_enabled(pwm_gpio_to_slice_num(26),false);
    for(unsigned pin=26;pin<=27;++pin) { gpio_init(pin);gpio_set_dir(pin,GPIO_OUT);gpio_put(pin,false); }
    auto* old=queue;queue=nullptr;delete old;
}
void prepare_pwm() {
    for(unsigned pin=26;pin<=27;++pin) gpio_set_function(pin,GPIO_FUNC_PWM);
    const unsigned slice=pwm_gpio_to_slice_num(26);
    pwm_set_enabled(slice,false);pwm_set_clkdiv_int_frac4(slice,1,0);pwm_set_wrap(slice,255);
    pwm_set_both_levels(slice,128,128);pwm_set_enabled(slice,true);
}
}
bool active() { return running.load(std::memory_order_acquire); }
void close() { if(active()) io_worker::invoke(nullptr,stop); }
uint32_t synth(const mk61_service_audio_synth& r,unsigned master) {
    if(!r.sample || r.rate!=25000 || r.volume>100 || master>10) return 0;
    close();script::tone(0,0);generator=r;gain=master*r.volume;
    bool ok=false;
    io_worker::invoke(&ok,[](void* raw) {
        prepare_pwm();running.store(true,std::memory_order_release);
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
            prepare_pwm();running.store(true,std::memory_order_release);
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

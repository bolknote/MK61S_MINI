#include "audio_stream.hpp"
#include "cosmic_clock.hpp"
#include "pcm_queue.hpp"
#include "key_click.hpp"
#include "script.hpp"
#include "io_worker.hpp"
#include "m3_audio.hpp"
#include "psg_packets.hpp"
#include "pwm_duty_ring.hpp"
#include "hardware/pwm.h"
#include "pico/stdlib.h"
#include <new>
#ifndef MK61_PICOCALC_AUDIO_DMA
#define MK61_PICOCALC_AUDIO_DMA 0
#endif
#if MK61_PICOCALC_AUDIO_DMA || defined(PICO_ON_DEVICE)
#define MK61_PICOCALC_SYNTH_DMA 1
#include "hardware/clocks.h"
#include "hardware/dma.h"
#include "hardware/irq.h"
#include "hardware/sync.h"
#else
#define MK61_PICOCALC_SYNTH_DMA 0
#endif
namespace picocalc::audio_stream {
namespace {
Queue* queue=nullptr;
repeating_timer timer{};
alarm_pool_t* pool=nullptr;
mk61_service_audio_synth generator{};
bool generator_duties=false,remote=false;
bool clock_owned=false;
bool remote_only=false;
mk61_service_audio_psg recovery{};
unsigned recovery_master=0;
uint32_t fallbacks=0;
enum class Playback : uint8_t { IDLE, STREAM, KEY_CLICK };
std::atomic<Playback> playback{Playback::IDLE};
std::atomic<uint32_t> clicks_started{0},clicks_completed{0};
audio::KeyClick click;
unsigned gain=0;
std::atomic<uint32_t> synth_blocks{0},synth_underruns{0};
std::atomic<bool> synth_dma{false};
uint32_t pwm_sample(uint32_t samples) {
    const int32_t left=(int16_t)samples,right=(int16_t)(samples>>16);
    const uint16_t l=(uint16_t)(128+(left*(int32_t)gain)/512000);
    const uint16_t r=(uint16_t)(128+(right*(int32_t)gain)/512000);
    return l|(uint32_t(r)<<16);
}
#if MK61_PICOCALC_SYNTH_DMA
constexpr unsigned BLOCK_SAMPLES=16;
// Ring addressing bounds every DMA read even if an IRQ is delayed beyond
// a complete block. Such a missed refill is detected, counted and silenced.
alignas(BLOCK_SAMPLES*sizeof(uint32_t)) uint32_t dma_samples[2][BLOCK_SAMPLES];
int synth_channels[2]{-1,-1},synth_timer=-1;
unsigned next_completed=0;
bool synth_irq_installed=false;
void dma_quiesce() {
    synth_dma.store(false,std::memory_order_release);
    if(synth_timer>=0) dma_timer_set_fraction((unsigned)synth_timer,0,1);
    for(int channel:synth_channels) if(channel>=0) {
        dma_channel_set_irq1_enabled((unsigned)channel,false);
        auto config=dma_channel_get_default_config((unsigned)channel);
        channel_config_set_enable(&config,false);
        channel_config_set_chain_to(&config,(unsigned)channel);
        dma_channel_set_config((unsigned)channel,&config,false);
    }
    for(int channel:synth_channels) if(channel>=0) {
        dma_channel_abort((unsigned)channel);
        dma_channel_acknowledge_irq1((unsigned)channel);
    }
}
void dma_irq();
void dma_release() {
    dma_quiesce();
    if(synth_irq_installed) { irq_remove_handler(DMA_IRQ_1,dma_irq);synth_irq_installed=false; }
    for(int& channel:synth_channels) if(channel>=0) { dma_channel_unclaim((unsigned)channel);channel=-1; }
    if(synth_timer>=0) { dma_timer_unclaim((unsigned)synth_timer);synth_timer=-1; }
}
void dma_refill(unsigned index) {
    for(auto& sample:dma_samples[index]) {
        const uint32_t value=generator.sample(generator.context);
        sample=generator_duties?value:pwm_sample(value);
    }
    synth_blocks.fetch_add(1,std::memory_order_relaxed);
}
void dma_fault() {
    synth_underruns.fetch_add(1,std::memory_order_relaxed);
    dma_quiesce();
    // Keep the stream/context owned until close(). No callback may run
    // after its APP is unloaded, including after a failed hardware refill.
    pwm_set_both_levels(pwm_gpio_to_slice_num(26),128,128);
}
void dma_irq() {
    if(!synth_dma.load(std::memory_order_acquire)) return;
    const unsigned index=next_completed,channel=(unsigned)synth_channels[index];
    const unsigned other=(unsigned)synth_channels[index^1];
    const uint32_t mask=(1U<<channel)|(1U<<other);
    const uint32_t pending=dma_hw->ints1&mask;
    if(!pending) return; // Another owner's shared DMA IRQ.
    if(pending!=(1U<<channel)) { dma_fault();return; }
    // Pause this completed channel before touching its buffer. If its
    // peer finishes during rendering, chaining cannot read a partial block.
    auto config=dma_channel_get_default_config(channel);
    channel_config_set_enable(&config,false);
    dma_channel_set_config(channel,&config,false);
    dma_channel_acknowledge_irq1(channel);
    if(dma_channel_is_busy(channel)) { dma_fault();return; }
    dma_refill(index);
    if((dma_hw->ints1&(1U<<other)) || dma_channel_is_busy(channel)) { dma_fault();return; }
    dma_channel_set_read_addr(channel,dma_samples[index],false);
    dma_channel_set_trans_count(channel,BLOCK_SAMPLES,false);
    channel_config_set_transfer_data_size(&config,DMA_SIZE_32);
    channel_config_set_read_increment(&config,true);
    channel_config_set_write_increment(&config,false);
    channel_config_set_dreq(&config,dma_get_timer_dreq((unsigned)synth_timer));
    channel_config_set_ring(&config,false,6);
    channel_config_set_chain_to(&config,other);
    channel_config_set_enable(&config,true);
    __dmb();next_completed=index^1;
    dma_channel_set_config(channel,&config,false);
    // A chain trigger received with EN clear is discarded. The peer can
    // finish after our pending-IRQ check, during READ_ADDR/TRANS_COUNT or
    // immediately before this enable write. Never report a live DMA stream
    // with both channels idle after that lost trigger. A completed peer
    // must have started this fully published block by now.
    __dmb();
    if((dma_hw->ints1&(1U<<other)) && !dma_channel_is_busy(channel)) dma_fault();
}
bool start_dma() {
    synth_blocks.store(0,std::memory_order_relaxed);synth_underruns.store(0,std::memory_order_relaxed);
    const unsigned hz=clock_get_hz(clk_sys);
    if(!hz || hz%25000 || hz/25000>65535) return false;
    synth_channels[0]=dma_claim_unused_channel(false);
    if(synth_channels[0]>=0) synth_channels[1]=dma_claim_unused_channel(false);
    if(synth_channels[1]>=0) synth_timer=dma_claim_unused_timer(false);
    if(synth_timer<0) { dma_release();return false; }
    dma_timer_set_fraction((unsigned)synth_timer,0,1);
    dma_refill(0);dma_refill(1);
    for(unsigned index=0;index<2;++index) {
        const unsigned channel=(unsigned)synth_channels[index];
        auto config=dma_channel_get_default_config(channel);
        channel_config_set_transfer_data_size(&config,DMA_SIZE_32);
        channel_config_set_read_increment(&config,true);
        channel_config_set_write_increment(&config,false);
        channel_config_set_dreq(&config,dma_get_timer_dreq((unsigned)synth_timer));
        channel_config_set_ring(&config,false,6);
        channel_config_set_chain_to(&config,(unsigned)synth_channels[index^1]);
        dma_channel_configure(channel,&config,&pwm_hw->slice[pwm_gpio_to_slice_num(26)].cc,
            dma_samples[index],BLOCK_SAMPLES,false);
        dma_channel_acknowledge_irq1(channel);
        dma_channel_set_irq1_enabled(channel,true);
    }
    next_completed=0;
    irq_add_shared_handler(DMA_IRQ_1,dma_irq,PICO_SHARED_IRQ_HANDLER_DEFAULT_ORDER_PRIORITY);
    synth_irq_installed=true;irq_set_enabled(DMA_IRQ_1,true);
    synth_dma.store(true,std::memory_order_release);
    dma_start_channel_mask(1U<<(unsigned)synth_channels[0]);
    dma_timer_set_fraction((unsigned)synth_timer,1,(uint16_t)(hz/25000));return true;
}
#if defined(PICO_ON_DEVICE)
alignas(256) uint32_t remote_samples[DutyRing::SIZE];
DutyRing remote_ring;
int remote_channel=-1,remote_pacer=-1;
repeating_timer remote_alarm{};
bool remote_alarm_live=false;
void remote_quiesce() {
    synth_dma.store(false,std::memory_order_release);
    if(remote_pacer>=0)dma_timer_set_fraction((unsigned)remote_pacer,0,1);
    if(remote_channel>=0) {
        auto config=dma_channel_get_default_config((unsigned)remote_channel);
        channel_config_set_enable(&config,false);dma_channel_set_config((unsigned)remote_channel,&config,false);
        dma_channel_abort((unsigned)remote_channel);
    }
    pwm_set_both_levels(pwm_gpio_to_slice_num(26),128,128);
}
void remote_release() {
    if(remote_alarm_live){cancel_repeating_timer(&remote_alarm);remote_alarm_live=false;}
    remote_quiesce();
    if(remote_channel>=0){dma_channel_unclaim((unsigned)remote_channel);remote_channel=-1;}
    if(remote_pacer>=0){dma_timer_unclaim((unsigned)remote_pacer);remote_pacer=-1;}
}
bool remote_tick(repeating_timer* alarm) {
    if(!synth_dma.load(std::memory_order_acquire))return false;
    if(m3_audio::failed()){remote_quiesce();remote_alarm_live=false;return false;}
    const auto result=!dma_channel_is_busy((unsigned)remote_channel)?DutyRing::LATE:remote_ring.refill(remote_samples,[] {
        const uint32_t head=UINT32_MAX-dma_hw->ch[remote_channel].transfer_count;__dmb();return head;
    },[]{return m3_audio::duty(nullptr);});
    if(result==DutyRing::LATE) {
        synth_underruns.fetch_add(1,std::memory_order_relaxed);m3_audio::fault(-31);
        remote_quiesce();remote_alarm_live=false;return false;
    }
    alarm->delay_us=result==DutyRing::EARLY?-40:-1280;
    if(result==DutyRing::REFILLED)synth_blocks.fetch_add(1,std::memory_order_relaxed);
    return true;
}
bool start_remote_dma() {
    const unsigned hz=clock_get_hz(clk_sys);
    if(!hz || hz%25000 || hz/25000>65535)return false;
    synth_blocks.store(0,std::memory_order_relaxed);synth_underruns.store(0,std::memory_order_relaxed);
    remote_channel=dma_claim_unused_channel(false);
    if(remote_channel>=0)remote_pacer=dma_claim_unused_timer(false);
    if(remote_pacer<0){remote_release();return false;}
    if(!pool)pool=alarm_pool_create_with_unused_hardware_alarm(2);
    if(!pool){remote_release();return false;}
    dma_timer_set_fraction((unsigned)remote_pacer,0,1);
    remote_ring.prime(remote_samples,[]{return m3_audio::duty(nullptr);});
    auto config=dma_channel_get_default_config((unsigned)remote_channel);
    channel_config_set_transfer_data_size(&config,DMA_SIZE_32);
    channel_config_set_read_increment(&config,true);channel_config_set_write_increment(&config,false);
    channel_config_set_ring(&config,false,8);channel_config_set_dreq(&config,dma_get_timer_dreq((unsigned)remote_pacer));
    dma_channel_set_irq0_enabled((unsigned)remote_channel,false);dma_channel_set_irq1_enabled((unsigned)remote_channel,false);
    dma_channel_acknowledge_irq0((unsigned)remote_channel);dma_channel_acknowledge_irq1((unsigned)remote_channel);
    dma_channel_configure((unsigned)remote_channel,&config,&pwm_hw->slice[pwm_gpio_to_slice_num(26)].cc,
        remote_samples,UINT32_MAX,false);
    if(!alarm_pool_add_repeating_timer_us(pool,-1280,remote_tick,nullptr,&remote_alarm)){remote_release();return false;}
    remote_alarm_live=true;synth_dma.store(true,std::memory_order_release);
    dma_start_channel_mask(1U<<(unsigned)remote_channel);
    dma_timer_set_fraction((unsigned)remote_pacer,1,(uint16_t)(hz/25000));return true;
}
#endif
#endif
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
    uint32_t samples;
    if(generator.sample) {
        samples=generator.sample(generator.context);
    } else { const uint16_t mono=(uint16_t)queue->pop();samples=mono|(uint32_t(mono)<<16); }
    // Match the existing conservative speaker duty range. The PCM center
    // is 50%, with at most +/-25% excursion.
    const uint32_t levels=generator_duties?samples:pwm_sample(samples);
    pwm_set_both_levels(pwm_gpio_to_slice_num(26),(uint16_t)levels,(uint16_t)(levels>>16));
    return true;
}
bool start_timer() {
    if(!pool) pool=alarm_pool_create_with_unused_hardware_alarm(2);
    return pool && alarm_pool_add_repeating_timer_us(pool,-40,tick,nullptr,&timer);
}
void stop(void*) {
    bool dma_owned=false;
#if defined(PICO_ON_DEVICE)
    if(remote_channel>=0){remote_release();dma_owned=true;}
#endif
#if MK61_PICOCALC_SYNTH_DMA
    if(synth_timer>=0){dma_release();dma_owned=true;}
#endif
    if(!dma_owned && playback.load(std::memory_order_acquire)!=Playback::IDLE) cancel_repeating_timer(&timer);
    generator={};generator_duties=false;playback.store(Playback::IDLE,std::memory_order_release);
    silence_pwm();
    auto* old=queue;queue=nullptr;delete old;
}
void prepare_pwm(uint16_t center=128) {
    for(unsigned pin=26;pin<=27;++pin) gpio_set_function(pin,GPIO_FUNC_PWM);
    const unsigned slice=pwm_gpio_to_slice_num(26);
    pwm_set_enabled(slice,false);
#if MK61_PICOCALC_MANAGED_CLOCK
    const unsigned divider=cosmic_clock::pwm_divider16();pwm_set_clkdiv_int_frac4(slice,divider/16,divider%16);
#else
    pwm_set_clkdiv_int_frac4(slice,1,0);
#endif
    pwm_set_wrap(slice,255);
    pwm_set_both_levels(slice,center,center);pwm_set_enabled(slice,true);
}
}
bool active() { return playback.load(std::memory_order_acquire)==Playback::STREAM; }
void close() {
    if(playback.load(std::memory_order_acquire)!=Playback::IDLE) io_worker::invoke(nullptr,stop);
    m3_audio::close();remote=false;remote_only=false;recovery={};
    cosmic_clock::audio_end();
    clock_owned=false;
}
void stop_key_click() {
    if(playback.load(std::memory_order_acquire)==Playback::KEY_CLICK) io_worker::invoke(nullptr,stop);
}
KeyClickStatistics key_click_statistics() {
    return {clicks_started.load(std::memory_order_acquire),clicks_completed.load(std::memory_order_acquire),
            playback.load(std::memory_order_acquire)==Playback::KEY_CLICK};
}
SynthStatistics synth_statistics() {
    return {synth_dma.load(std::memory_order_acquire),synth_blocks.load(std::memory_order_relaxed),
            synth_underruns.load(std::memory_order_relaxed),remote,fallbacks};
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
namespace {
uint32_t start_generator(const mk61_service_audio_synth& r,unsigned master,bool boost,bool duties) {
    if(!r.sample || r.rate!=25000 || r.volume>100 || master>10) return 0;
    if(boost && !clock_owned) {
        if(!cosmic_clock::audio_begin())return 0;
        clock_owned=true;
    }
    generator=r;gain=master*r.volume;generator_duties=duties;
    bool ok=false;
    io_worker::invoke(&ok,[](void* raw) {
        prepare_pwm();playback.store(Playback::STREAM,std::memory_order_release);
#if MK61_PICOCALC_SYNTH_DMA
#if defined(PICO_ON_DEVICE)
        if(generator_duties && start_remote_dma()) { *(bool*)raw=true;return; }
#endif
        if(MK61_PICOCALC_AUDIO_DMA && !generator_duties && start_dma()) { *(bool*)raw=true;return; }
#endif
        *(bool*)raw=start_timer();if(!*(bool*)raw) stop(nullptr);
    });
    if(!ok && boost){cosmic_clock::audio_end();clock_owned=false;}
    return ok;
}
}
uint32_t synth(const mk61_service_audio_synth& r,unsigned master) {
    if(!r.sample || r.rate!=25000 || r.volume>100 || master>10)return 0;
    close();script::tone(0,0);return start_generator(r,master,true,false);
}
uint32_t psg(const mk61_service_audio_psg& r,unsigned master,bool required,const mk61_service_audio_psg_config* config) {
    if(!psg_packets::valid(r) || !psg_packets::valid(psg_packets::options(config)) || !r.recover || master>10)return 0;
    close();script::tone(0,0);
    if(m3_audio::open(r,master*r.local.volume,config)) {
        recovery=r;recovery_master=master;remote=true;remote_only=required;
        const mk61_service_audio_synth output{m3_audio::duty,nullptr,25000,100};
        if(start_generator(output,master,false,true))return 2;
        m3_audio::close();remote=false;remote_only=false;recovery={};
    }
    if(required)return 0;
    return start_generator(r.local,master,true,false);
}
void poll() {
    if(!remote || !m3_audio::failed())return;
    const auto saved=recovery;const unsigned master=recovery_master;
    const bool required=remote_only;
    if(active())io_worker::invoke(nullptr,stop);
    m3_audio::close();remote=false;remote_only=false;recovery={};
    saved.recover(saved.local.context);
    if(required)return;
    ++fallbacks;
    (void)start_generator(saved.local,master,true,false);
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
    if(!queue) { r.rate=25000;r.queued=0;r.underruns=synth_underruns.load(std::memory_order_relaxed);return 1; }
    r.rate=25000;r.queued=queue->queued();r.underruns=queue->underruns.load(std::memory_order_relaxed);return 1;
}
}

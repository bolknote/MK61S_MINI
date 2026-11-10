#!/usr/bin/env python3
"""Execute production I2C service/finish bodies with deterministic IRQ ordering."""
from pathlib import Path
import os
import subprocess
import tempfile

ROOT = Path(__file__).resolve().parents[1]
source = (ROOT / 'ports/picocalc/io_worker.cpp').read_text()


def body(text, begin, end):
    return text[text.index(begin):text.index(end)]


production = body(source, 'u32 i2c_irq_mask() {', 'struct I2cBus {')
production += body(source, 'void finish_i2c() {', 'void i2c_timeout(unsigned) {')
production += body(source, 'void service(bool allow_i2c) {', 'void wait_for_progress() {')
production = production.replace('void service(bool allow_i2c)', 'void new_service(bool allow_i2c)')
TEST = r'''
#include "i2c_transfer.hpp"
#include "selective_irq_mask.hpp"
#include "worker_deadline_trace.hpp"
#include "pwm_duty_ring.hpp"
#include <atomic>
#include <array>
#include <cassert>
#include <cstdint>
#include <cstdio>
#include <cstring>
#include <deque>
#include <optional>
#include <vector>
using u32=uint32_t;using u64=uint64_t;
using picocalc::SelectiveIrqMask;using picocalc::WorkerDeadlineTrace;
using picocalc::audio_stream::DutyRing;
constexpr unsigned TIMER_IRQ_0=0,I2C1_IRQ=24,PWM_IRQ=3;
constexpr u32 I2C_BIT=1u<<I2C1_IRQ,WAKE_BIT=1u<<2,PWM_BIT=1u<<PWM_IRQ,OTHER_BIT=1u<<12;
constexpr u32 CLOCKS_SLEEP_EN0_CLK_SYS_I2C1_BITS=128;
enum {IDLE,QUEUED,WORKING,DONE};
struct {std::atomic<unsigned> stage{IDLE};bool read=true;unsigned length=2;uint8_t bytes[2]{};int result=0;} i2c;
picocalc::I2cTransfer i2c_transfer;
WorkerDeadlineTrace deadline_trace;
struct DeadlineClock {u32 operator()()const;};
using DeadlineScope=WorkerDeadlineTrace::Scope<DeadlineClock>;
u64 now=0,next_pwm=1280;u32 enabled=I2C_BIT|WAKE_BIT|PWM_BIT|OTHER_BIT,pending=0;
bool global_mask=false;unsigned priority=256,prepare_delay=0,finish_delay=0,sdk_mask_delay=0;
unsigned i2c_deliveries=0,pwm_deliveries=0,alarm_sets=0,cancels=0;
DutyRing ring;std::array<u32,64> duties{};DutyRing::Result pwm_result=DutyRing::EARLY;
std::atomic<u32> transactions{0},i2c_irqs{0},i2c_busy_us{0},i2c_timeouts{0},i2c_aborts{0},i2c_sleep_holds{0};
int i2c_alarm=2;
void pump();void spend(unsigned);void i2c_irq();
u32 time_us_32(){return (u32)now;}u64 time_us_64(){return now;}
u32 DeadlineClock::operator()()const{return time_us_32();}
u64 from_us_since_boot(u64 n){return n;}
u32 save_and_disable_interrupts(){const bool saved=global_mask;global_mask=true;return saved;}
void restore_interrupts(u32 saved){global_mask=saved;pump();}
void hardware_alarm_cancel(unsigned n){assert(n==2);++cancels;}
bool hardware_alarm_set_target(unsigned n,u64 target){
    assert(n==2);++alarm_sets;
    if(sdk_mask_delay){const auto saved=save_and_disable_interrupts();spend(sdk_mask_delay);restore_interrupts(saved);}
    return now>=target;
}
#define __sev() do {}while(0)
struct Lease {Lease(u32,u32){}bool temporary()const{return false;}};
std::optional<Lease> i2c_sleep_clocks;
struct IrqPort {
    u32 enabled()const{return ::enabled;}
    void disable(u32 mask){::enabled&=~mask;}
    void enable(u32 mask){::enabled|=mask;pump();}
} i2c_irq_port;
using I2cIrqPort=IrqPort;
void drain_uart(){}
namespace m3_audio {void service(){}}
struct Bus {
    unsigned flags_=0,resets=0;std::deque<uint8_t> rx;std::vector<unsigned> commands;
    void prepare(bool){flags_=0;rx.clear();commands.clear();spend(prepare_delay);}
    void put(unsigned command){
        commands.push_back(command);
        if(command&picocalc::I2cTransfer::END){
            flags_=picocalc::I2cTransfer::STOP;rx={7,9};pending|=I2C_BIT;pump();
        }
    }
    unsigned flags(){return flags_;}bool available(){return !rx.empty();}
    uint8_t get(){auto value=rx.front();rx.pop_front();return value;}
    void finish(bool failed){
        if(failed){++resets;deadline_trace.reset_controller();}
        spend(finish_delay);flags_=0;rx.clear();
    }
} i2c_bus;
#include "production.inc"
void pwm_irq(){
    ++pwm_deliveries;
    pwm_result=ring.refill_block(duties.data(),[]{return u32(now/40);},[](u32* out,unsigned n){
        for(unsigned i=0;i<n;++i)out[i]=i;spend(100);
    });
    if(pwm_result==DutyRing::LATE)deadline_trace.audio_fault(time_us_32());
}
void pump(){
    if(global_mask)return;
    if((pending&enabled&PWM_BIT) && priority>0){
        pending&=~PWM_BIT;const auto old=priority;priority=0;pwm_irq();priority=old;
    }
    if((pending&enabled&I2C_BIT) && priority>128){
        pending&=~I2C_BIT;const auto old=priority;priority=128;++i2c_deliveries;i2c_irq();priority=old;
    }
}
void spend(unsigned work){
    while(work){
        if(next_pwm<=now){pending|=PWM_BIT;next_pwm=UINT64_MAX;pump();continue;}
        const auto n=unsigned(next_pwm-now<work?next_pwm-now:work);
        now+=n;work-=n;
        if(now==next_pwm){pending|=PWM_BIT;next_pwm=UINT64_MAX;pump();}
    }
}
void reset(){
    now=0;next_pwm=1280;enabled=I2C_BIT|WAKE_BIT|PWM_BIT|OTHER_BIT;pending=0;priority=256;global_mask=false;
    prepare_delay=finish_delay=sdk_mask_delay=0;i2c_deliveries=pwm_deliveries=alarm_sets=cancels=0;
    i2c.stage=IDLE;i2c.read=true;i2c.length=2;i2c.result=0;i2c_transfer=picocalc::I2cTransfer{};i2c_bus=Bus{};
    deadline_trace.mark=0;deadline_trace.fault_site=0;deadline_trace.fault_age_us=0;deadline_trace.resets=0;
    i2c_sleep_clocks.reset();ring.prime_block(duties.data(),[](u32* p,unsigned n){for(unsigned i=0;i<n;++i)p[i]=i;});
    pwm_result=DutyRing::EARLY;
}
// Previous ordering as a negative control: a global mask surrounds the
// same production completion/start path. Payload/timer/error handling are
// identical to the production function above.
void old_service(){
    drain_uart();m3_audio::service();const auto saved=save_and_disable_interrupts();
    finish_i2c();
    if(i2c.stage==QUEUED){
        i2c.stage=WORKING;i2c_sleep_clocks.emplace(CLOCKS_SLEEP_EN0_CLK_SYS_I2C1_BITS,0);
        i2c_transfer.begin(i2c_bus,i2c.read,i2c.bytes,i2c.length,time_us_64());
        if(i2c_alarm>=0)hardware_alarm_set_target((unsigned)i2c_alarm,from_us_since_boot(i2c_transfer.deadline()));
    }
    restore_interrupts(saved);
}
int main(){
    static_assert(sizeof(WorkerDeadlineTrace)==16);
    for(bool old:{true,false})for(bool recovery:{false,true}){
        reset();
        if(recovery){
            assert(i2c_transfer.begin(i2c_bus,true,nullptr,2,0));pending=0;
            i2c.stage=WORKING;i2c_bus.flags_=picocalc::I2cTransfer::ABORT;finish_delay=750;
        }else{i2c.stage=QUEUED;prepare_delay=750;}
        now=1260;
        if(old)old_service();else new_service(true);
        assert(pwm_deliveries==1 && !global_mask && enabled==(I2C_BIT|WAKE_BIT|PWM_BIT|OTHER_BIT));
        assert(pwm_result==(old?DutyRing::LATE:DutyRing::REFILLED));
        if(recovery)assert(i2c.result==-1 && i2c.stage==DONE && i2c_bus.resets==1 && deadline_trace.resets==1);
        else assert(i2c.result==2 && i2c.bytes[0]==7 && i2c.bytes[1]==9 && i2c.stage==DONE && i2c_deliveries==1);
        assert(deadline_trace.mark==0);
    }
    // A long inner SDK PRIMASK still fails. The diagnostic must identify
    // ALARM, rather than conceal the failure or spin waiting for a writer.
    reset();i2c.stage=QUEUED;sdk_mask_delay=750;now=1260;new_service(true);
    assert(pwm_result==DutyRing::LATE && deadline_trace.fault_site==WorkerDeadlineTrace::ALARM);
    assert(deadline_trace.fault_age_us>=750 && !deadline_trace.mark);
    // Nested peripheral masks retain pending STOPs and pre-disabled IRQs.
    reset();enabled&=~WAKE_BIT;
    {SelectiveIrqMask<IrqPort> first(i2c_irq_port,I2C_BIT|WAKE_BIT);
     {SelectiveIrqMask<IrqPort> nested(i2c_irq_port,I2C_BIT|WAKE_BIT);pending|=WAKE_BIT;}
     assert(!(enabled&(I2C_BIT|WAKE_BIT)) && (pending&WAKE_BIT));}
    assert((enabled&I2C_BIT) && !(enabled&WAKE_BIT) && (pending&WAKE_BIT));
    // Single-word timestamp publication and nesting survive both28-bit and32-bit wrap.
    for(u32 origin:{0x0ffffff0u,0xfffffff0u}){
        reset();now=origin;
        {DeadlineScope outer(deadline_trace,WorkerDeadlineTrace::SERVICE,DeadlineClock{});now+=10;
         {DeadlineScope inner(deadline_trace,WorkerDeadlineTrace::ALARM,DeadlineClock{});now+=25;
          deadline_trace.audio_fault(time_us_32());assert(deadline_trace.fault_site==4 && deadline_trace.fault_age_us==25);}
         now+=5;}
        assert(!deadline_trace.mark);
    }
    std::puts("Production I2C/PWM: pending STOP and reset serialization, high-priority preemption during750us begin/recovery, exact IRQ restoration/nesting, packed trace wrap; inner SDK PRIMASK remains a visible ALARM fault PASS");
}
'''
with tempfile.TemporaryDirectory(prefix='picocalc-i2c-audio-') as directory:
    folder = Path(directory)
    (folder / 'production.inc').write_text(production)
    (folder / 'test.cpp').write_text(TEST)
    subprocess.run([os.environ.get('CXX', 'clang++'), '-std=c++17', '-O2', '-Wall', '-Wextra', '-Werror',
                    '-fsanitize=address,undefined', '-fno-sanitize-recover=all',
                    '-I'+str(folder), '-I'+str(ROOT/'ports/picocalc'),
                    str(folder/'test.cpp'), '-o', str(folder/'test')], check=True)
    subprocess.run([str(folder/'test')], check=True)

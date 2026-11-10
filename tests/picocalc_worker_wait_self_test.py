#!/usr/bin/env python3
"""Exercise actual core1 alarm waits and I2C deadline rearming."""
import os
from pathlib import Path
import subprocess
import tempfile

ROOT=Path(__file__).resolve().parents[1]
source=(ROOT/'ports/picocalc/io_worker.cpp').read_text()
wait=source[source.index('void timed_wait(unsigned us) {'):source.index('void worker() {')]
callback=source[source.index('void i2c_timeout(unsigned) {'):source.index('std::atomic<u32> uart_wait_us')]
alarm=source[source.index('bool set_i2c_alarm(u64 target) {'):source.index('struct I2cBus {')]
TEST=r'''
#include <atomic>
#include <cassert>
#include <cstdint>
#include <cstdio>
#include "worker_deadline_trace.hpp"
using u64=uint64_t;
enum {IDLE,WORKING,DONE};
struct {std::atomic<unsigned> stage{IDLE};} i2c;
struct {u64 limit=0;u64 deadline()const{return limit;}} i2c_transfer;
int i2c_alarm=2;
unsigned core=1,sdk_waits=0,waits=0,sets=0,finishes=0,events=0;
u64 now=0,target=0;bool early=false,race=false,callback_before_wait=false,event_pending=false;
picocalc::WorkerDeadlineTrace deadline_trace;
struct DeadlineClock {uint32_t operator()()const{return (uint32_t)now;}};
using WorkerDeadlineTrace=picocalc::WorkerDeadlineTrace;
using DeadlineScope=WorkerDeadlineTrace::Scope<DeadlineClock>;
void i2c_timeout(unsigned);
unsigned get_core_num(){return core;}
u64 time_us_64(){return now;}
u64 make_timeout_time_us(unsigned us){return now+us;}
u64 from_us_since_boot(u64 us){return us;}
void best_effort_wfe_or_timeout(u64 t){++sdk_waits;now=t;}
bool hardware_alarm_set_target(unsigned alarm,u64 t){
    assert(alarm==2);++sets;target=t;
    if(callback_before_wait){now=t;i2c_timeout(2);callback_before_wait=false;return false;}
    if(race)now=t;return t<=now;
}
void test_wfe(){++waits;if(event_pending){event_pending=false;return;}assert(target>now);now=early?now+1:target;}
#define __wfe test_wfe
#define __sev() do {++events;if(callback_before_wait)event_pending=true;}while(0)
void finish_i2c(){++finishes;if(i2c.stage==WORKING && now>=i2c_transfer.limit)i2c.stage=DONE;}
#include "production.inc"
int main(){
    timed_wait(50);assert(now==50 && sets==1 && waits==1 && !sdk_waits);
    callback_before_wait=true;timed_wait(50);
    assert(now==100 && events==1 && !event_pending);now=50;finishes=0;
    i2c.stage=WORKING;i2c_transfer.limit=now+20;timed_wait(1000);
    assert(now==70 && target==70 && !sdk_waits);
    i2c_timeout(2);assert(i2c.stage==DONE && finishes==1);
    // An audio wake is earlier than the I2C timeout. Audio may stop now;
    // the callback must still arm the unchanged bus deadline.
    i2c.stage=WORKING;i2c_transfer.limit=10000;timed_wait(50);
    assert(now==120);i2c_timeout(2);assert(target==10000 && i2c.stage==WORKING);
    now=target;i2c_timeout(2);assert(i2c.stage==DONE);
    // An early peripheral SEV does not extend the I2C deadline.
    i2c.stage=WORKING;i2c_transfer.limit=now+30;early=true;timed_wait(50);
    assert(target==10030 && now==10001);early=false;
    // A deadline passing while the target is written must not WFE.
    const auto before=waits;race=true;i2c_timeout(2);race=false;
    assert(i2c.stage==DONE && waits==before);
    core=0;const auto armed=sets;timed_wait(50);assert(sdk_waits==1 && sets==armed);
    core=1;i2c_alarm=-1;timed_wait(1000);assert(sdk_waits==2 && sets==armed);
    std::puts("Production worker wait: own-core alarm, early wake, missed target, preserved I2C deadline after audio stop, no core0 pool traffic PASS");
}
'''
with tempfile.TemporaryDirectory(prefix='picocalc-worker-wait-') as directory:
    folder=Path(directory);(folder/'production.inc').write_text(alarm+wait+callback)
    (folder/'test.cpp').write_text(TEST)
    subprocess.run([os.environ.get('CXX','clang++'),'-std=c++17','-O2','-Wall','-Wextra','-Werror',
                    '-fsanitize=address,undefined','-fno-sanitize-recover=all','-I'+str(folder),'-I'+str(ROOT/'ports/picocalc'),
                    str(folder/'test.cpp'),'-o',str(folder/'test')],check=True)
    subprocess.run([str(folder/'test')],check=True)

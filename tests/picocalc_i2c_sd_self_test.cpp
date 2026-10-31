#include "i2c_transfer.hpp"
#include "sd_speed.hpp"
#include <array>
#include <vector>
#include <deque>
#include <cassert>
#include <cstdio>

namespace {
struct I2cBus {
    unsigned pending=0,starts=0,finishes=0,resets=0;bool reading=false;
    std::vector<unsigned> commands;std::deque<uint8_t> received;
    void prepare(bool read) { ++starts;reading=read;pending=0;received.clear();commands.clear(); }
    void put(unsigned command) { commands.push_back(command); }
    unsigned flags() { return pending; }
    bool available() { return !received.empty(); }
    uint8_t get() { auto v=received.front();received.pop_front();return v; }
    void finish(bool failed) { ++finishes;if(failed) ++resets;pending=0;received.clear(); }
};
void i2c_test() {
    using T=picocalc::I2cTransfer;I2cBus bus;T t;
    const uint8_t command[]={0x85,240};
    assert(!t.begin(bus,false,command,0,0) && !t.begin(bus,true,nullptr,3,0));
    assert(t.begin(bus,false,command,2,0));
    assert((bus.commands==std::vector<unsigned>{0x85,0x2F0}));
    assert(!t.begin(bus,false,command,1,1));
    // The foreground can prepare every LCD strip while bus clocks advance.
    for(unsigned us=0;us<3000;us+=10) assert(!t.step(bus,us));
    bus.pending=T::STOP;assert(t.step(bus,3000) && t.result()==2 && !t.active() && !bus.resets);
    assert(!t.step(bus,4000) && bus.finishes==1);
    assert(t.begin(bus,true,nullptr,2,5000));
    assert((bus.commands==std::vector<unsigned>{0x100,0x300}));
    bus.received.push_back(1);assert(!t.step(bus,6000));
    bus.received.push_back('7');bus.pending=T::STOP;
    assert(t.step(bus,7000) && t.result()==2 && t.bytes()[0]==1 && t.bytes()[1]=='7');
    for(unsigned flag:{T::ABORT,T::RX_OVERFLOW}) {
        assert(t.begin(bus,true,nullptr,2,10000));bus.pending=flag;
        const auto before=bus.resets;assert(t.step(bus,10001) && t.result()<0 && t.aborted() && bus.resets==before+1);
    }
    assert(t.begin(bus,true,nullptr,2,20000));assert(!t.step(bus,29999));
    assert(t.step(bus,30000) && t.result()==-2 && t.timed_out());
    bus.pending=T::STOP;bus.received={'x','y'};
    assert(!t.step(bus,30001)); // A late completion cannot complete a new job.
    assert(t.begin(bus,true,nullptr,2,40000) && !t.step(bus,40001));
    bus.received={'x'};bus.pending=T::STOP;
    assert(t.step(bus,40002) && t.result()<0); // Never publish a short read.
    assert(t.begin(bus,true,nullptr,2,50000));bus.received={1,2,3};bus.pending=T::STOP;
    assert(t.step(bus,50001) && t.result()<0 && t.aborted());
    assert(t.begin(bus,true,nullptr,2,60000));bus.received={4,5};bus.pending=T::STOP;
    assert(t.step(bus,70000) && t.result()==2); // Completed wire data wins a delayed timer callback.
}
struct SdBus {
    uint32_t hz=0;bool corrupt_fast=false,fail_fast=false,fail_safe=false;unsigned reads=0,safe_reads=0;
    std::vector<std::array<uint32_t,2>> trace;
    uint32_t rate(uint32_t request) {
        unsigned div=1;while(125000000/(2*div)>request) ++div;
        return hz=125000000/(2*div);
    }
    bool read(uint32_t sector,uint8_t* bytes) {
        ++reads;trace.push_back({sector,hz});const bool fast=hz>picocalc::sd::SAFE_HZ;
        if(!fast) ++safe_reads;
        if((fast && fail_fast) || (!fast && fail_safe && safe_reads>1)) return false;
        for(unsigned i=0;i<512;++i) bytes[i]=(uint8_t)(sector*13+i*71);
        if(fast && corrupt_fast) bytes[317]^=1;
        return true;
    }
};
struct WaitBus {
    uint64_t clock=0,ready=0;unsigned polls=0,waits=0;
    uint64_t now() { return clock; }
    uint8_t byte() { ++polls;++clock;return clock>=ready?0xFF:0; }
    void wait(uint64_t until) { assert(until>=clock && until-clock<=50);++waits;clock=until; }
};
void sd_test() {
    using namespace picocalc::sd;
    assert(transfer_rate(0x32)==25000000 && transfer_rate(0xFF)==SAFE_HZ);
    SdBus bus;auto q=qualify_speed(bus,0x32,1023);
    assert(q.ok && !q.fallback && q.hz==20833333 && q.safe_hz==12500000 && bus.reads==6);
    assert(bus.trace[0][0]==0 && bus.trace[2][0]==1 && bus.trace[4][0]==1023);
    for(bool crc_failure:{false,true}) {
        bus={};bus.fail_fast=crc_failure;bus.corrupt_fast=!crc_failure;q=qualify_speed(bus,0x32,1023);
        assert(q.ok && q.fallback && q.hz==SAFE_HZ && bus.reads==3);
    }
    bus={};bus.fail_fast=bus.fail_safe=true;q=qualify_speed(bus,0x32,1023);assert(!q.ok && q.fallback);
    bus={};q=qualify_speed(bus,0x32,1023,false);assert(q.ok && !q.fallback && q.hz==SAFE_HZ && bus.reads==1);
    bus={};q=qualify_speed(bus,0x09,0);assert(q.ok && q.hz<=1000000 && bus.reads==1);
    WaitBus waiting;assert(wait_ready(waiting,1000) && waiting.polls==1 && !waiting.waits);
    waiting={};waiting.ready=230;assert(wait_ready(waiting,1000) && waiting.waits==5 && waiting.polls==6);
    waiting={};waiting.ready=10000;assert(!wait_ready(waiting,200) && waiting.clock<=201 && waiting.waits==4);
}
}
int main() { i2c_test();sd_test();std::puts("IRQ I2C FIFO/STOP/NACK/timeout/recovery and read-only SD speed/CRC fallback/bounded waits PASS"); }

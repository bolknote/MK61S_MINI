#include "hardware.hpp"
#include "diagnostics.hpp"
#include <cassert>
#include <cstdio>
#include <cstring>
#include <vector>
static uint64_t ticks;
uint64_t time_us_64() { return ticks; }
namespace picocalc::diagnostics {
Scope::Scope(Point p):point_(p),start_(0),generation_(0){}
Scope::~Scope(){assert(point_==Point::KEYBOARD && start_==0 && generation_==0);}
}
struct Bus {
    bool pending=false,supported=true,requested=false,slept=false,permit=true;
    bool fail_write=false,short_write=false,fail_read=false;
    uint8_t reg=0,command=0,reply[2]{};
    int count=0;
    uint64_t renewed=0,selected_at=0;
    unsigned control_writes=0,control_reads=0,fifo_reads=0;
    std::vector<unsigned> commands;
} bus;
namespace picocalc::io_worker {
bool request_i2c(bool read,const u8 *p,unsigned n) {
    if(!bus.permit) return false;
    assert(!bus.pending && n==(read?2u:((p[0]&0x80)?2u:1u)));
    bus.pending=true;bus.count=(int)n;
    if(!read) {
        bus.selected_at=ticks;
        bus.reg=p[0]&0x7f;bus.command=n==2?p[1]:0;
        if(n==2) {
            assert(bus.reg==BIOS_SLEEP_REG && bus.supported);
            assert(bus.command==BIOS_SLEEP_ENTER || bus.command==BIOS_SLEEP_LEAVE);
            ++bus.control_writes;bus.commands.push_back(bus.command);
            if(bus.fail_write) {bus.fail_write=false;bus.count=-1;bus.command=0;}
            if(bus.short_write) {bus.short_write=false;bus.count=1;bus.command=0;}
        }
    } else if(ticks-bus.selected_at>=1000000) {
        bus.command=0;bus.reply[0]=bus.reply[1]=0;
    } else if(bus.reg==BIOS_SLEEP_REG) {
        ++bus.control_reads;
        if(bus.fail_read) {bus.fail_read=false;bus.count=-1;return true;}
        if(!bus.supported) {bus.reply[0]=0xde;bus.reply[1]=0xad;return true;}
        if(bus.command==BIOS_SLEEP_ENTER) {
            if(!bus.requested) bus.slept=false;
            bus.requested=true;bus.renewed=ticks;
        } else if(bus.command==BIOS_SLEEP_LEAVE) bus.requested=bus.slept=false;
        bus.command=0;bus.reply[0]=BIOS_SLEEP_REG;
        bus.reply[1]=BIOS_SLEEP_TAG|(bus.requested?1:0)|(bus.slept?2:0);
    } else if(bus.reg==9) {++bus.fifo_reads;bus.reply[0]=bus.reply[1]=0;}
    else if(bus.reg==1) {bus.reply[0]=1;bus.reply[1]=0x12;}
    else if(bus.reg==0x0b) {bus.reply[0]=0x0b;bus.reply[1]=80;}
    else if(bus.reg==BIOS_POWER_REG) {bus.reply[0]=BIOS_POWER_REG;bus.reply[1]=0xb1;}
    else assert(false);
    return true;
}
bool take_i2c(int& n,u8 *p) {
    if(!bus.pending) return false;
    n=bus.count;if(n==2) std::memcpy(p,bus.reply,2);bus.pending=false;return true;
}
}
namespace picocalc {
// ACTUAL_KEYBOARD_POLL
}
static void advance(picocalc::Keyboard& k,unsigned milliseconds) {
    for(unsigned i=0;i<milliseconds;++i) {
        ticks+=1000;
        if(bus.requested) {
            if(ticks-bus.renewed>=2000000) bus.requested=bus.slept=false;
            else bus.slept=true;
        }
        picocalc::KeyEvent event{};k.poll(event);
    }
}
static void policy() {
    using picocalc::BiosSleep;
    for(unsigned byte=0;byte<256;++byte) {
        BiosSleep p;uint8_t reply[]={BIOS_SLEEP_REG,(uint8_t)byte};p.reply(0,2,reply);
        assert((p.supported()==1)==(byte==0xd0 || byte==0xd1 || byte==0xd3));
    }
    BiosSleep p;p.idle(true);assert(p.next(0)==BiosSleep::PROBE);
    uint8_t active[]={BIOS_SLEEP_REG,0xd1};p.reply(0,2,active);assert(p.next(499999)==BiosSleep::NONE);
    assert(p.next(500000)==BiosSleep::ENTER);
    p.idle(false);assert(p.next(1)==BiosSleep::LEAVE);
    uint8_t idle[]={BIOS_SLEEP_REG,0xd0};p.reply(2,2,idle);assert(p.next(3)==BiosSleep::NONE);
    p.idle(true);p.reply(4,-1,idle);assert(p.errors()==1 && p.next(5)==BiosSleep::NONE);
    assert(p.next(250004)==BiosSleep::PROBE);
}
int main() {
    policy();
    // Old firmware never receives a write to its unknown register.
    bus={};bus.supported=false;ticks=0;picocalc::Keyboard old;
    advance(old,300);assert(old.online() && old.bios_sleep().supported()==0);
    old.idle(true);advance(old,22000);old.idle(false);advance(old,300);
    assert(bus.control_writes==0 && old.errors()==0 && bus.fifo_reads>20);
    // Sleep, repeated lease renewal, keyboard polling, and explicit resume.
    bus={};ticks=0;picocalc::Keyboard k;advance(k,300);
    assert(k.bios_sleep().supported()==1 && !bus.requested);
    k.idle(true);advance(k,5000);
    assert(bus.requested && bus.slept && k.bios_sleep().requested() && k.bios_sleep().slept());
    assert(bus.control_writes>=9 && bus.fifo_reads>20);
    k.idle(false);advance(k,100);assert(!bus.requested && !k.bios_sleep().requested());
    // Wake while ENTER is in flight: the next command must cancel it.
    k.idle(true);
    while(!bus.pending || bus.reg!=BIOS_SLEEP_REG) advance(k,1);
    k.idle(false);advance(k,100);assert(!bus.requested && !k.bios_sleep().requested());
    // Failed/short write and failed read all rediscover before retrying.
    for(unsigned which=0;which<3;++which) {
        k.idle(true);
        bus.fail_write=which==0;bus.short_write=which==1;bus.fail_read=which==2;
        const unsigned errors=k.bios_sleep().errors();advance(k,1200);
        assert(k.bios_sleep().errors()>errors && bus.requested);
        k.idle(false);advance(k,200);assert(!bus.requested);
    }
    // An occupied I2C slot must not advance the command state.
    bus.permit=false;k.idle(true);const unsigned writes=bus.control_writes;
    advance(k,400);assert(bus.control_writes==writes);bus.permit=true;advance(k,1000);assert(bus.requested);
    // Simulate a paused Pico: firmware lease expires, then renewal recovers.
    ticks+=2500000;bus.requested=bus.slept=false;advance(k,1000);assert(bus.requested);
    k.idle(false);advance(k,200);assert(!bus.requested && !k.bios_sleep().requested());
    // Register selection expires in the BIOS while an APP/SD pauses polling.
    // Repeat the read-only selection, then reconcile ENTER/LEAVE as needed.
    for(bool entering:{true,false}) {
        k.idle(entering);
        while(!bus.pending || bus.reg!=BIOS_SLEEP_REG ||
              bus.command!=(entering?BIOS_SLEEP_ENTER:BIOS_SLEEP_LEAVE)) advance(k,1);
        advance(k,1);assert(!bus.pending);
        const unsigned errors=k.bios_sleep().errors();
        ticks+=1200000;bus.permit=false;advance(k,100);bus.permit=true;advance(k,250);
        assert(k.bios_sleep().supported()==1 && k.bios_sleep().errors()==errors);
        assert(bus.requested==entering && k.bios_sleep().requested()==entering);
    }
    bus={};ticks=0;picocalc::Keyboard probe;
    while(!bus.pending || bus.reg!=BIOS_SLEEP_REG) advance(probe,1);
    advance(probe,1);ticks+=1200000;advance(probe,200);
    assert(probe.bios_sleep().supported()==1 && probe.bios_sleep().errors()==0);
    assert(k.errors()==0);
    puts("Pico retained M3 sleep PASS: actual async poll, tagged discovery/old BIOS, renew/expiry, wake race, short/error/retry, FIFO, stale selection and occupied I2C");
}

#include "cosmic_clock_plan.hpp"
#include <cassert>
#include <cstdio>
#include <string>
#include <vector>
using namespace picocalc::cosmic_clock;
struct Backend {
    std::vector<std::string> events;
    bool busy=false,usb=true,held=false,reset=false;
    const char* fail="";
    bool idle(){return !busy;}
    void stop_click(){events.push_back("stop");}
    void drain(){events.push_back("drain");}
    bool pio(uint32_t div){events.push_back("pio"+std::to_string(div));return std::string(fail)!="pio";}
    void disconnect(){events.push_back("disconnect");usb=false;}
    bool deinit_usb(){events.push_back("deinit");return std::string(fail)!="deinit";}
    void hold_usb_reset(){assert(!usb);events.push_back("hold");held=true;}
    void detach_delay(){assert(held);events.push_back("delay");}
    bool change_clock(const Plan&){assert(held && !usb);events.push_back("clock");return std::string(fail)!="clock";}
    bool healthy(uint32_t){assert(held && !usb);events.push_back("measure");return std::string(fail)!="measure";}
    void release_usb_reset(){assert(held);held=false;events.push_back("release");}
    bool init_usb(){assert(!held);events.push_back("init");return std::string(fail)!="init";}
    void connect(){events.push_back("connect");usb=true;}
    void reboot(){events.push_back("reboot125");reset=true;}
    unsigned at(const std::string& event)const {for(unsigned i=0;i<events.size();++i)if(events[i]==event)return i;return UINT32_MAX;}
};
struct Pins {
    bool scl_stuck=false,sda_stuck=false;unsigned delays=0,clocks=0;
    std::vector<std::string> events;
    void init(){events.push_back("init");}
    void release_sda(){events.push_back("release-sda");}
    void release_scl(){events.push_back("release-scl");++clocks;}
    void low_scl(){events.push_back("low-scl");}
    void low_sda(){events.push_back("low-sda");}
    bool scl_high(){return !scl_stuck;}
    bool sda_high(){return !sda_stuck;}
    void delay(){++delays;}
};
struct Reset {
    std::string events;bool armed=false;
    void stop_click(){events+="stop ";}void drain(){events+="drain ";}
    void prepare_psram(){events+="psram ";}void reply(){events+="reply ";}
    void arm_reset(){events+="arm ";armed=true;}
    void spin(){assert(armed);events+="spin";throw 42;}
};
int main(){
    unsigned transitions=0;
    for(const auto& before:plans)for(const auto& after:plans){
        assert(valid(before) && valid(after));Backend b;assert(transition(b,before,after));++transitions;
        assert(b.at("disconnect")<b.at("hold") && b.at("hold")<b.at("clock") && b.at("clock")<b.at("release"));
        const std::string pio="pio"+std::to_string(after.pio_div256);
        assert((after.mhz>before.mhz)==(b.at(pio)<b.at("clock")));
        assert(b.usb && !b.held && !b.reset);
    }
    for(const char* fault:{"pio","deinit","clock","measure","init"}){
        Backend b;b.fail=fault;assert(!transition(b,plans[0],plans[2]));
        if(std::string(fault)=="pio")assert(b.usb && !b.reset && b.at("disconnect")==UINT32_MAX);
        else assert(b.reset && b.events.back()=="reboot125" && !b.usb);
    }
    Backend busy;busy.busy=true;assert(!transition(busy,plans[0],plans[1]) && busy.events.empty());
    assert(!find(0) && !find(126) && !find(300));
    Lease lease;assert(lease.arm(250,100));assert(!lease.arm(200,200));assert(!lease.expired(100+uint64_t(LEASE_MS)*1000-1));
    assert(lease.expired(100+uint64_t(LEASE_MS)*1000));lease.clear();assert(!lease.active && lease.mhz==125);
    assert(!lease.arm(300,0) && !lease.arm(200,UINT64_MAX-1));
    for(unsigned mhz:{125,200,250}){const auto* p=find(mhz);assert(uint64_t(mhz)*1000000*256==uint64_t(PIO_HZ)*p->pio_div256);}
    Pins pins;assert(clear_i2c(pins) && pins.clocks==11 && pins.delays==21);
    Pins stuck;stuck.scl_stuck=true;assert(!clear_i2c(stuck) && stuck.delays==20 && stuck.events.size()==3);
    Pins sda;sda.sda_stuck=true;assert(!clear_i2c(sda));
    Reset reset;bool caught=false;
    try{planned_reboot(reset);}catch(int code){assert(code==42);caught=true;}
    assert(caught && reset.events=="stop drain psram reply drain arm spin");
    std::printf("Clock policy PASS: %u integer-PLL transitions, bounded peripheral clocks, USB reset ordering, five faults, independent lease, open-drain I2C clear and nonreturning drained reset\n",transitions);
}

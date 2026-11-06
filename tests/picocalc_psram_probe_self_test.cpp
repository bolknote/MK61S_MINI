#include "psram_probe.hpp"
#include <cassert>
#include <cstdio>
#include <cstring>
#include <string>
#include <vector>
using namespace picocalc::psram;
struct Bus {
    static constexpr u32 CAPACITY=8U*1024*1024;
    enum Fault { NONE,COMPARE,READ_IO,WRITE_IO,BURST };
    std::vector<u8> ram=std::vector<u8>(CAPACITY,0xA5);
    std::string events;
    bool qpi=false,reset_error=false,spi_error=false;
    unsigned attempts=0,bad_attempts=0,enter_errors=0,fallbacks=0;
    u32 alias=0;Fault fault=NONE;
    bool bad() const { return (qpi && attempts<=bad_attempts) || (!qpi && spi_error); }
    u32 address(u32 at) const { return bad()?at&~alias:at; }
    bool enter_qpi() { events+='Q';qpi=true;return ++attempts>enter_errors; }
    bool reset_spi() { events+='R';if(reset_error) return false;qpi=false;return true; }
    void fallback() { assert(!qpi);events+='F';++fallbacks; }
    bool write(u32 at,const u8* bytes,unsigned count) {
        assert(at<CAPACITY && count<=CAPACITY-at);
        if(bad() && fault==WRITE_IO) return false;
        for(unsigned i=0;i<count;++i) ram[address(at+i)]=bytes[i];
        return true;
    }
    bool read(u32 at,u8* bytes,unsigned count) {
        assert(at<CAPACITY && count<=CAPACITY-at);
        if(bad() && fault==READ_IO) return false;
        for(unsigned i=0;i<count;++i) bytes[i]=ram[address(at+i)];
        if(bad() && fault==COMPARE && at==0) bytes[0]^=1;
        if(bad() && fault==BURST && at==CAPACITY-32 && count==32) bytes[17]^=1;
        return true;
    }
};
int main() {
    { Bus bus;BootProbe out;assert(qualify_boot(bus,out,true));
      assert(bus.events=="Q" && bus.qpi && out.qpi_attempts==1 && !out.failures); }
    { Bus bus;BootProbe out;assert(qualify_boot(bus,out,false));
      assert(bus.events.empty() && !bus.qpi && !out.qpi_attempts && !out.failures); }
    for(auto fault:{Bus::COMPARE,Bus::READ_IO,Bus::WRITE_IO,Bus::BURST}) {
        Bus bus;BootProbe out;bus.fault=fault;bus.bad_attempts=1;
        assert(qualify_boot(bus,out,true));
        assert(bus.events=="QRQ" && bus.qpi && out.qpi_attempts==2 && out.failures==1 && !bus.fallbacks);
        const auto phase=fault==Bus::READ_IO?ProbePhase::READ:fault==Bus::WRITE_IO?ProbePhase::WRITE:ProbePhase::COMPARE;
        assert(out.first.phase==phase && out.first.qpi==1 && out.first.address==(fault==Bus::BURST?Bus::CAPACITY-15:0));
        if(fault==Bus::COMPARE) assert(out.first.expected==13 && out.first.actual==12);
        if(fault==Bus::BURST) assert(out.first.expected==2 && out.first.actual==3);
    }
    // Every external address bit must be observable against the zero anchor.
    for(unsigned bit=0;bit<23;++bit) {
        Bus bus;BootProbe out;bus.alias=1U<<bit;bus.bad_attempts=2;
        assert(qualify_boot(bus,out,true));
        assert(bus.events=="QRQRF" && !bus.qpi && bus.fallbacks==1 && out.failures==2);
        assert(out.first.phase==ProbePhase::COMPARE && out.first.address==0 && out.first.expected==13);
    }
    { Bus bus;BootProbe out;bus.alias=1U<<12;bus.bad_attempts=2;bus.spi_error=true;
      assert(!qualify_boot(bus,out,true));assert(bus.events=="QRQRF" && out.failures==3); }
    { Bus bus;BootProbe out;bus.fault=Bus::COMPARE;bus.bad_attempts=2;bus.reset_error=true;
      assert(!qualify_boot(bus,out,true));assert(bus.events=="QR" && out.qpi_attempts==1 && out.failures==2);
      assert(out.first.phase==ProbePhase::COMPARE && out.last_failure==ProbePhase::RESET_SPI && !bus.fallbacks); }
    { Bus bus;BootProbe out;bus.enter_errors=1;
      assert(qualify_boot(bus,out,true));assert(bus.events=="QRQ" && out.failures==1);
      assert(out.first.phase==ProbePhase::ENTER_QPI); }
    { Bus bus;BootProbe out;bus.enter_errors=2;
      assert(qualify_boot(bus,out,true));assert(bus.events=="QRQRF" && out.failures==2 && !bus.qpi); }
    { Bus bus;BootProbe out;bus.spi_error=true;bus.fault=Bus::READ_IO;
      assert(!qualify_boot(bus,out,false));assert(out.first.phase==ProbePhase::READ && !out.first.qpi && bus.events.empty()); }
    puts("PSRAM boot probe: all23 address aliases, burst mismatch, read/write I/O, one recovery, verified fallback and reset/entry failures PASS");
}

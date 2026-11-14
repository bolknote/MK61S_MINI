#!/usr/bin/env python3
"""Execute the actual Pico keyboard/power poll with old and new BIOS replies."""
from pathlib import Path
import os
import subprocess
import tempfile

ROOT = Path(__file__).resolve().parents[1]
header = (ROOT / "ports/picocalc/hardware.hpp").read_text()
keyboard = "class Keyboard {" + header.split("class Keyboard {", 1)[1].split("\n};", 1)[0] + "\n};\n"
source = (ROOT / "ports/picocalc/hardware.cpp").read_text()
poll_start = "bool Keyboard::request_register(" if "bool Keyboard::request_register(" in source else "bool Keyboard::poll("
poll = source[source.index(poll_start):source.index("void Keyboard::clock_changed(")]
fixture = r'''
#include "battery.hpp"
#include <algorithm>
#include <cassert>
#include <cstdint>
#include <cstdio>
#include <cstring>
#include <vector>
using u8=uint8_t;using u32=uint32_t;using u64=uint64_t;
static u64 now;
u64 time_us_64() { return now; }
struct Bus {
    bool job=false,native=false,fail_power=false,fail_fifo=false;
    u8 reg=0,last=0,raw_power=0xB7,reply[2]{};int result=0;
    std::vector<u8> selected;
} bus;
namespace picocalc {
struct KeyEvent { u8 state=0,key=0; };
namespace diagnostics { enum class Point { KEYBOARD };struct Scope { explicit Scope(Point) {} }; }
namespace io_worker {
bool request_i2c(bool read,const u8* bytes,unsigned length) {
    if(bus.job) return false;
    assert(length==(read?2u:1u));bus.job=true;
    if(!read) {
        bus.reg=bytes[0];bus.selected.push_back(bus.reg);bus.result=1;return true;
    }
    bus.result=2;bus.reply[0]=bus.reg;
    if(bus.reg==9) {
        if(bus.fail_fifo) {bus.fail_fifo=false;bus.result=-1;return true;}
        bus.reply[0]=0;bus.last=0;
    } else if(bus.reg==0x0B) bus.last=0xB7; // 55% + old charging bit looks like a valid power reply!
    else if(bus.reg==1) bus.last=0x12;
    else if(bus.reg==BIOS_POWER_REG) {
        if(bus.fail_power) {bus.fail_power=false;bus.result=-1;return true;}
        if(bus.native) bus.last=bus.raw_power;
        // Old Southbridge leaves the previous payload for unsupported regs.
    } else assert(false);
    bus.reply[1]=bus.last;return true;
}
bool take_i2c(int& result,u8* bytes) {
    if(!bus.job) return false;
    result=bus.result;if(result==2) std::memcpy(bytes,bus.reply,2);
    bus.job=false;return true;
}
}
@KEYBOARD@
@POLL@
}
static void advance(picocalc::Keyboard& keyboard,unsigned ms,bool forbid_power=false) {
    for(unsigned i=0;i<ms;++i) {
        now+=1000;picocalc::KeyEvent event;keyboard.poll(event);
        if(forbid_power) assert(!keyboard.battery().power_valid());
    }
}
int main() {
    picocalc::Keyboard old;
    advance(old,400,true);
    assert(old.online() && old.battery().percent==55 && old.battery().bios_flag7);
    assert(!old.battery().power_supported() && old.battery_errors()==0);
    auto power=std::find(bus.selected.begin(),bus.selected.end(),BIOS_POWER_REG);
    assert(power!=bus.selected.end() && power!=bus.selected.begin() && *(power-1)==1);
    advance(old,21000,true); // Re-probe the optional register without false flags or bus errors.
    assert(!old.battery().power_supported() && old.battery_errors()==0);
    bus={};bus.native=true;now=0;picocalc::Keyboard fresh;
    advance(fresh,400);assert(fresh.battery().charging());
    assert(std::count(bus.selected.begin(),bus.selected.end(),1)==1);
    bus.raw_power=0xBB;advance(fresh,1200);
    assert(fresh.battery().charge_complete() && !fresh.battery().charging());
    assert(fresh.battery().percent==55); // No percentage-based inference.
    bus.fail_power=true;
    for(unsigned i=0;i<1500 && fresh.battery().power_valid();++i) advance(fresh,1);
    assert(fresh.battery().power_supported() && !fresh.battery().power_valid());
    assert(fresh.battery_errors()==1 && !fresh.battery().external_power());
    bus.raw_power=0xB3;advance(fresh,1200);
    assert(fresh.battery().external_power() && !fresh.battery().charging() && !fresh.battery().charge_complete());
    bus.fail_fifo=true;
    for(unsigned i=0;i<200 && fresh.online();++i) advance(fresh,1);
    assert(!fresh.online() && !fresh.battery().power_supported());
    bus.native=false;advance(fresh,22000,true); // Old BIOS after a controller restart.
    assert(fresh.online() && !fresh.battery().power_supported());
    for(const u8 reg:bus.selected) assert(reg==1 || reg==9 || reg==0x0B || reg==BIOS_POWER_REG);
    std::puts("Pico power poll: actual production async poll, stale old-BIOS replies, discovery, DONE, I2C errors/recovery and BIOS restart PASS");
}
'''.replace("@KEYBOARD@", keyboard).replace("@POLL@", poll)
with tempfile.TemporaryDirectory(prefix="mk61-power-poll-") as work:
    work = Path(work)
    source = work / "poll.cpp"
    source.write_text(fixture)
    flags = ["-fsanitize=address,undefined", "-fno-omit-frame-pointer"] if os.environ.get("MK61_TEST_SANITIZERS") == "1" else []
    binary = work / "poll-test"
    subprocess.run(["clang++", "-std=c++17", "-O2", "-Wall", "-Wextra", "-Werror", *flags,
                    "-I" + str(ROOT / "ports/picocalc"), str(source), "-o", str(binary)], check=True)
    subprocess.run([str(binary)], check=True)

#!/usr/bin/env python3
"""Run actual resident/foreground power paths against bounded I/O endpoints."""
import os
from pathlib import Path
import subprocess
import tempfile

ROOT=Path(__file__).resolve().parents[1]
source=(ROOT/'ports/picocalc/main.cpp').read_text()
def function(signature):
    assert source.count(signature)==1,signature
    start=source.index(signature);at=source.index('{',start)+1;depth=1
    while depth:
        depth+=(source[at]=='{')-(source[at]=='}');at+=1
    return source[start:at]

fixture=r'''
#include "power.hpp"
#include "calculator.hpp"
#include <cassert>
#include <cstdio>
#include <cstring>
#include <deque>
#include <array>
#include <stdexcept>
using picocalc::KeyEvent;
constexpr int PICO_ERROR_TIMEOUT=-2;
u64 clock_us=1000000;
u64 time_us_64(){return clock_us;}
u32 millis(){return (u32)(clock_us/1000);}
bool vbus=true,audio_active=false,disk_active=false;
unsigned entries=0,leaves=0,clock_refreshes=0,reports=0,saves=0,tones=0,leds=0;
unsigned snapshots=0,usb_turns=0,sleep_turns=0,wake_mode=0;
std::array<u8,1024> state{},saved_state{};
namespace picocalc {
void SleepClocks::init(){}
void SleepClocks::enter(){assert(!active_);active_=true;usb_=vbus;++::entries;}
void SleepClocks::leave(){if(active_){active_=false;++leaves;}}
bool SleepClocks::refresh(){++clock_refreshes;return false;}
namespace script {
bool input(u8){assert(false);return false;}
void tone(unsigned f,unsigned d){assert(!f && !d);++tones;}
void led_stop(){++leds;}
void service_effects(){}
}
namespace audio_stream {bool active(){return audio_active;}}
namespace files {bool usb_active(){return disk_active;}}
namespace io_worker {bool frame_pending(){return false;}}
namespace diagnostics {enum class Point{PUMP};struct Scope{explicit Scope(Point){}};}
namespace controls {
enum class Source {PHYSICAL,REMOTE};
std::array<bool,256> held{};unsigned events=0,pulses=0;
void event(KeyEvent e,Source){++events;held[e.code]=e.state!=3;}
void pulse(u8 code,u32){assert(code!=POWER_BUTTON);++pulses;held[code]=true;}
}
namespace console {
std::deque<int> bytes;
int read(bool,bool){if(bytes.empty())return -1;int c=bytes.front();bytes.pop_front();return c;}
bool input_usb(){return true;}
bool accept(int,bool){return true;}
struct {bool skip_lf(int c){return c=='\n';}}routing;
}
enum class Page {CALCULATOR,MAIN};
struct FrameSchedule {static u64 next(u64 at){return at+20000;}};
}
namespace m61_text {bool calculator_suspended(){return false;}}
struct {
    bool pending=false;unsigned renders=0,invalidations=0;
    bool bootloader_pending(){return pending;}
    bool presentation_pending(){return false;}
    template<class... T>void render(T...){++renders;}
    void presented(){}
    void invalidate(){++invalidations;}
}screen;
struct {
    unsigned wakes=0,inputs=0;bool parked(){return true;}
    void wake_core(){++wakes;}
    bool input(u8){++inputs;assert(false);return false;}
}calculator;
struct {
    bool asleep=false;unsigned calls=0,notes=0;
    bool color_active(){return false;}
    bool needs_refresh(){return false;}
    template<class T>bool flush(T&){assert(false);return false;}
    void sleep(bool value){asleep=value;++calls;}
    void note_input(u64){++notes;}
}panel;
struct {
    std::deque<KeyEvent> events;bool inflight=false,idling=false;
    unsigned changes=0,backlights=0;u8 lcd=240,keys=40;
    bool poll(KeyEvent& e){if(events.empty())return false;e=events.front();events.pop_front();return true;}
    bool transaction_pending(){return inflight;}
    bool online(){return true;}
    int battery(){return 0;}
    u64 next_poll(){return 0;}
    void idle(bool value){idling=value;}
    void backlight(u8 l,u8 k){lcd=l;keys=k;++backlights;}
    void clock_changed(){++changes;}
}keyboard;
struct {
    std::deque<KeyEvent> events;
    bool key(KeyEvent& e){if(events.empty())return false;e=events.front();events.pop_front();return true;}
    bool holds_frame(){return false;}
    int receive(u8 c,u32){return c;}
}remote_screen;
struct {
    bool live=false,foreground=false;unsigned inputs=0;
    bool active(){return live;}
    bool running(){return foreground;}
    bool input(u8){++inputs;assert(false);return false;}
}services;
struct {
    struct {u8 lcd_backlight=240,key_backlight=40;}lights;
    picocalc::Page page(){return picocalc::Page::CALCULATOR;}
    bool input(u8,decltype(calculator)&){assert(false);return false;}
    const auto& settings(){return lights;}
}ui;
struct {
    bool input_active(){return false;}
    void input_source(bool){}
    int receive(u8 c){return c>=0x1D && c<=0x1F?-1:c;}
}terminal;
picocalc::SleepPolicy power;
picocalc::SleepClocks sleep_clocks;
bool panel_ready=true,sleep_applied=false,physical_event=false;
u32 physical_keys=0;u8 last_physical_key=0;
u64 last_activity=0;unsigned math_failures=0,clicks=0;
void save_settings(){++saves;}
void report(unsigned){++reports;assert(power.asleep());}
void key_click(){++clicks;}
picocalc::Snapshot display_snapshot(){++snapshots;return {};}
@WAKE@
@INPUT@
void usb_service(){
    assert(++usb_turns<100);clock_us+=1000;
    if(power.asleep() && sleep_applied) {
        assert(state==saved_state && panel.asleep && !keyboard.lcd && !keyboard.keys);
        ++sleep_turns;
        if(sleep_turns==1)picocalc::console::bytes.push_back(5);
        if(sleep_turns==3) {
            if(wake_mode==1)wake(clock_us); // RTC wake follows this same path.
            else if(wake_mode==2)keyboard.events.push_back({1,'7'});
            else if(wake_mode==3)picocalc::console::bytes.push_back(picocalc::POWER_BUTTON);
            else keyboard.events.push_back({1,picocalc::POWER_BUTTON});
        }
    }
}
namespace picocalc {void idle_until(u64 at,bool){assert(at>clock_us);clock_us=at;}}
@KEY_EVENT@
@APPLY_SLEEP@
@WAIT@
@PUMP@
void reset(){
    assert(!power.asleep());clock_us+=1000000;power={};sleep_clocks={};
    vbus=true;audio_active=disk_active=false;
    entries=leaves=clock_refreshes=reports=saves=tones=leds=snapshots=usb_turns=sleep_turns=wake_mode=0;
    screen={};calculator={};panel={};keyboard={};remote_screen={};services={};ui={};
    panel_ready=true;sleep_applied=physical_event=false;
    physical_keys=0;last_physical_key=0;last_activity=0;clicks=0;
    picocalc::controls::held={};picocalc::controls::events=picocalc::controls::pulses=0;picocalc::console::bytes.clear();
    for(unsigned i=0;i<state.size();++i)state[i]=(u8)(i*17+43);saved_state=state;
}
void preserved(){
    assert(state==saved_state && !power.asleep() && !sleep_applied && !panel.asleep);
    assert(keyboard.lcd==240 && keyboard.keys==40 && !keyboard.idling);
    assert(!services.inputs && !calculator.inputs && !clicks && !panel.notes && !physical_keys);
    assert(!picocalc::controls::held[picocalc::POWER_BUTTON] && !picocalc::controls::pulses);
}
int main(){
    reset();KeyEvent e{};
    keyboard.events.push_back({1,picocalc::POWER_BUTTON});assert(!key_event(e));
    assert(power.asleep() && power.button_presses()==1 && !picocalc::controls::events);
    for(u8 state:{u8(2),u8(3)}){keyboard.events.push_back({state,picocalc::POWER_BUTTON});assert(!key_event(e));assert(power.asleep() && power.button_presses()==1);}
    keyboard.events.push_back({1,picocalc::POWER_BUTTON});assert(!key_event(e));preserved();assert(power.button_presses()==2 && !calculator.wakes);
    reset();remote_screen.events.push_back({1,picocalc::POWER_BUTTON});assert(!key_event(e));
    remote_screen.events.push_back({1,picocalc::POWER_BUTTON});assert(!key_event(e));preserved();assert(!picocalc::controls::events);
    for(bool usb:{false,true})for(unsigned mode:{0U,1U,2U,3U}) {
        reset();vbus=usb;wake_mode=mode;input(picocalc::POWER_BUTTON,true);wait_for_wake();preserved();
        assert(entries==1 && leaves==1 && saves==1 && tones==1 && reports==1 && sleep_turns==3);
        assert(power.button_presses()==(mode==1 || mode==2?1U:2U));
        assert(calculator.wakes==(mode==2?1U:0U));
    }
    for(unsigned holder:{0U,1U,2U}) {
        reset();services.foreground=holder==0;services.live=true;disk_active=holder==1;audio_active=holder==2;
        keyboard.events.push_back({1,picocalc::POWER_BUTTON});u8 key=0xA5;
        assert(!service_pump(nullptr,key) && key==0xA5);preserved();
        assert(!entries && !leaves && reports==1 && power.button_presses()==2);
        assert(services.foreground==(holder==0) && disk_active==(holder==1) && audio_active==(holder==2));
    }
    reset();services.live=services.foreground=true;wake_mode=3;
    picocalc::console::bytes.push_back(picocalc::POWER_BUTTON);u8 key=0xA5;
    assert(!service_pump(nullptr,key) && key==0xA5);preserved();assert(power.button_presses()==2 && !entries);
    reset();input(picocalc::POWER_BUTTON,false);keyboard.inflight=true;
    assert(!apply_sleep() && !sleep_applied && !panel.calls && !entries);
    keyboard.inflight=false;assert(apply_sleep() && entries==1);
    input(picocalc::POWER_BUTTON,false);assert(apply_sleep());preserved();
    reset();screen.pending=true;keyboard.events.push_back({1,picocalc::POWER_BUTTON});assert(!key_event(e));
    assert(!power.asleep() && !power.button_presses() && !picocalc::controls::events);
    puts("Actual power input/pump: BIOS press-only toggles, hold/release filtering, no APP/bitmap/click, USB/battery/RTC/ordinary wake, cooperative state retention and APP/audio/MSC clocks PASS");
}
'''
for marker,signature in {
    '@WAKE@':'void wake(u64 now)',
    '@INPUT@':'void input(u8 code, bool physical)',
    '@KEY_EVENT@':'bool key_event(picocalc::KeyEvent& event)',
    '@APPLY_SLEEP@':'bool apply_sleep()',
    '@WAIT@':'void wait_for_wake()',
    '@PUMP@':'bool service_pump(void*, u8& key)',
}.items():fixture=fixture.replace(marker,function(signature))
with tempfile.TemporaryDirectory(prefix='picocalc-power-button-') as directory:
    path=Path(directory);cpp=path/'test.cpp';cpp.write_text(fixture);binary=path/'test'
    flags=['-fsanitize=address,undefined','-fno-omit-frame-pointer'] if os.environ.get('MK61_TEST_SANITIZERS')=='1' else []
    subprocess.run([os.environ.get('CXX','clang++'),'-std=c++17','-O2','-Wall','-Wextra','-Werror',*flags,
        '-DMK61_CORE_STANDALONE=1','-I'+str(ROOT/'ports/picocalc'),'-I'+str(ROOT/'code'),str(cpp),'-o',str(binary)],check=True)
    subprocess.run([str(binary)],check=True)

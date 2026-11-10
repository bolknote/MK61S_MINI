#!/usr/bin/env python3
"""Compile actual input delivery; keep calculator/service/sleep wake paths."""
import os,subprocess,tempfile
from pathlib import Path
ROOT=Path(__file__).resolve().parents[1]
source=(ROOT/'ports/picocalc/main.cpp').read_text()
first='void input(u8 code, bool physical) {';last='void save_settings() {'
assert source.count(first)==source.count(last)==1
body=source[source.index(first):source.index(last)]
fixture=r'''
#include <cassert>
#include <cstdint>
#include <cstdio>
#include "power.hpp"
using u8=uint8_t;using u32=uint32_t;using u64=uint64_t;
namespace picocalc {
enum class Page {CALCULATOR,MAIN};
namespace script {bool accept=false;unsigned calls=0;bool input(u8){++calls;return accept;}}
}
namespace m61_text {bool suspended=false;bool calculator_suspended(){return suspended;}}
u64 time_us_64(){return 10000;}
struct {
    unsigned wakes=0,inputs=0;bool park=true,accept=true;
    void wake_core(){++wakes;park=false;}
    bool parked()const{return park;}
    bool input(u8){++inputs;if(accept)park=false;return accept;}
} calculator;
struct {bool pending=false;bool bootloader_pending(){return pending;}}screen;
struct {bool sleeping=false;unsigned activities=0,buttons=0;void note_button(){++buttons;}unsigned button_presses(){return buttons;}bool asleep(){return sleeping;}void activity(u64){++activities;}void sleep(){sleeping=true;}}power;
struct {bool opened=false,accept=false;unsigned calls=0;bool active(){return opened;}bool input(u8){++calls;return accept;}}services;
struct {
    picocalc::Page value=picocalc::Page::MAIN;bool accept=true;unsigned calls=0;
    picocalc::Page page(){return value;}
    template<class T>bool input(u8 c,T&){++calls;if(c==9)value=value==picocalc::Page::MAIN?picocalc::Page::CALCULATOR:picocalc::Page::MAIN;else if(c==27)value=picocalc::Page::CALCULATOR;return accept;}
}ui;
struct {unsigned notes=0;void note_input(u64){++notes;}}panel;
unsigned clicks=0,wakes=0,physical_keys=0;u8 last_physical_key=0;u64 last_activity=0;
void key_click(){++clicks;}void wake(u64){++wakes;power.sleeping=false;}
@INPUT@
void reset(){calculator={};screen={};power={};services={};ui={};panel={};clicks=wakes=physical_keys=0;last_physical_key=0;last_activity=0;picocalc::script::accept=false;picocalc::script::calls=0;m61_text::suspended=false;}
int main(){
    for(bool physical:{false,true})for(bool active:{false,true}) {
        reset();services.opened=active;
        input(picocalc::POWER_BUTTON,physical);
        assert(power.sleeping && power.button_presses()==1 && !calculator.wakes && !calculator.inputs);
        assert(!services.calls && !ui.calls && !panel.notes && !clicks && !physical_keys);
        input(picocalc::POWER_BUTTON,physical); // BIOS sends no release between presses.
        assert(!power.sleeping && power.button_presses()==2 && wakes==1);
        assert(!calculator.wakes && !calculator.inputs && !services.calls && !ui.calls && !clicks);
    }
    reset();input(0xb6,true);input(0xb6,true);input(0xb5,true);
    assert(calculator.park && !calculator.wakes && !calculator.inputs && ui.calls==3);
    assert(panel.notes==3 && clicks==3 && physical_keys==3 && last_physical_key==0xb5 && last_activity==10000);
    for(u8 key:{u8(9),u8(27),u8(13),u8('1'),u8(0xb4),u8(0xb7)}){
        reset();input(key,false);assert(calculator.wakes==2 && !calculator.park && panel.notes==1);
    }
    reset();ui.value=picocalc::Page::CALCULATOR;input(9,false);assert(calculator.wakes==2 && ui.value==picocalc::Page::MAIN);
    for(u8 key:{u8(0xb5),u8(0xb6),u8('1')}){
        reset();ui.value=picocalc::Page::CALCULATOR;input(key,false);assert(calculator.wakes==2);
    }
    reset();ui.value=picocalc::Page::CALCULATOR;ui.accept=false;input('7',false);
    assert(calculator.inputs==1 && calculator.wakes==2 && panel.notes==1);
    reset();services.opened=services.accept=true;input(0xb6,false);
    assert(calculator.wakes==2 && services.calls==1 && !ui.calls && !calculator.inputs);
    reset();calculator.park=false;input(0xb6,false);assert(calculator.wakes==2);
    reset();power.sleeping=true;input(0xb6,true);
    assert(calculator.wakes==1 && wakes==1 && !ui.calls && !panel.notes && !physical_keys);
    reset();screen.pending=true;input(0xb6,true);assert(!calculator.wakes && !power.activities && !ui.calls && !panel.notes);
    reset();ui.value=picocalc::Page::CALCULATOR;picocalc::script::accept=true;input('1',false);
    assert(calculator.wakes==2 && picocalc::script::calls==1 && !ui.calls && !calculator.inputs);
    reset();ui.value=picocalc::Page::CALCULATOR;ui.accept=false;m61_text::suspended=true;input('1',false);
    assert(calculator.wakes==2 && !calculator.inputs && !panel.notes);
    puts("Actual input delivery: parked menu arrows/repeat, open/close, digits, services/USB, active core, sleep, boot and M61 wake semantics PASS");
}
'''.replace('@INPUT@',body)
# Initializer-list support is explicit to keep the fixture independent of
# incidental transitive includes in the firmware headers.
fixture='#include <initializer_list>\n'+fixture
with tempfile.TemporaryDirectory(prefix='picocalc-key-delivery-') as directory:
    root=Path(directory);p=root/'test.cpp';p.write_text(fixture);binary=root/'test'
    flags=['-fsanitize=address,undefined','-fno-omit-frame-pointer'] if os.environ.get('MK61_TEST_SANITIZERS')=='1' else []
    subprocess.run([os.environ.get('CXX','clang++'),'-std=c++17','-O2','-Wall','-Wextra','-Werror',*flags,'-I'+str(ROOT/'ports/picocalc'),'-I'+str(ROOT/'code'),str(p),'-o',str(binary)],check=True)
    subprocess.run([str(binary)],check=True)

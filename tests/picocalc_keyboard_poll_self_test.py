#!/usr/bin/env python3
"""Actual Keyboard::poll under the M3's documented1s selection expiry."""
from pathlib import Path
import hashlib,subprocess,tempfile
ROOT=Path(__file__).resolve().parents[1]

def body(text):
 start=text.index('bool Keyboard::request_register(')if 'bool Keyboard::request_register('in text else text.index('bool Keyboard::poll(')
 end=text.find('void Keyboard::clock_changed()',start)
 return text[start:end if end>=0 else len(text)]

fixture=r'''
#include "hardware.hpp"
#include "diagnostics.hpp"
#include <cassert>
#include <cstdio>
#include <vector>
static uint64_t ticks;
uint64_t time_us_64(){return ticks;}
namespace picocalc::diagnostics {
 Scope::Scope(Point p):point_(p),start_(0),generation_(0){}
 Scope::~Scope(){assert(point_==Point::KEYBOARD&&start_==0&&generation_==0);}
}
struct Bus {
 bool pending=false,selected=false;unsigned reg=0;uint64_t at=0;int count=0;uint8_t bytes[2]{};
 unsigned stale=0,writes=0,reads=0;uint8_t level=100,key_state=0,key_code=0;bool permit=true;
 void expire(){if(selected&&ticks-at>=1000000)selected=false;}
} bus;
namespace picocalc::io_worker {
 bool request_i2c(bool read,const u8* p,unsigned n){
  if(!bus.permit)return false;
  assert(!bus.pending&&n==(read?2u:1u));bus.expire();bus.pending=true;bus.count=(int)n;
  if(!read){bus.reg=p[0];bus.at=ticks;bus.selected=true;++bus.writes;}
  else {++bus.reads;if(!bus.selected){bus.bytes[0]=bus.bytes[1]=0;++bus.stale;}
   else if(bus.reg==0x0b){bus.bytes[0]=0x0b;bus.bytes[1]=bus.level;}
   else if(bus.reg==BIOS_POWER_REG){bus.bytes[0]=BIOS_POWER_REG;bus.bytes[1]=0xbb;}
   else if(bus.reg==1){bus.bytes[0]=1;bus.bytes[1]=0;}
   else {bus.bytes[0]=bus.key_state;bus.bytes[1]=bus.key_code;bus.key_state=0;}
   bus.selected=false;
  }return true;
 }
 bool take_i2c(int& n,u8* p){if(!bus.pending)return false;n=bus.count;if(n==2){p[0]=bus.bytes[0];p[1]=bus.bytes[1];}bus.pending=false;return true;}
}
namespace picocalc {
ACTUAL_BODY
}
static void poll(picocalc::Keyboard& k,unsigned delta=1000){ticks+=delta;picocalc::KeyEvent event{};(void)k.poll(event);}
static void selected(picocalc::Keyboard& k,unsigned reg){
 for(unsigned i=0;i<1000&&!(bus.selected&&bus.reg==reg);++i)poll(k);
 assert(bus.selected&&bus.reg==reg);poll(k);
}
int main(){
 // Complete a FIFO request, then select the legacy battery register.
 bus={};ticks=0;picocalc::Keyboard k;
 for(unsigned i=0;i<200&&!(bus.selected&&bus.reg==0x0b);++i)poll(k);
 assert(bus.selected&&bus.reg==0x0b);poll(k); // physical selection complete
 poll(k,1200000); // core0 can be inside an SD call that feeds the watchdog
 for(unsigned i=0;i<100&&k.battery().percent!=100;++i)poll(k);
#ifdef BASELINE
 assert(bus.stale==1&&k.battery_errors()==1);
 puts("Archived actual poll: delayed1.2s selection -> valid wire0,0 -> BATTERY_ERRORS+1, no bus error: reproduced");
#else
 assert(bus.stale==0&&k.battery_errors()==0&&k.battery().percent==100);
 assert(k.selection_restarts()==1);
 // The lease applies equally to key FIFO, version discovery and power.
 for(unsigned reg:{9u,1u,unsigned(BIOS_POWER_REG)}){
  bus={};ticks=0;picocalc::Keyboard p;selected(p,reg);poll(p,1200000);
  for(unsigned i=0;i<50;++i)poll(p);
  assert(bus.stale==0&&p.selection_restarts()==1&&p.errors()==0&&p.battery_errors()==0);
 }
 // Renew at the guard, not on an ordinary delayed but still valid read.
 for(unsigned age:{899999u,900000u}){
  bus={};ticks=0;picocalc::Keyboard p;selected(p,0x0b);ticks=bus.at+age;
  picocalc::KeyEvent e{};(void)p.poll(e);
  assert(p.selection_restarts()==unsigned(age==900000));
  for(unsigned i=0;i<50;++i)poll(p);
  assert(bus.stale==0&&p.battery_errors()==0&&p.battery().percent==100);
 }
 // An unavailable physical slot must leave the renewal pending. No read
 // may overtake the replacement selection and no retry is counted early.
 bus={};ticks=0;picocalc::Keyboard blocked;selected(blocked,0x0b);bus.permit=false;poll(blocked,1200000);
 assert(blocked.selection_restarts()==0);bus.permit=true;
 for(unsigned i=0;i<60;++i)poll(blocked);
 assert(blocked.selection_restarts()==1&&bus.stale==0&&blocked.battery_errors()==0);
 // Once a read completed, its buffered key remains valid across a long
 // core0 pause; renewing at that point would drop the already-popped key.
 bus={};ticks=0;bus.key_state=1;bus.key_code='A';picocalc::Keyboard buffered;
 for(unsigned i=0;i<100&&!(bus.pending&&bus.count==2&&bus.reg==9);++i)poll(buffered);
 assert(bus.pending&&bus.count==2);ticks+=1200000;picocalc::KeyEvent event{};
 assert(buffered.poll(event)&&event.code=='A'&&buffered.selection_restarts()==0&&bus.reads==1);
 // Both UNKNOWN encodings are valid peer responses; corruption101..126
 // remains a protocol error and must retain its exact first bad reply.
 for(uint8_t raw:{uint8_t(127),uint8_t(255),uint8_t(101),uint8_t(126)}){
  bus={};bus.level=raw;ticks=0;picocalc::Keyboard p;
  for(unsigned i=0;i<300;++i)poll(p);
  if((raw&127)==127){assert(p.battery_errors()==0&&p.battery_unknown_reads()==1&&p.battery().percent==-1);}
  else {assert(p.battery_errors()==1);const auto f=p.battery_fault();assert(f.phase==4&&f.reg==0x0b&&f.value==raw&&f.count==2);}
 }
 puts("Actual poll: key/battery/version/power lease renewed, guard boundary, blocked admission, buffered key retained; UNKNOWN accepted, malformed reply counted/captured PASS");
#endif
}
'''
def run(text,baseline):
 with tempfile.TemporaryDirectory(prefix='keyboard-poll-')as d:
  p=Path(d);source=p/'test.cpp';source.write_text(fixture.replace('ACTUAL_BODY',body(text)))
  cmd=['clang++','-std=c++17','-DMK61_CORE_STANDALONE=1','-O2','-Wall','-Wextra','-Werror','-Wno-unused-function','-fsanitize=address,undefined','-fno-sanitize-recover=all','-I'+str(ROOT/'ports/picocalc'),'-I'+str(ROOT/'code'),str(source),'-o',str(p/'test')]
  if baseline:cmd.insert(1,'-DBASELINE=1')
  subprocess.run(cmd,check=True);subprocess.run([str(p/'test')],check=True)
if __name__=='__main__':
 import argparse
 ap=argparse.ArgumentParser();ap.add_argument('--baseline-only',action='store_true');a=ap.parse_args()
 old=(ROOT/'tests/fixtures/picocalc_keyboard_poll_before_renewal.inc').read_text()
 assert hashlib.sha256(body(old).rstrip().encode()).hexdigest()=='d6ea3d16626c34a6e106175ab95e5f3400f788c72cada8a8ee39367902f90e70'
 run(old,True)
 if not a.baseline_only:run((ROOT/'ports/picocalc/hardware.cpp').read_text(),False)

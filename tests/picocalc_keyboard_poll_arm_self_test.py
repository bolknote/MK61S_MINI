#!/usr/bin/env python3
"""Actual sealed Pico Keyboard ARM; modeled peer expiry/UNKNOWN, no device I/O."""
from pathlib import Path
import argparse,hashlib,json,re,struct,subprocess,sys
ROOT=Path(__file__).resolve().parents[1];sys.path[:0]=[str(ROOT/'tests'),str(ROOT/'sdk/coproc')]
from elf32 import ELF
from unicorn_runtime import Uc
from unicorn import UC_ARCH_ARM,UC_MODE_MCLASS,UC_MODE_THUMB,UC_HOOK_CODE,UC_HOOK_MEM_READ,UC_HOOK_MEM_WRITE
from unicorn.arm_const import *
EVENT=0x20030000;STACK=0x20041000;STOP=0x2003e000

def symbol(e,pattern):
 values=[v['value']for k,v in e.symbols.items()if re.fullmatch(pattern,k)];assert len(values)==1,(pattern,values);return values[0]
def layout(gdb,path):
 out=subprocess.run([str(gdb),'-nx','-batch',str(path),'-iex','set auto-load python-scripts off','-ex',"ptype /o 'picocalc::Keyboard'"],capture_output=True,text=True,check=True).stdout
 fields={}
 for name in ('battery_errors_','errors_','selected_at_','selected_reg_','selection_restarts_','battery_unknown_reads_','battery_fault_'):
  m=re.search(r'/\*\s*(\d+)\s*\|\s*(\d+)\s*\*/[^\n]*\b'+name+r';',out)
  if m:fields[name]=(int(m[1]),int(m[2]))
 # A nested structure's label occurs after its body; get its offset from the
 # first at_us field, which is also the start of BatteryFault.
 m=re.search(r'/\*\s*(\d+)\s*\|\s*4\s*\*/[^\n]*\bat_us;',out)
 if m:fields['battery_fault_']=(int(m[1]),16)
 sizes=re.findall(r'total size \(bytes\):\s*(\d+)',out);assert sizes
 fields['size']=(int(sizes[-1]),0);assert fields['battery_errors_']==(40,4)
 return fields
class Machine:
 def __init__(self,e,fields,level=100):
  self.e=e;self.fields=fields;self.u=Uc(UC_ARCH_ARM,UC_MODE_MCLASS|UC_MODE_THUMB)
  for at,n in ((0x10000000,0x200000),(0x20000000,0x42000),(0x40000000,0x60000)):self.u.mem_map(at,n)
  for seg in e.segments:
   if seg['data']:self.u.mem_write(seg['address'],seg['data'])
  self.keyboard=symbol(e,r'_ZN12_GLOBAL__N_18keyboardE');self.entry=symbol(e,r'_ZN8picocalc8Keyboard4pollE.*')
  self.request=symbol(e,r'_ZN8picocalc9io_worker11request_i2cE.*')&~1;self.take=symbol(e,r'_ZN8picocalc9io_worker8take_i2cE.*')&~1
  self.now=0;self.pending=False;self.selected=False;self.at=0;self.reg=0;self.count=0;self.reply=bytes(2);self.level=level
  self.stale=self.reads=self.writes=0;self.minimum=STACK
  self.u.hook_add(UC_HOOK_CODE,self.code);self.u.hook_add(UC_HOOK_MEM_READ,self.read);self.u.hook_add(UC_HOOK_MEM_WRITE,self.write)
 def get(self,at):return struct.unpack('<I',self.u.mem_read(at,4))[0]
 def put(self,at,value):self.u.mem_write(at,struct.pack('<I',value&0xffffffff))
 def stat(self,name):return self.get(self.keyboard+self.fields[name][0])
 def done(self,value):self.u.reg_write(UC_ARM_REG_R0,value);self.u.reg_write(UC_ARM_REG_PC,self.u.reg_read(UC_ARM_REG_LR))
 def read(self,u,access,at,size,value,user):
  if at==0x40054024:self.put(at,self.now>>32)
  if at==0x40054028:self.put(at,self.now)
 def write(self,u,access,at,size,value,user):
  assert self.keyboard<=at and at+size<=self.keyboard+self.fields['size'][0]or EVENT<=at and at+size<=EVENT+32 or STACK-2048<=at and at+size<=STACK,('unexpected ARM write',hex(at),size)
 def code(self,u,pc,size,user):
  self.minimum=min(self.minimum,u.reg_read(UC_ARM_REG_SP))
  if pc==self.request:
   assert not self.pending
   read=u.reg_read(UC_ARM_REG_R0);n=u.reg_read(UC_ARM_REG_R2);assert n==(2 if read else 1)
   if self.selected and self.now-self.at>=1000000:self.selected=False
   self.pending=True;self.count=n
   if read:
    self.reads+=1
    if not self.selected:self.reply=bytes(2);self.stale+=1
    elif self.reg==0x0b:self.reply=bytes((0x0b,self.level))
    elif self.reg==0x0f:self.reply=bytes((0x0f,0xbb))
    elif self.reg==1:self.reply=bytes((1,0))
    else:self.reply=bytes(2)
    self.selected=False
   else:
    self.reg=u.mem_read(u.reg_read(UC_ARM_REG_R1),1)[0];self.at=self.now;self.selected=True;self.writes+=1
   self.done(1)
  elif pc==self.take:
   if not self.pending:self.done(0);return
   self.put(u.reg_read(UC_ARM_REG_R0),self.count)
   if self.count==2:u.mem_write(u.reg_read(UC_ARM_REG_R1),self.reply)
   self.pending=False;self.done(1)
 def poll(self,delay=1000):
  self.now+=delay;self.u.reg_write(UC_ARM_REG_R0,self.keyboard);self.u.reg_write(UC_ARM_REG_R1,EVENT)
  self.u.reg_write(UC_ARM_REG_SP,STACK);self.u.reg_write(UC_ARM_REG_LR,STOP|1);self.u.reg_write(UC_ARM_REG_XPSR,0x1000000);self.u.reg_write(UC_ARM_REG_PRIMASK,0)
  self.u.emu_start(self.entry|1,STOP,count=100000)
  assert self.u.reg_read(UC_ARM_REG_PC)==STOP and self.u.reg_read(UC_ARM_REG_SP)==STACK and not self.u.reg_read(UC_ARM_REG_PRIMASK)
 def prime(self):
  for _ in range(500):
   if self.selected and self.reg==0x0b:break
   self.poll()
  assert self.selected and self.reg==0x0b;self.poll()

def main():
 ap=argparse.ArgumentParser(description=__doc__);ap.add_argument('--reference-elf',type=Path,required=True);ap.add_argument('--elf',type=Path,required=True);ap.add_argument('--gdb',type=Path,required=True);ap.add_argument('--output',type=Path,required=True);a=ap.parse_args()
 ref=ELF(a.reference_elf);candidate=ELF(a.elf);rl=layout(a.gdb,a.reference_elf);cl=layout(a.gdb,a.elf)
 old=Machine(ref,rl);old.prime();old.poll(1200000)
 for _ in range(50):old.poll()
 assert old.stale==1 and old.stat('battery_errors_')==1
 unknown=Machine(ref,rl,127)
 for _ in range(300):unknown.poll()
 assert unknown.stat('battery_errors_')==1
 cases=0
 for origin in (0,0xffff0000,0x1ffff0000):
  for delay in (16000,899999,900000,1200000):
   m=Machine(candidate,cl);m.now=origin;m.prime();m.now=m.at;m.poll(delay)
   for _ in range(100):m.poll()
   assert m.stale==0 and m.stat('battery_errors_')==0
   assert m.stat('selection_restarts_')==int(delay>=900000);cases+=1
 for level in (0,100,127,255,101,126):
  m=Machine(candidate,cl,level)
  for _ in range(300):m.poll()
  if level&127==127:assert m.stat('battery_errors_')==0 and m.stat('battery_unknown_reads_')==1
  elif level>100:
   assert m.stat('battery_errors_')==1
   fault=bytes(m.u.mem_read(m.keyboard+cl['battery_fault_'][0],16));at,elapsed,count,phase,reg,value,selected=struct.unpack('<IIi4B',fault)
   assert (count,phase,reg,value,selected)==(2,4,0x0b,level,0x0b)and 16000<=elapsed<100000
  else:assert m.stat('battery_errors_')==0
  cases+=1
 result=dict(status='PASS',physical_io=False,hardware_timing_measured=False,reference_stale_read_and_unknown_errors_reproduced=True,actual_firmware_ARM_cases=cases,reference_sha256=hashlib.sha256(a.reference_elf.read_bytes()).hexdigest(),candidate_sha256=hashlib.sha256(a.elf.read_bytes()).hexdigest(),scope='Actual sealed Pico Keyboard/request_register/fault ARM, DWARF-pinned objects, modeled I2C peer1s expiry and documented UNKNOWN, normal/guard/late/32bit rollover, malformed reply capture; no runtime or counter fields edited')
 a.output.write_text(json.dumps(result,indent=2)+'\n');print(json.dumps(result,indent=2))
if __name__=='__main__':main()

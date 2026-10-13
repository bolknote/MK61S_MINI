#!/usr/bin/env python3
"""Differentially run old/new production ARM snprintf, including nano-specific ABI."""
import argparse,struct,random
from pathlib import Path
from unicorn import Uc,UC_ARCH_ARM,UC_MODE_THUMB,UC_MODE_MCLASS
from unicorn.arm_const import *
from run_portable_system_arm_tests import Elf
p=argparse.ArgumentParser();p.add_argument('baseline',type=Path);p.add_argument('candidate',type=Path);a=p.parse_args()
class Formatter:
 def __init__(self,path):
  self.elf=Elf(path);self.u=Uc(UC_ARCH_ARM,UC_MODE_THUMB|UC_MODE_MCLASS)
  self.u.mem_map(0x08000000,0x100000);self.u.mem_map(0x20000000,0x20000);self.elf.load(self.u)
  self.stop=0x080FF000;self.u.mem_write(self.stop,b'\x70\x47')
 def call(self,fmt,cap,args):
  u=self.u;sp=0x2001FFD0;dest=0x20017000;f=0x20017400;text=0x20017500
  u.mem_write(dest,b'\xCD'*160);u.mem_write(f,fmt.encode()+b'\0');u.mem_write(text,b'abcdef ghijklmnop\0')
  for r,v in [(UC_ARM_REG_SP,sp),(UC_ARM_REG_LR,self.stop|1),(UC_ARM_REG_R0,dest+8),(UC_ARM_REG_R1,cap),(UC_ARM_REG_R2,f),(UC_ARM_REG_R3,0xDEAD)]:u.reg_write(r,v)
  u.reg_write(UC_ARM_REG_XPSR,0x01000000)
  u.mem_write(sp-4096,b'\0'*4096)
  slot=3
  for kind,value in args:
   if kind in ['d','q']:slot=(slot+1)&~1;wire=struct.pack('<d' if kind=='d' else '<Q',value)
   else:wire=struct.pack('<I',(text if kind=='s' else value)&0xffffffff)
   if slot==3:u.reg_write(UC_ARM_REG_R3,struct.unpack('<I',wire)[0])
   else:u.mem_write(sp+(slot-4)*4,wire)
   slot+=len(wire)//4
  u.emu_start(self.elf.symbols['snprintf']|1,self.stop,timeout=2000000,count=2000000)
  assert u.reg_read(UC_ARM_REG_PC)==self.stop
  return u.reg_read(UC_ARM_REG_R0),bytes(u.mem_read(dest,160))
old,new=Formatter(a.baseline),Formatter(a.candidate);cases=0
random.seed(61)
for _ in range(1200):
 flags=random.choice(['','-','+',' ','0','#','-0','+0','#0']);width=random.choice([0,1,7,16,35]);prec=random.choice([-1,0,1,4,12])
 conv=random.choice(['d','u','x','X','o','c','s','p']);fmt='['+'%'+flags+str(width)+('' if prec<0 else '.'+str(prec))+conv+']'
 # Old nano tests uninitialized pdata.size for #o with explicit precision.
 # That undefined stack-dependent behavior is not an ABI contract.
 if conv=='o' and '#' in flags and prec>=0:continue
 value=random.getrandbits(32);args=[('s',0)] if conv=='s' else [('i',value)]
 for cap in [0,1,2,7,16,64]:
  before=old.call(fmt,cap,args);after=new.call(fmt,cap,args)
  assert before==after,(fmt,cap,args,before[0],after[0],before[1][8:72],after[1][8:72]);cases+=1
for fmt,args in [('[%a] %u',[('d',1.25),('i',7)]),('[%f] %u',[('d',1.25),('i',7)]),('[%lld] %u',[('q',0x123456789),('i',7)]),('[%zu]',[('i',12)]),('[%hhu]',[('i',257)]),('[%ls]',[('s',0)]),('[%q]',[]),('[%#o]',[('i',0)]),('[%p]',[('i',0)]),('[%.0u]',[('i',0)])]:
 for cap in [0,1,7,64]:
  assert old.call(fmt,cap,args)==new.call(fmt,cap,args),(fmt,cap);cases+=1
print('Compact formatter ARM/nano ABI:',cases,'bounded-output differential cases PASS')

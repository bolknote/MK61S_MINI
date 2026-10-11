#!/usr/bin/env python3
"""Qualify retained buffers against real ARM allocators (WS ELF, Classic ELF)."""
import re,struct,sys
from pathlib import Path
sys.path.insert(0,str(Path(__file__).resolve().parent))
from run_portable_system_arm_tests import Elf
from unicorn import Uc,UC_ARCH_ARM,UC_MODE_THUMB,UC_MODE_MCLASS
from unicorn.arm_const import *
owner_names=re.findall(r'MK61_SHARED_MEMORY_OWNER\(\s*([A-Z_]+)',Path(str(Path(__file__).resolve().parents[1]/"code/shared_memory_owner_catalog.inc")).read_text())
owner={n:i for i,n in enumerate(owner_names)}
for path,bulk in [(sys.argv[1],False),(sys.argv[2],True)]:
 e=Elf(Path(path));u=Uc(UC_ARCH_ARM,UC_MODE_MCLASS|UC_MODE_THUMB)
 u.mem_map(0x08000000,0x100000);u.mem_map(0x20000000,0x20000);e.load(u)
 u.reg_write(UC_ARM_REG_C1_C0_2,0xF00000);u.reg_write(UC_ARM_REG_FPEXC,0x40000000)
 stop=0x080FF000;obj=0x2001C800
 def call(name,*args):
  u.reg_write(UC_ARM_REG_SP,e.symbol('_estack')-16);u.reg_write(UC_ARM_REG_LR,stop|1)
  for r,v in zip([UC_ARM_REG_R0,UC_ARM_REG_R1,UC_ARM_REG_R2,UC_ARM_REG_R3],args):u.reg_write(r,v)
  u.emu_start(e.symbol(name)|1,stop,count=1000000)
  assert u.reg_read(UC_ARM_REG_PC)==stop,(name,hex(u.reg_read(UC_ARM_REG_PC)))
  return u.reg_read(UC_ARM_REG_R0)
 def word(p):return struct.unpack('<I',u.mem_read(p,4))[0]
 def acquire(p,arena,kind,size):
  u.mem_write(p,bytes(48));assert call('_ZN13shared_memory5Lease7acquire',p,arena,owner[kind],size)==1
  return word(p+4)
 heap_symbol=e.symbol('11heap_cursor')
 # IRQ allocation must refuse before changing any allocator/arena state.
 initial=word(heap_symbol);u.reg_write(UC_ARM_REG_IPSR,16)
 assert call('24allocate_retained_buffer',8192)==0
 assert word(heap_symbol)==initial
 u.reg_write(UC_ARM_REG_IPSR,0)
 wk=acquire(obj,0,'LANGUAGE_VM',8192);data=bytes(range(256))*32;u.mem_write(wk,data)
 call('_ZN13shared_memory5Lease5reset',obj)
 wk2=acquire(obj,0,'LANGUAGE_VM',8192);assert wk==wk2 and u.mem_read(wk,8192)==data
 call('_ZN13shared_memory5Lease5reset',obj)
 part=obj+64;u.mem_write(part,bytes(16))
 assert call('18WorkspacePartition4open',part,owner['LANGUAGE_VM'],4016)==1
 tail=word(part+4);tail_data=bytes([0x7B])*4016;u.mem_write(tail,tail_data)
 short=acquire(obj+128,0,'LANGUAGE_VM',8192-4016)
 assert short==wk;u.mem_write(short,bytes([0xA5])*(8192-4016))
 call('_ZN13shared_memory5Lease5reset',obj+128);assert call('18WorkspacePartition5close',part)==1
 assert u.mem_read(tail,4016)==tail_data
 for size in [24576,8308]:assert call('24allocate_retained_buffer',size)
 if bulk:
  p=acquire(obj+192,2,'PROGRAM_STORE_COMPRESSION',8192)
  u.mem_write(p,bytes([0x42])*8192);call('_ZN13shared_memory5Lease5reset',obj+192)
 app=acquire(obj+256,4,'LOADABLE_MODULE',20480)
 u.mem_write(app,bytes([0xCD])*20480)
 stage=acquire(obj+320,3,'VFAT_STAGE',2560);u.mem_write(stage,bytes([0xA6])*2560)
 previous=word(heap_symbol)
 assert call('24allocate_retained_buffer',65536)==0
 assert word(heap_symbol)==previous
 assert u.mem_read(app,20480)==bytes([0xCD])*20480
 assert u.mem_read(stage,2560)==bytes([0xA6])*2560
 assert u.mem_read(tail,4016)==tail_data
 call('_ZN13shared_memory5Lease5reset',obj+320);call('_ZN13shared_memory5Lease5reset',obj+256)
 print(path,'IRQ refusal, workspace retention/partition, APP+stage coexistence, OOM immutability PASS',flush=True)

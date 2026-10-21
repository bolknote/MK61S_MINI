#!/usr/bin/env python3
"""Run actual ARM bodies, checking byte bounds, AAPCS, guards and contents."""
import argparse,hashlib,json,random,sys
from pathlib import Path
ROOT=Path(__file__).resolve().parents[2]
sys.path.insert(0,str(ROOT/'tests'))
from check_stm32_vectors import ElfImage
from unicorn import *
from unicorn.arm_const import *
p=argparse.ArgumentParser(description=__doc__)
p.add_argument('--elf',type=Path,required=True);p.add_argument('--cpu',choices=('m0','m4'),required=True)
p.add_argument('--output',type=Path,required=True)
p.add_argument('--names',nargs='+')
a=p.parse_args();e=ElfImage(a.elf)
u=Uc(UC_ARCH_ARM,UC_MODE_THUMB|UC_MODE_MCLASS)
u.ctl_set_cpu_model(UC_CPU_ARM_CORTEX_M0 if a.cpu=='m0' else UC_CPU_ARM_CORTEX_M4)
u.mem_map(0x20000000,0x100000);u.mem_map(0x08000000,0x100000);e.load(u)
u.mem_map(0x10000000,4096)
stop=0x10000000;sp=0x200fe000;src=0x20020000;dst=0x20050000
if a.cpu=='m0':
 raw=(ROOT/'research/rp2040-memset-2026-10-21/capture/bootrom.bin').read_bytes()
 u.mem_map(0,0x10000);u.mem_write(0,raw);e.symbols['bootrom']=0x261d
else:
 raw=(ROOT/'research/stm32f411-rom-2026-10-21/capture/rom-a.bin').read_bytes()
 u.mem_map(0x1fff0000,0x10000);u.mem_write(0x1fff0000,raw)
names=a.names or [n for n in ('baseline','own16','own64','memcpy','rom_copy','byte_copy','bootrom') if n in e.symbols]
r=random.Random(610411)
cases=[(n,s,d) for n in range(258) for s in range(4) for d in range(4)]
cases += [(n,s,d) for n in (511,512,513,1023,1024,1025,4095,4096,4097,16383,16384,65535,65536) for s in range(4) for d in range(4)]
cases += [(r.randrange(8193),r.randrange(16),r.randrange(16)) for _ in range(500)]
cases += [(0,0,0)]
active=[0,0,0]
pattern=bytes(r.getrandbits(8) for _ in range(65664))
saved={i:0x72816201+i*314 for i in range(UC_ARM_REG_R4,UC_ARM_REG_R11+1)}
def access(cpu,typ,addr,size,value,user):
 n,s,d=active
 if a.cpu=='m0':assert size in (1,2,4) and addr%size==0,('alignment',hex(addr),size,active)
 if typ==UC_MEM_WRITE:
  assert (d<=addr and addr+size<=d+n) or sp-64<=addr<sp,('write bound',hex(addr),size,active)
 elif 0x20010000<=addr<0x200f0000:
  assert s<=addr and addr+size<=s+n,('read bound',hex(addr),size,active)
u.hook_add(UC_HOOK_MEM_READ|UC_HOOK_MEM_WRITE,access)
results=[]
for name in names:
 for i,(n,so,do) in enumerate(cases):
  s=src+so;d=dst+do
  if i==len(cases)-1:s=d=0
  active[:]=[n,s,d]
  u.mem_write(src-16,pattern[:n+64]);u.mem_write(dst-16,b'\x5A'*(n+64))
  expected=bytes(u.mem_read(s,n)) if n else b''
  for reg,v in saved.items():u.reg_write(reg,v)
  for reg,v in ((UC_ARM_REG_R0,d),(UC_ARM_REG_R1,s),(UC_ARM_REG_R2,n),(UC_ARM_REG_SP,sp),(UC_ARM_REG_LR,stop|1),(UC_ARM_REG_XPSR,0x01000000)):
   u.reg_write(reg,v)
  try:u.emu_start(e.symbols[name]|1,stop,count=1000000)
  except Exception:print('FAIL',name,n,so,do,hex(u.reg_read(UC_ARM_REG_PC)));raise
  assert u.reg_read(UC_ARM_REG_PC)==stop,(name,n,so,do,'return')
  assert u.reg_read(UC_ARM_REG_R0)==d and u.reg_read(UC_ARM_REG_SP)==sp,(name,n,so,do,'AAPCS return')
  assert all(u.reg_read(reg)==v for reg,v in saved.items()),(name,n,so,do,'callee saved')
  actual=bytes(u.mem_read(dst-16,n+64))
  want=b'\x5A'*(16+do)+expected+b'\x5A'*(48-do)
  assert actual==want,(name,n,so,do,'content')
  assert bytes(u.mem_read(src-16,n+64))==pattern[:n+64],(name,'source modified')
 row=dict(name=name,cases=len(cases),bytes=e.sizes.get(name),status='PASS');results.append(row);print(row,flush=True)
a.output.write_text(json.dumps(dict(cpu=a.cpu,elf_sha256=hashlib.sha256(a.elf.read_bytes()).hexdigest(),results=results),indent=2)+'\n')

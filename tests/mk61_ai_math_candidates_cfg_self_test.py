#!/usr/bin/env python3
"""Check final APP control flow and reproduce failed003's invalid fallthrough."""
import argparse
import hashlib
import json
from pathlib import Path
import re
import struct
import subprocess
import sys

ROOT=Path(__file__).resolve().parents[1]
sys.path[:0]=[str(ROOT),str(ROOT/'tests')]
from check_stm32_vectors import ElfImage
from prepare_mk61_ai_math_candidates import records
from tools.apps.packer.app_relocations import extract

def sha(path):return hashlib.sha256(Path(path).read_bytes()).hexdigest()
def symbol(elf,part):
 names=[n for n in elf.symbols if part in n and elf.sizes.get(n,0)]
 assert len(names)==1,(part,names)
 return names[0],elf.symbols[names[0]]&~1

def cfg(elf,tool):
 text=subprocess.check_output([str(tool),'-d',str(elf.path)],text=True)
 instructions={}
 for line in text.splitlines():
  parts=line.split('\t')
  if len(parts)<3 or not re.fullmatch(r'\s*[0-9a-f]+:',parts[0]):continue
  addr=int(parts[0].strip()[:-1],16);mn=parts[2].strip().split('.')[0]
  if mn.startswith('.'):continue
  size=sum(len(token)//2 for token in parts[1].split())
  instructions[addr]=(mn,parts[3].strip() if len(parts)>3 else '',size)
 def walk(name):
  start=elf.symbols[name]&~1;end=start+elf.sizes[name];seen=set();pending=[start];calls=[]
  while pending:
   addr=pending.pop()
   if addr in seen or not start<=addr<end or addr not in instructions:continue
   seen.add(addr);mn,args,size=instructions[addr]
   target=re.match(r'([0-9a-f]+)\s',args);target=int(target[1],16) if target else None
   if mn=='bl' and target is not None:calls.append((addr,target))
   if mn in ('bx','bkpt','udf') or (mn=='pop' and 'pc' in args):continue
   if mn=='b':
    if target is not None:pending.append(target)
    continue
   if mn.startswith('b') and mn not in ('bl','blx') and target is not None:pending.append(target)
   pending.append(addr+size)
  return seen,calls
 return instructions,walk

def positive(base,tool):
 elf=ElfImage(base/'app/MATHCAND.elf');elf.path=base/'app/MATHCAND.elf'
 instructions,walk=cfg(elf,tool)
 flow,entry=symbol(elf,'mk61_app_flow_step');del entry
 stage,stage_address=symbol(elf,'5stageEj');del stage
 pair,pair_address=symbol(elf,'m0_math_pair_probe');del pair
 submit,submit_address=symbol(elf,'13submit_worker');join,join_address=symbol(elf,'11join_worker')
 seen,calls=walk(flow);assert any(target==pair_address for _,target in calls),'Two-core validation removed'
 markers=set()
 for addr,target in calls:
  if target!=stage_address:continue
  for prior in range(addr-2,max(addr-10,0),-2):
   item=instructions.get(prior)
   if item and item[0]=='movs':
    match=re.fullmatch(r'r0, #(\d+)(?:\s.*)?',item[1])
    if match:markers.add(int(match[1]));break
 assert {3,4,5,6,7,60,61,62,63}<=markers,('Missing reachable stage',markers)
 # Exclude validation probes: the ordinary timed path must itself retain
 # real worker submission/join, beyond the standalone emulation entrypoints.
 names={value&~1:name for name,value in elf.symbols.items() if elf.sizes.get(name,0)}
 pending=[flow];visited=set();targets=set()
 while pending:
  name=pending.pop()
  if name in visited:continue
  visited.add(name)
  for _,target in walk(name)[1]:
   targets.add(target)
   if target in names and not names[target].startswith('m0_math_'):pending.append(names[target])
 assert submit_address in targets and join_address in targets,'Timed two-core dispatch removed'
 for name in (submit,join):
  nodes,_=walk(name)
  assert any(instructions[a][0] in ('blx','bx') for a in nodes),'Adapter has no native call/return'
 return dict(reachable_markers=sorted(markers),timed_two_core_submit_and_join=True,
             real_pair_probe_in_flow=True,flow_instructions=len(seen))

def negative(base,bad_dir,resident,rom):
 from native_eabi_m0_arm_self_test import Machine,SP,STOP
 from unicorn import UC_HOOK_CODE
 from unicorn.arm_const import (UC_ARM_REG_R0,UC_ARM_REG_R1,UC_ARM_REG_R2,UC_ARM_REG_R4,
     UC_ARM_REG_R5,UC_ARM_REG_R6,UC_ARM_REG_R7,UC_ARM_REG_SP,UC_ARM_REG_LR,UC_ARM_REG_PC,UC_ARM_REG_XPSR)
 manifest=json.loads((bad_dir/'MATHCAND.json').read_text());app=ElfImage(bad_dir/'MATHCAND.elf')
 base_address=0x2001e450;delta=base_address-0x20000000
 class Replay(Machine):
  def write(self,uc,access,address,size,value,user):
   if base_address<=address and address+size<=base_address+manifest['memory_bytes']:return
   return super().write(uc,access,address,size,value,user)
 m=Replay(resident,True,stack_bytes=16384,instruction_budget=1000000,bootrom=rom)
 image=bytearray(app.bytes_at(app.named_sections['.module_image']))
 offsets,_=extract(bad_dir/'MATHCAND.elf',0x20000000,manifest['image_bytes'],manifest['memory_bytes'])
 for at in offsets:struct.pack_into('<I',image,at,struct.unpack_from('<I',image,at)[0]+delta)
 m.uc.mem_write(base_address,bytes(image))
 runtime=next(v for n,v in m.elf.symbols.items() if n.endswith('native_runtimeE'))
 m.uc.mem_write(app.symbols['mk61_app_runtime']+delta,struct.pack('<I',runtime))
 for n,v in app.symbols.items():
  if n.startswith('m0_math_'):m.elf.symbols[n]=v+delta
 _,h,data=next(records((base/'MATHCASE.BIN').read_bytes()))
 m.uc.mem_write(m.elf.symbols['m0_math_header'],struct.pack('<16I',*h));m.uc.mem_write(m.elf.symbols['m0_math_payload'],data)
 assert m.call('m0_math_load',0,width=32)[0]&0xffffffff==1
 common=next(v for n,v in m.elf.symbols.items() if n.endswith('10NativeHost6commonE'))
 native_call=struct.unpack('<I',m.uc.mem_read(common+12,4))[0]
 services=app.symbols['_ZN12_GLOBAL__N_18servicesE']+delta
 m.uc.mem_write(services,struct.pack('<I',common))
 original=app.symbols['_ZN12_GLOBAL__N_18originalE']+delta
 jobs=app.symbols['_ZN12_GLOBAL__N_14jobsE']+delta
 seed=app.symbols['_ZN12_GLOBAL__N_14seedE']+delta
 norms=struct.unpack('<I',m.uc.mem_read(app.symbols['_ZN12_GLOBAL__N_15normsE']+delta,4))[0]
 weights=struct.unpack('<I',m.uc.mem_read(original+44,4))[0]
 sp=SP-512;frame=bytearray(276)
 for at,value in {4:14,8:0,12:services,16:0,20:28,24:14,28:weights,32:128,36:norms,40:4,44:0,48:original,52:seed}.items():struct.pack_into('<I',frame,at,value)
 m.uc.mem_write(sp,bytes(frame));failure={}
 def quiet(uc,address,size,user):
  del address,size,user
  uc.reg_write(UC_ARM_REG_R0,1);uc.reg_write(UC_ARM_REG_PC,uc.reg_read(UC_ARM_REG_LR))
 def copy_check(uc,address,size,user):
  del address,size,user
  dst=uc.reg_read(UC_ARM_REG_R0)
  if not base_address<=dst<base_address+manifest['memory_bytes']:
   failure.update(destination=dst,LR=uc.reg_read(UC_ARM_REG_LR),source=uc.reg_read(UC_ARM_REG_R1),bytes=uc.reg_read(UC_ARM_REG_R2),r4=uc.reg_read(UC_ARM_REG_R4))
   uc.emu_stop()
 for address in (app.symbols['mk61_app_snprintf']+delta,native_call):
  address&=~1;m.uc.hook_add(UC_HOOK_CODE,quiet,begin=address,end=address)
 memcpy=(app.symbols['memcpy']+delta)&~1;m.uc.hook_add(UC_HOOK_CODE,copy_check,begin=memcpy,end=memcpy)
 for reg,value in ((UC_ARM_REG_R4,jobs),(UC_ARM_REG_R5,1),(UC_ARM_REG_R6,14),(UC_ARM_REG_R7,jobs+572),(UC_ARM_REG_SP,sp),(UC_ARM_REG_LR,STOP|1),(UC_ARM_REG_XPSR,0x01000000)):m.uc.reg_write(reg,value)
 m.uc.ctl_flush_tb() # Earlier load/ROM initialization cached memcpy blocks.
 m.uc.emu_start(0x2000170b+delta,STOP,count=100000)
 assert failure==dict(destination=native_call+708,LR=0x2001fb65,source=original,bytes=57,r4=native_call+708),failure
 return dict(status='OLD_BINARY_INVALID_FALLTHROUGH_REPRODUCED',actual_old_elf_sha256=sha(bad_dir/'MATHCAND.elf'),
             modeled_only='snprintf/debug output; real linked setup instructions and resident memcpy ABI',
             stopped_before_invalid_write=True,observed={k:hex(v) for k,v in failure.items()},
             matches_hardware_LR_and_r4=True,predicted_postcopy_r1=hex(original+57))

def main():
 p=argparse.ArgumentParser(description=__doc__);p.add_argument('--package-dir',type=Path,required=True)
 p.add_argument('--negative-dir',type=Path,default=ROOT/'research/picocalc-ai-performance-20261111/math-candidates/regression-003')
 p.add_argument('--rom',type=Path,default=ROOT/'research/rp2040-memset-2026-10-21/capture/bootrom.bin');a=p.parse_args();base=a.package_dir.resolve()
 meta=json.loads((base/'package.json').read_text());commands=json.loads((base/'app/compile_commands.json').read_text())
 tool=Path(commands[0]['arguments'][0]).with_name('arm-none-eabi-objdump')
 good=positive(base,tool);bad=negative(base,a.negative_dir.resolve(),meta['resident_elf'],a.rom)
 out=dict(status='LINKED_CFG_AND_NEGATIVE_ARM_PASS',physical_io=False,app_sha256=sha(base/'app/MATHCAND.APP'),positive=good,negative=bad)
 (base/'cfg-results.json').write_text(json.dumps(out,indent=2)+'\n');print(json.dumps(out,indent=2))
if __name__=='__main__':main()

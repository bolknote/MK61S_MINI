#!/usr/bin/env python3
"""Functional ARM/SIO oracle. This does not predict physical cycle counts."""
import argparse,copy,hashlib,json,random,struct,subprocess,sys,zlib
from pathlib import Path
ROOT=Path(__file__).resolve().parents[3]
sys.path[:0]=[str(ROOT/'tests'),str(ROOT)]
from native_eabi_m0_arm_self_test import Machine,SP,signed
from unicorn import UC_HOOK_MEM_READ,UC_HOOK_CODE
from unicorn.arm_const import UC_ARM_REG_R0,UC_ARM_REG_PC,UC_ARM_REG_LR

class Interpolators:
 def __init__(self):
  self.core=0;self.state=[[[0]*7 for _ in range(2)]for _ in range(2)]
  self.reads=self.writes=0
 def write(self,address,size,value):
  assert size==4 and 0xd0000080<=address<0xd0000100
  off=address-0xd0000080;unit=off//64;off%=64
  offsets=[0,4,8,12,16,44,48]
  assert off in offsets,('unexpected SIO write',hex(address))
  index=offsets.index(off);self.state[self.core][unit][index]=value&(0x007fffff if index>=5 else 0xffffffff)
  self.writes+=1
 def read(self,uc,access,address,size,value,user):
  del access,value,user
  assert size==4
  off=address-0xd0000080;unit=off//64;off%=64;s=self.state[self.core][unit]
  offsets=[0,4,8,12,16,44,48]
  if off in offsets:result=s[offsets.index(off)]
  else:
   assert off in (32,36),('unexpected SIO read',hex(address))
   lane=(off-32)//4;ctrl=s[5+lane]
   assert ctrl&0x7e0000==0,'blend/clamp/force/raw modes are not part of this oracle'
   source=s[(1-lane)if ctrl&(1<<16)else lane]
   shifted=source>>(ctrl&31);lo=(ctrl>>5)&31;hi=(ctrl>>10)&31
   mask=((1<<(hi+1))-1)&~((1<<lo)-1);filtered=shifted&mask
   if ctrl&(1<<15)and filtered&(1<<hi):filtered-=1<<(hi+1)
   result=(s[2+lane]+filtered)&0xffffffff
  uc.mem_write(address,struct.pack('<I',result));self.reads+=1
 def bases(self,table):
  self.state[self.core][0]=[0,0,table,table+512,0,0x2020,0x12028]
  self.state[self.core][1]=[0,0,table+1024,table+1536,0,0x2020,0x12028]

def dot_tests(elf):
 io=Interpolators()
 class Probe(Machine):
  def write(self,uc,access,address,size,value,user):
   if 0xd0000080<=address<0xd0000100:return io.write(address,size,value)
   return super().write(uc,access,address,size,value,user)
 m=Probe(elf,True,stack_bytes=256,instruction_budget=2000)
 m.uc.hook_add(UC_HOOK_MEM_READ,io.read,begin=0xd0000080,end=0xd00000ff)
 source,table=0x20020000,0x20021000;rng=random.Random(0x1a8)
 count=0
 vectors=[[-128]*32,[127]*32,[0]*32,[-128,127]*16,list(range(-16,16))]
 cases=[]
 for x in vectors:
  for mask in (0,1,127,128,129,254,255):cases.append((x,bytes([mask]*16)))
 for mask in range(256):
  cases.append(([rng.randrange(-128,128)for _ in range(32)],bytes((mask+17*i)&255 for i in range(16))))
 for _ in range(512):cases.append(([rng.randrange(-128,128)for _ in range(32)],rng.randbytes(16)))
 for x,w in cases:
  tables=[]
  for g in range(4):tables.append([sum(x[g*8+j]for j in range(8)if mask&(1<<j))for mask in range(256)])
  total=sum(x);raw=struct.pack('<1025h',*(v for t in tables for v in t),total)
  m.uc.mem_write(source,w);m.uc.mem_write(table,raw);io.bases(table)
  expected=sum((1<<p)*tables[g][w[p*4+g]]for p in range(4)for g in range(4))-8*total
  for name,b in [('packed_dot32',table),('interp_dot32',total)]:
   actual=signed(m.call(name,source,b&0xffffffff,width=32)[0]&0xffffffff,32)
   assert actual==expected,(count,name,actual,expected,x,w.hex())
  count+=1
 return dict(status='ARM_SIO_DOT_PASS',physical_io=False,timing_prediction=False,cases=count,
             checks=count*2,all_8bit_indices=True,signed_int8_extremes=True,
             callee_saved_and_SP_checked=True,maximum_stack_bytes=SP-m.stack_lowest,
             SIO_reads=io.reads,SIO_writes=io.writes,elf_sha256=hashlib.sha256(elf.read_bytes()).hexdigest())

def matrix_tests(base):
 from check_stm32_vectors import ElfImage
 from prepare_mk61_ai_math_candidates import records
 from mk61_ai_math_candidates_cfg_self_test import cfg,symbol
 from tools.apps.packer.app_relocations import extract
 meta=json.loads((base/'package.json').read_text())
 digest=lambda p:hashlib.sha256(Path(p).read_bytes()).hexdigest()
 for name,h in meta['source_pins'].items():assert digest(ROOT/name)==h,name
 for name,h in meta['generated'].items():assert digest(base/name)==h,name
 assert digest(meta['resident_elf'])==meta['resident_elf_sha256']
 io=Interpolators()
 rng=random.Random(0x5210)
 for core in range(2):
  for unit in range(2):
   io.state[core][unit]=[rng.getrandbits(32)for _ in range(5)]+[0x1c20,0x10828]
 original_state=copy.deepcopy(io.state)
 class Probe(Machine):
  def __init__(self):
   self.allowed=[]
   super().__init__(meta['resident_elf'],True,stack_bytes=2048,instruction_budget=10000000,
                    bootrom=ROOT/'research/rp2040-memset-2026-10-21/capture/bootrom.bin')
  def write(self,uc,access,address,size,value,user):
   if 0xd0000080<=address<0xd0000100:return io.write(address,size,value)
   if any(lo<=address and address+size<=hi for lo,hi in self.allowed):return
   return super().write(uc,access,address,size,value,user)
 m=Probe();m.uc.hook_add(UC_HOOK_MEM_READ,io.read,begin=0xd0000080,end=0xd00000ff)
 elf=base/'app/INTERP.elf';app=ElfImage(elf);manifest=json.loads((base/'app/INTERP.json').read_text())
 delta=0x20020000-0x20000000
 image=bytearray(app.bytes_at(app.named_sections['.module_image']))
 offsets,_=extract(elf,0x20000000,manifest['image_bytes'],manifest['memory_bytes'])
 for at in offsets:struct.pack_into('<I',image,at,struct.unpack_from('<I',image,at)[0]+delta)
 m.uc.mem_write(0x20020000,bytes(image));bss=app.named_sections['.module_bss']
 m.allowed.append((bss[3]+delta,bss[3]+delta+bss[5]))
 for name in ('_ZN12_GLOBAL__N_18originalE','_ZN12_GLOBAL__N_14jobsE'):
  address=app.symbols[name]+delta;m.allowed.append((address,address+app.sizes[name]))
 runtime=next(v for n,v in m.elf.symbols.items()if n.endswith('native_runtimeE'))
 m.uc.mem_write(app.symbols['mk61_app_runtime']+delta,struct.pack('<I',runtime))
 tables=0x2002b000
 assert 0x20020000+manifest['memory_bytes']<tables-16
 m.allowed.append((tables,tables+8200))
 for name,address in app.symbols.items():
  if name.startswith('m0_interp_'):m.elf.symbols[name]=address+delta
 pointer=next(v for n,v in m.elf.symbols.items()if '6mk61ai4math' in n and n.endswith('5tableE'))
 m.allowed.append((pointer,pointer+4));m.call('_ZN6mk61ai4math10initializeEv',0,width=32)
 m.uc.mem_write(m.elf.symbols['m0_interp_tables'],struct.pack('<I',tables))
 shim=0x081fd000;m.uc.mem_write(shim,bytes.fromhex('10b50c46a047012010bd'))
 submit=next(v for n,v in m.elf.symbols.items()if n.startswith('_ZN8picocalc9io_worker14submit_compute'))&~1
 join=next(v for n,v in m.elf.symbols.items()if n.startswith('_ZN8picocalc9io_worker12join_compute'))&~1
 mailbox=dict(pending=False,submits=0,joins=0,refuse=False)
 def submitting(uc,address,size,user):
  del address,size,user
  assert not mailbox['pending'];mailbox['submits']+=1
  if mailbox['refuse']:
   uc.reg_write(UC_ARM_REG_R0,0);uc.reg_write(UC_ARM_REG_PC,uc.reg_read(UC_ARM_REG_LR))
  else:
   mailbox['pending']=True;io.core=1;uc.reg_write(UC_ARM_REG_PC,shim|1)
 def core0(uc,address,size,user):
  del uc,address,size,user
  assert io.core==1;io.core=0
 def joining(uc,address,size,user):
  del address,size,user
  assert mailbox['pending'];mailbox['pending']=False;mailbox['joins']+=1
  assert io.core==0;uc.reg_write(UC_ARM_REG_PC,uc.reg_read(UC_ARM_REG_LR))
 m.uc.hook_add(UC_HOOK_CODE,submitting,begin=submit,end=submit)
 m.uc.hook_add(UC_HOOK_CODE,core0,begin=shim+6,end=shim+6)
 m.uc.hook_add(UC_HOOK_CODE,joining,begin=join,end=join)
 checks=[]
 for _,h,data in records((base/'MATHCASE.BIN').read_bytes()):
  m.uc.mem_write(m.elf.symbols['m0_interp_header'],struct.pack('<16I',*h))
  m.uc.mem_write(m.elf.symbols['m0_interp_payload'],data)
  assert m.call('m0_interp_load',0,width=32)[0]&0xffffffff==1
  expected=list(struct.unpack_from('<'+'I'*h[3],data,len(data)-h[3]*4))
  for v,name in enumerate(meta['variants']):
   if h[4]!=128 and v:continue
   for cores in (1,2):
    before=(mailbox['submits'],mailbox['joins'])
    assert m.call('m0_interp_probe',v,cores,width=32)[0]&0xffffffff==1,(h[0],name,cores)
    result=struct.unpack('<30I',m.uc.mem_read(m.elf.symbols['m0_interp_result'],120))
    assert result[:2]==(1,1)and list(result[2:2+h[3]])==expected,(h[0],name,cores,result)
    assert not mailbox['pending']and io.state==original_state
    assert (mailbox['submits'],mailbox['joins'])==tuple(x+int(cores==2)for x in before)
    checks.append(dict(id=h[0],variant=name,cores=cores,bit_exact=True,SIO_state_restored=True))
  mailbox['refuse']=True;before=mailbox['joins']
  assert not(m.call('m0_interp_probe',0,2,width=32)[0]&0xffffffff)
  assert not mailbox['pending']and mailbox['joins']==before and io.state==original_state
  mailbox['refuse']=False
  corrupt=bytearray(data);corrupt[0]^=1;m.uc.mem_write(m.elf.symbols['m0_interp_payload'],bytes(corrupt))
  assert not(m.call('m0_interp_load',0,width=32)[0]&0xffffffff)
 # Check the ordinary timed flow, excluding standalone numerical probes.
 commands=json.loads((base/'app/compile_commands.json').read_text())
 tool=Path(commands[0]['arguments'][0]).with_name('arm-none-eabi-objdump');app.path=elf
 instructions,walk=cfg(app,tool);flow,_=symbol(app,'mk61_app_flow_step')
 names={address&~1:name for name,address in app.symbols.items()if app.sizes.get(name,0)}
 todo=[flow];visited=set();targets=set()
 while todo:
  name=todo.pop()
  if name in visited:continue
  visited.add(name)
  for _,target in walk(name)[1]:
   targets.add(target)
   if target in names and not names[target].startswith('m0_interp_'):todo.append(names[target])
 submit_name,submit_address=symbol(app,'6submitEPv');join_name,join_address=symbol(app,'4joinEv')
 assert submit_address in targets and join_address in targets,'Timed two-core dispatch removed'
 _,stage=symbol(app,'5stageEj');seen,calls=walk(flow);markers=set()
 for address,target in calls:
  if target!=stage:continue
  for previous in range(address-2,max(address-12,0),-2):
   item=instructions.get(previous)
   if item and item[0]=='movs':
    import re
    match=re.fullmatch(r'r0, #(\d+)(?:\s.*)?',item[1])
    if match:markers.add(int(match[1]));break
 assert {1,2,3,6,7}<=markers,markers
 assert SP-m.stack_lowest<1024,SP-m.stack_lowest
 return dict(status='ARM_ROM_SIO_MATRIX_PASS',physical_io=False,physical_timing=False,
    cases=len(meta['cases']),checks=len(checks),details=checks,
    separate_per_core_interpolator_state=True,programmable_SIO_state_preserved=True,
    actual_resident_hybrid_reference=True,worker_refusal_does_not_join=True,
    malformed_crc_rejected=True,timed_two_core_CFG_preserved=True,reachable_markers=sorted(markers),
    maximum_numerical_probe_stack_bytes=SP-m.stack_lowest,
    scheduling_model='real ARM callbacks executed inline; two private SIO register banks; no concurrency timing simulated',
    app_sha256=digest(base/'app/INTERP.APP'),resident_elf_sha256=meta['resident_elf_sha256'])

if __name__=='__main__':
 p=argparse.ArgumentParser();p.add_argument('--elf',type=Path);p.add_argument('--package-dir',type=Path);p.add_argument('--output',type=Path,required=True);a=p.parse_args()
 if not a.elf and not a.package_dir:p.error('--elf or --package-dir required')
 result=matrix_tests(a.package_dir.resolve())if a.package_dir else dot_tests(a.elf)
 a.output.write_text(json.dumps(result,indent=2)+'\n');print(json.dumps({k:v for k,v in result.items()if k!='details'},indent=2))

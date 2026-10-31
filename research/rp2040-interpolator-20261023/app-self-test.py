#!/usr/bin/env python3
"""Test the APP's real source with small loops and synthetic timer/storage.

The shipping APP ELF kernels are separately tested by verify.py. This reduced
fixture tests protocol, state restoration, ABBA checksums and fail-closed paths.
"""
import argparse
import hashlib
import json
from pathlib import Path
import struct
import subprocess
import sys
HERE=Path(__file__).resolve().parent
ROOT=HERE.parents[1]
sys.path[:0]=[str(HERE),str(ROOT/'tools'),str(ROOT/'tests')]
from build_picocalc import compiler_bin
from verify import InterpMachine
from native_eabi_m0_arm_self_test import SP
from m0_math_compare_app_self_test import SHIM
from decode import decode,VARIANTS
from unicorn import UC_HOOK_CODE,UC_HOOK_MEM_READ
from unicorn.arm_const import UC_ARM_REG_R0,UC_ARM_REG_R1,UC_ARM_REG_R2,UC_ARM_REG_R3,UC_ARM_REG_SP,UC_ARM_REG_LR,UC_ARM_REG_PC

def main():
 p=argparse.ArgumentParser(description=__doc__);p.add_argument('--output',type=Path,required=True)
 p.add_argument('--variant',choices=VARIANTS,default='all');a=p.parse_args()
 out=a.output.resolve();out.mkdir(parents=True,exist_ok=True);tc=compiler_bin(None)
 shim=out/'api.c';shim.write_text(SHIM)
 flags=['-mcpu=cortex-m0plus','-mthumb','-mfloat-abi=soft','-Os','-fno-builtin','-ffunction-sections','-fdata-sections',
   '-DINTERP_SAMPLES=4','-DINTERP_ROUNDS=2','-DINTERP_VARIANT='+str(list(VARIANTS).index(a.variant)),
   '-I'+str(HERE),'-I'+str(ROOT/'sdk/portable/include'),'-I'+str(ROOT/'code')]
 objects=[]
 for source in [HERE/'benchmark.c',HERE/'kernels.cpp',HERE/'divide.S',HERE/'root_seed.S',ROOT/'sdk/portable/memory.c',shim]:
  obj=out/(source.name+'.o');objects.append(obj)
  cpp=source.suffix=='.cpp'
  subprocess.run([str(tc/('arm-none-eabi-g++' if cpp else 'arm-none-eabi-gcc')),*flags,
   *(['-std=c++17','-fno-exceptions','-fno-rtti'] if cpp else []),'-c',str(source),'-o',str(obj)],check=True)
 elf=out/'fixture.elf'
 subprocess.run([str(tc/'arm-none-eabi-gcc'),*flags,'-nostdlib','-Wl,-Ttext=0x20000000','-Wl,-Tdata=0x20010000',
  '-Wl,-e,main',*[str(x) for x in objects],'-lgcc','-o',str(elf)],check=True)
 class AppMachine(InterpMachine):
  def __init__(self):
   super().__init__(elf);self.instruction_budget=100000000;self.stack_bytes=32768
  def write(self,uc,access,address,size,value,user):
   if any(s[2]&1 and s[3]<=address and address+size<=s[3]+s[5] for s in self.elf.sections):return
   super().write(uc,access,address,size,value,user)
 def execute(case):
  m=AppMachine();uc=m.uc
  for base in (0x40054000,0x40008000,0x40028000):uc.mem_map(base,4096)
  # Independent nonzero states, with valid writable control fields.
  initial=[]
  for b in range(2):
   values=[0x12345678+b,0x89ABCDEF-b,123,456,789,15<<10,31<<10]
   for off,val in zip((0,4,8,12,16,44,48),values):uc.mem_write(0xD0000080+64*b+off,struct.pack('<I',val))
   initial.extend(values)
  uc.mem_write(0xD0000078,struct.pack('<I',3 if case=='busy_divider' else 1))
  uc.mem_write(0xD0000000,struct.pack('<I',1 if case=='wrong_core' else 0))
  clock_values=(1,256,2,0x80000001,0,125,(6<<16)|(2<<12))
  for addr,v in zip((0x4000803C,0x40008040,0x40008044,0x40028000,0x40028004,0x40028008,0x4002800C),clock_values):uc.mem_write(addr,struct.pack('<I',v))
  operations=struct.unpack('<4I',uc.mem_read(m.elf.symbols['operations'],16))
  file_object=bytes(uc.mem_read(m.elf.symbols['file_object'],m.elf.sizes['file_object']))
  writes=[];service_calls=0;timer_reads=0
  def timer(uc,access,address,size,value,user):
   nonlocal timer_reads
   timer_reads+=1;uc.mem_write(address,struct.pack('<I',timer_reads*100))
  uc.hook_add(UC_HOOK_MEM_READ,timer,begin=0x40054028,end=0x4005402B)
  def callback(uc,address,size,user):
   nonlocal service_calls
   r=[uc.reg_read(x) for x in (UC_ARM_REG_R0,UC_ARM_REG_R1,UC_ARM_REG_R2,UC_ARM_REG_R3)];value=0
   if address==0x080E0020:value=m.elf.symbols['services']
   elif address==0x080E0050:service_calls+=1
   elif address==0x080E0010:
    if r[0]==operations[0]:value=operations[3]
    else:
     pointer=struct.unpack('<I',uc.mem_read(uc.reg_read(UC_ARM_REG_SP),4))[0]
     if r[0]==operations[1]:uc.mem_write(pointer,file_object)
     elif r[0]==operations[2]:
      name,data,n,unused=struct.unpack('<4I',uc.mem_read(pointer,16));assert bytes(uc.mem_read(name,7))==b'RESULT\0'
      writes.append(bytes(uc.mem_read(data,n)));value=1
     else:raise AssertionError(r)
   else:raise AssertionError(hex(address))
   uc.reg_write(UC_ARM_REG_R0,value);uc.reg_write(UC_ARM_REG_PC,uc.reg_read(UC_ARM_REG_LR))
  for addr in (0x080E0010,0x080E0020,0x080E0050):
   uc.mem_write(addr,b'\x70\x47');uc.hook_add(UC_HOOK_CODE,callback,begin=addr,end=addr)
  if case=='bad_result':
   def corrupt(uc,access,address,size,value,user):
    v=struct.unpack('<I',uc.mem_read(address,4))[0];uc.mem_write(address,struct.pack('<I',v^0x100000))
   uc.hook_add(UC_HOOK_MEM_READ,corrupt,begin=0xD00000A0,end=0xD00000AB)
   uc.hook_add(UC_HOOK_MEM_READ,corrupt,begin=0xD00000E0,end=0xD00000EB)
  status=m.call('main',0)[0]&0xFFFFFFFF
  final=[]
  for b in range(2):
   for off in (0,4,8,12,16,44,48):final.append(struct.unpack('<I',uc.mem_read(0xD0000080+b*64+off,4))[0])
  assert final==initial,(case,'state not restored')
  if case=='normal':
   assert status==0 and len(writes)==1
   report=decode(writes[0],physical=False,expected_rounds=2,expected_samples=4,variant=a.variant)
   assert report['rows']==6*VARIANTS[a.variant][1]
   assert all(all(v==100 for rr in row['raw_us'] for v in rr) for row in report['results'])
   (out/'synthetic-result.bin').write_bytes(writes[0])
   # Admission must reject a damaged payload, drifting checksum and clock.
   rejected=0
   for offset in (32,56,144,256+32,256+48+24*2):
    bad=bytearray(writes[0]);bad[offset]^=128
    try:decode(bytes(bad),physical=False,expected_rounds=2,expected_samples=4,variant=a.variant)
    except AssertionError:rejected+=1
   assert rejected==5
   # V3 must not silently admit a result carrying the old checksum schema.
   old=(ROOT/'.build/rp2040-interpolator-20261023/packet-v2/protocol'/a.variant/'synthetic-result.bin').read_bytes()
   try:decode(old,physical=False,expected_rounds=2,expected_samples=4,variant=a.variant)
   except AssertionError:rejected+=1
   assert rejected==6
   assert all(not any('net' in key for key in rr) for row in report['results'] for rr in row['rounds'])
   probe=[]
   for flip in (0,1,0x80000000):
    expected=0
    for i in range(4096):
     j=i&31;lo=(j*0x1234567+0x7654321)&0xFFFFFFFF;hi=(j*2654435761)&0xFFFFFFFF
     if j==7:lo^=flip
     expected=((expected^lo)*16777619)&0xFFFFFFFF;expected^=expected>>16
     expected=((expected^hi)*16777619)&0xFFFFFFFF;expected^=expected>>16
     expected=(expected+i)&0xFFFFFFFF
    got=m.call('checksum_probe',flip)[0]
    assert got==expected,(flip,got,expected)
    probe.append(got)
   assert probe[0]!=probe[1] and probe[0]!=probe[2],('periodic checksum erased result changes',probe)
  elif case in ('wrong_core','busy_divider'):
   assert status!=0 and not writes and not timer_reads
  else:
   assert status!=0 and len(writes)==1 and struct.unpack_from('<I',writes[0],28)[0]>0
   try:decode(writes[0],physical=False,expected_rounds=2,expected_samples=4,variant=a.variant)
   except AssertionError:pass
   else:raise AssertionError('Admitted a corrupted hardware result')
  return dict(case=case,status=status,peripheral_state_restored=True,output_files=len(writes),timer_reads=timer_reads,service_calls=service_calls,
   stack_bytes_observed=SP-m.stack_lowest)
 cases=[]
 for name in ('normal','wrong_core','busy_divider','bad_result'):
  cases.append(execute(name));print('PASS',name,flush=True)
 report=dict(status='PASS',variant=a.variant,hardware_verified=False,physical_timing=False,cases=cases,
  decoder_negative_cases=6,
  checksum_regression_scope='4096 steps, repeated position7, low-word bits0 and31; exhaustive64bit-by32position coverage is in separate checksum report',
  fixture_elf_sha256=hashlib.sha256(elf.read_bytes()).hexdigest(),benchmark_sha256=hashlib.sha256((HERE/'benchmark.c').read_bytes()).hexdigest(),
  scope='Same benchmark source compiled with 4 samples and 2 rounds. Numerical ARM kernels execute; timer/storage callbacks and SIO are modelled. Exact shipping APP kernels qualified separately.')
 (out/'report.json').write_text(json.dumps(report,indent=2)+'\n');print(json.dumps(report,indent=2))
if __name__=='__main__':main()

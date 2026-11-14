#!/usr/bin/env python3
"""Byte-exact ARM packer regression and instruction counts; no hardware timing."""
from pathlib import Path
import argparse,hashlib,json,struct
from host_nrz4 import NrzMachine
from host_test import ELF,BASE,STACK,STOP,pack,words,pattern,Uc
from unicorn import UC_ARCH_ARM,UC_MODE_MCLASS,UC_MODE_THUMB,UC_HOOK_CODE,UC_HOOK_MEM_WRITE
from unicorn.arm_const import *

CAPACITY=241
INPUT=0x20006000;OUTPUT=0x20007000;SENTINEL=0x6d6d6d6d
def reference(data):
 symbols=[]
 for at in range(0,len(data),4):
  symbols.append(0)
  for byte in data[at:at+4]:symbols.extend((byte>>4,byte&15))
  symbols.append(15)
 symbols.append(15)
 result=[SENTINEL]*(2*CAPACITY)
 for i,v in enumerate(symbols):
  b=((v&1)<<9)|((v&2)<<7);c=((v&4)<<9)|((v&8)<<7)
  result[i]=b|((~b&0x300)<<16);result[CAPACITY+i]=c|((~c&0xc00)<<16)
 return struct.pack('<482I',*result)

class Packer:
 def __init__(self,kit):
  package=(kit/'module.s3m').read_bytes();header=words(package[:64]);image=bytearray(package[64:64+header[4]])
  for at in words(package[64+header[4]:]):
   struct.pack_into('<I',image,at,struct.unpack_from('<I',image,at)[0]+BASE-0x20000000)
  self.u=Uc(UC_ARCH_ARM,UC_MODE_MCLASS|UC_MODE_THUMB);self.u.mem_map(0x20000000,65536)
  self.u.mem_write(BASE,bytes(image));elf=ELF(kit/'module.elf')
  self.entry=elf.symbols['fl_nrz_pack']['value']+BASE-0x20000000
  self.u.hook_add(UC_HOOK_MEM_WRITE,self.write)
 def write(self,u,access,at,size,value,user):
  assert OUTPUT<=at and at+size<=OUTPUT+2*CAPACITY*4 or STACK-512<=at and at+size<=STACK,(hex(at),size)
 def run(self,data):
  self.u.mem_write(INPUT,data);self.u.mem_write(OUTPUT-4,pack(SENTINEL)*(2*CAPACITY+2))
  for reg,value in zip((UC_ARM_REG_R0,UC_ARM_REG_R1,UC_ARM_REG_R2),(INPUT,len(data),OUTPUT)):self.u.reg_write(reg,value)
  saved=list(range(UC_ARM_REG_R4,UC_ARM_REG_R11+1))
  for reg in saved:self.u.reg_write(reg,0x71300000+reg)
  self.u.reg_write(UC_ARM_REG_SP,STACK);self.u.reg_write(UC_ARM_REG_LR,STOP|1);self.u.reg_write(UC_ARM_REG_XPSR,0x1000000)
  self.u.emu_start(self.entry|1,STOP,count=100000)
  assert self.u.reg_read(UC_ARM_REG_PC)==STOP and self.u.reg_read(UC_ARM_REG_SP)==STACK
  assert all(self.u.reg_read(reg)==0x71300000+reg for reg in saved)
  assert self.u.mem_read(OUTPUT-4,4)==pack(SENTINEL)and self.u.mem_read(OUTPUT+2*CAPACITY*4,4)==pack(SENTINEL)
  assert bytes(self.u.mem_read(OUTPUT,2*CAPACITY*4))==reference(data)

def main():
 ap=argparse.ArgumentParser(description=__doc__);ap.add_argument('--kit',required=True,type=Path)
 ap.add_argument('--reference-kit',required=True,type=Path);a=ap.parse_args()
 optimized=json.loads((a.kit/'manifest.json').read_text());baseline=json.loads((a.reference_kit/'manifest.json').read_text())
 assert optimized['nrz4_packer']=='frames'and baseline['nrz4_packer']=='reference'
 encoder=Packer(a.kit);cases=0
 for n in range(4,97,4):
  for kind in range(7):
   for seed in(0,1,0x9e3779b9):encoder.run(pattern(n,kind,seed));cases+=1
 # Every possible byte, including high/low nibble asymmetry, across frames.
 for v in range(256):encoder.run(bytes((v+i*17)&255 for i in range(96)));cases+=1
 instructions=[];module_wave_cases=0
 for n in(24,48,72,96):
  row={'bytes':n}
  for kit,label in((a.reference_kit,'reference'),(a.kit,'frames')):
   elf=ELF(kit/'module.elf');wave=elf.symbols['wave']['value']+BASE-0x20000000
   machine=NrzMachine((kit/'module.s3m').read_bytes());machine.u.mem_write(wave,pack(SENTINEL)*(2*CAPACITY))
   assert machine.start(5,n,36,6)==0
   assert bytes(machine.u.mem_read(wave,2*CAPACITY*4))==reference(pattern(n,6,0x9e3779b9))
   row[label+'_init_instructions']=machine.instructions;module_wave_cases+=1
  row['instruction_reduction']=1-row['frames_init_instructions']/row['reference_init_instructions'];instructions.append(row)
 result=dict(status='PASS',physical_io=False,hardware_timing_measured=False,actual_ARM_packer_cases=cases,
  actual_ARM_INIT_wave_comparisons=module_wave_cases,guard_words_and_unused_wave_preserved=True,callee_saved_registers_preserved=True,
  module_sha256=hashlib.sha256((a.kit/'module.s3m').read_bytes()).hexdigest(),
  reference_module_sha256=hashlib.sha256((a.reference_kit/'module.s3m').read_bytes()).hexdigest(),
  init_instruction_counts=instructions,limits='Instruction counts are not Cortex-M3 cycles or physical timing. INIT includes fixture pattern generation.')
 (a.kit/'host-pack-test.json').write_text(json.dumps(result,indent=2)+'\n');print(json.dumps(result,indent=2))
if __name__=='__main__':main()

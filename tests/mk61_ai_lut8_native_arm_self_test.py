#!/usr/bin/env python3
"""Execute the integrated LUT8/direct kernels from the final firmware ELF."""
import argparse
import hashlib
import json
from pathlib import Path
import struct
import sys
ROOT=Path(__file__).resolve().parents[1]
sys.path[:0]=[str(ROOT),str(ROOT/'tests')]
from prepare_mk61_ai_math_candidates import records

def main():
 p=argparse.ArgumentParser(description=__doc__)
 p.add_argument('--firmware',type=Path,required=True);p.add_argument('--fixtures',type=Path,required=True)
 p.add_argument('--output',type=Path,required=True)
 p.add_argument('--rom',type=Path,default=ROOT/'research/rp2040-memset-2026-10-21/capture/bootrom.bin');a=p.parse_args()
 from native_eabi_m0_arm_self_test import Machine,SP
 class Probe(Machine):
  def __init__(self):
   self.allowed=[];super().__init__(a.firmware,True,stack_bytes=2048,instruction_budget=1000000,bootrom=a.rom)
  def write(self,uc,access,address,size,value,user):
   if any(lo<=address and address+size<=hi for lo,hi in self.allowed):return
   return super().write(uc,access,address,size,value,user)
 m=Probe();source,tables,out,batch=0x20020000,0x20026000,0x2002a000,0x2002b000
 m.allowed.extend([(source,source+13000),(tables,tables+8200),(out,out+112),(batch,batch+60)])
 pointer=next(v for n,v in m.elf.symbols.items() if '6mk61ai4math' in n and n.endswith('5tableE'))
 m.allowed.append((pointer,pointer+4));m.call('_ZN6mk61ai4math10initializeEv',0,width=32)
 lut=next(n for n in m.elf.symbols if n.startswith('_ZN6mk61ai22linear_batch_lut8_sram'))
 direct=next(n for n in m.elf.symbols if n.startswith('_ZN6mk61ai17linear_batch_sram'))
 cases=[]
 for _,h,data in records(a.fixtures.read_bytes()):
  m.uc.mem_write(source,data);rows,cols,groups=h[3:6];w=h[11]
  weights=source+cols+groups*8;scales=weights+2*w
  expected=list(struct.unpack_from('<'+'I'*rows,data,len(data)-rows*4))
  use_lut=cols==128
  if use_lut:
   for g in range(4):m.call('mk61ai_prepare_lut8x32',source+32*g,tables+2050*g,width=32)
  kernel=lut if use_lut else direct
  for halves in (False,True):
   sizes=(rows//2,rows-rows//2) if halves else (rows,)
   start=0
   for n in sizes:
    values=[cols,4,256 if use_lut else 0,n,0,source+cols,0,tables,
            source+cols+groups*4,source,weights+(w if use_lut else 0)+start*cols//2,
            scales+start*cols//16,out+start*4]
    raw=struct.pack('<B3x13IB3x',1,*values,0);assert len(raw)==60
    m.uc.mem_write(batch,raw);m.call(kernel,batch,width=32)
    assert m.uc.mem_read(batch+56,1)==b'\0',(h[0],halves,'status')
    start+=n
   assert list(struct.unpack('<'+'I'*rows,m.uc.mem_read(out,rows*4)))==expected,(h[0],halves)
  if not use_lut:
   m.uc.mem_write(batch,struct.pack('<B3x13IB3x',1,*values,0));m.call(lut,batch,width=32)
   assert m.uc.mem_read(batch+56,1)==b'\2','LUT8 accepted unsupported width/grid'
  cases.append(dict(id=h[0],columns=cols,rows=rows,kernel='LUT8' if use_lut else 'direct',whole_and_split_bit_exact=True))
 result=dict(status='NATIVE_ARM_ROM_PASS',physical_io=False,cases=cases,whole_and_split_checks=2*len(cases),
             maximum_kernel_stack_bytes=SP-m.stack_lowest,
             firmware_sha256=hashlib.sha256(a.firmware.read_bytes()).hexdigest(),
             fixtures_sha256=hashlib.sha256(a.fixtures.read_bytes()).hexdigest(),
             new_kernel_and_prepare_in_SRAM=True)
 assert all(0x20000000<=m.elf.symbols[n]<0x20042000 for n in (lut,'mk61ai_prepare_lut8x32','mk61ai_dot_lut8_q4_a8_32'))
 a.output.write_text(json.dumps(result,indent=2)+'\n')
 print('Integrated ARM/ROM PASS:',len(cases),'real tiles, whole/split outputs bit-exact, unsupported width rejected; stack',result['maximum_kernel_stack_bytes'])
if __name__=='__main__':main()

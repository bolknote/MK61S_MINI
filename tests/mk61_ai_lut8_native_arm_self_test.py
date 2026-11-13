#!/usr/bin/env python3
"""Execute the integrated LUT8/direct kernels from the final firmware ELF."""
import argparse
import hashlib
import json
import random
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
 from unicorn import UC_HOOK_CODE,UC_HOOK_MEM_READ
 fallback=m.elf.symbols['mk61ai_dot_lut8_q4_a8_32_unaligned']&~1
 assert 0x10000000<=fallback<0x10200000,'Rare fallback consumes SRAM'
 fallback_entries=[0]
 def fallback_entry(uc,address,size,user):fallback_entries[0]+=1
 def aligned_word(uc,access,address,size,value,user):
  if size==4:assert address%4==0,('unaligned weight word',hex(address))
 m.uc.hook_add(UC_HOOK_CODE,fallback_entry,begin=fallback,end=fallback)
 m.uc.hook_add(UC_HOOK_MEM_READ,aligned_word,begin=source,end=source+20)
 # Execute the production ASM on every index byte, signed INT8 extremes,
 # both table alignments and every weight alignment (scalar fallback).
 rng=random.Random(0x1a8);dot_cases=[]
 for x in ([-128]*32,[127]*32,[0]*32,[-128,127]*16,list(range(-16,16))):
  for mask in (0,1,127,128,129,254,255):dot_cases.append((x,bytes([mask]*16)))
 for mask in range(256):
  dot_cases.append(([rng.randrange(-128,128)for _ in range(32)],bytes((mask+17*i)&255 for i in range(16))))
 for _ in range(512):dot_cases.append(([rng.randrange(-128,128)for _ in range(32)],rng.randbytes(16)))
 dot_checks=0
 for x,w in dot_cases:
  m.uc.mem_write(source+128,bytes(v&255 for v in x));expected=0
  for j in range(32):
   code=sum(((w[plane*4+j//8]>>(j%8))&1)<<plane for plane in range(4))
   expected+=(code-8)*x[j]
  for table_offset in (0,2):
   m.call('mk61ai_prepare_lut8x32',source+128,tables+table_offset,width=32)
   for weight_offset in range(4):
    m.uc.mem_write(source+weight_offset,w)
    before_fallback=fallback_entries[0]
    actual=m.call('mk61ai_dot_lut8_q4_a8_32',source+weight_offset,tables+table_offset,width=32)[0]&0xffffffff
    assert actual==expected&0xffffffff,(dot_checks,weight_offset,table_offset,actual,expected)
    assert fallback_entries[0]-before_fallback==int(weight_offset!=0)
    dot_checks+=1
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
 # All three validation classes remain: invalid shape/format, missing
 # buffers and nonfinite arithmetic. A failed first row must not be stored.
 assert cols==128
 probe_values=values.copy();probe_values[3]=1;probe_values[-1]=out
 original_scale=bytes(m.uc.mem_read(source+cols,4));numeric_checks=0
 for scale in (0x7f800000,0xff800000,0x7fc00001,0xffc00001):
  m.uc.mem_write(source+cols,struct.pack('<I',scale))
  for kernel in (lut,direct):
   m.uc.mem_write(out,b'\x61\xa1\xba\xad')
   m.uc.mem_write(batch,struct.pack('<B3x13IB3x',1,*probe_values,0));m.call(kernel,batch,width=32)
   assert m.uc.mem_read(batch+56,1)==b'\7',(kernel,'nonfinite accepted')
   assert m.uc.mem_read(out,4)==b'\x61\xa1\xba\xad','Failed row was stored'
   numeric_checks+=1
 m.uc.mem_write(source+cols,original_scale)
 invalid=[(0,384),(1,2),(2,0)]+[(i,0)for i in (5,7,10,11,12)]
 for i,value in invalid:
  bad=probe_values.copy();bad[i]=value
  m.uc.mem_write(batch,struct.pack('<B3x13IB3x',1,*bad,0));m.call(lut,batch,width=32)
  assert m.uc.mem_read(batch+56,1)==b'\2',('Invalid LUT8 field accepted',i)
 result=dict(status='NATIVE_ARM_ROM_PASS',physical_io=False,cases=cases,whole_and_split_checks=2*len(cases),
             integer_dot_cases=len(dot_cases),integer_dot_checks=dot_checks,
             all_weight_byte_alignments=True,both_table_halfword_alignments=True,
             unaligned_fallback_entries=fallback_entries[0],no_unaligned_weight_word_reads=True,
             numeric_error_checks=numeric_checks,format_error_checks=len(invalid),failed_row_not_stored=True,
             maximum_kernel_stack_bytes=SP-m.stack_lowest,
             firmware_sha256=hashlib.sha256(a.firmware.read_bytes()).hexdigest(),
             fixtures_sha256=hashlib.sha256(a.fixtures.read_bytes()).hexdigest(),
             new_kernel_and_prepare_in_SRAM=True)
 assert all(0x20000000<=m.elf.symbols[n]<0x20042000 for n in (lut,'mk61ai_prepare_lut8x32','mk61ai_dot_lut8_q4_a8_32'))
 a.output.write_text(json.dumps(result,indent=2)+'\n')
 print('Integrated ARM/ROM PASS:',len(cases),'real tiles, whole/split outputs bit-exact, unsupported width rejected; stack',result['maximum_kernel_stack_bytes'])
if __name__=='__main__':main()

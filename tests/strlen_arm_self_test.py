#!/usr/bin/env python3
"""Production strlen: independent byte lengths, unmapped edges and AAPCS.

Its documented maximum read is the aligned eight-byte group containing NUL.
No byte before the supplied pointer or after that group may be read, even if
mapped. Input writes are forbidden and stack accesses stay in the exact frame.
"""
import argparse
import hashlib
import json
from pathlib import Path
import random
import sys
from unicorn import Uc,UC_ARCH_ARM,UC_MODE_MCLASS,UC_MODE_THUMB,UC_HOOK_MEM_READ,UC_HOOK_MEM_WRITE
from unicorn.arm_const import (UC_ARM_REG_R0,UC_ARM_REG_R1,UC_ARM_REG_R2,UC_ARM_REG_R3,
    UC_ARM_REG_R4,UC_ARM_REG_R5,UC_ARM_REG_R6,UC_ARM_REG_R7,UC_ARM_REG_R8,
    UC_ARM_REG_R9,UC_ARM_REG_R10,UC_ARM_REG_R11,UC_ARM_REG_SP,UC_ARM_REG_LR,
    UC_ARM_REG_PC,UC_ARM_REG_XPSR)
sys.path.insert(0,str(Path(__file__).resolve().parents[1]/'tools'))
from check_stm32_vectors import ElfImage

SAVED=(UC_ARM_REG_R4,UC_ARM_REG_R5,UC_ARM_REG_R6,UC_ARM_REG_R7,
       UC_ARM_REG_R8,UC_ARM_REG_R9,UC_ARM_REG_R10,UC_ARM_REG_R11)
PAGE=4096;STACK=0x2001e000;SP=STACK+PAGE-8

def run(path):
    elf=ElfImage(path);entry=elf.symbols['strlen']&~1;size=elf.sizes['strlen']
    u=Uc(UC_ARCH_ARM,UC_MODE_MCLASS|UC_MODE_THUMB)
    code_page=entry&~(PAGE-1);u.mem_map(code_page,PAGE)
    for kind,offset,vaddr,paddr,n,mem,flags,alignment in elf.segments:
        if kind==1 and n:
            assert code_page<=vaddr and vaddr+n<=code_page+PAGE
            u.mem_write(vaddr,elf.data[offset:offset+n])
    u.mem_map(STACK,PAGE);stop=code_page+PAGE-2
    for address in [0x20008000,0x08060000]:u.mem_map(address,PAGE)
    active={};calls=0;greatest_extra=0;patterns=3
    def read(uc,access,address,n,value,user):
        del uc,access,value,user
        if entry<=address and address+n<=entry+size:return
        if SP-8<=address and address+n<=SP:return
        assert active['pointer']<=address and address+n<=active['group_end'],('read outside NUL group',hex(address),n,active)
        if n==8:assert address%8==0,('unaligned paired load',hex(address))
    def write(uc,access,address,n,value,user):
        del uc,access,value,user
        assert SP-8<=address and address+n<=SP,('input/non-frame write',hex(address),n)
    u.hook_add(UC_HOOK_MEM_READ,read);u.hook_add(UC_HOOK_MEM_WRITE,write)
    rng=random.Random(0x5354524c)
    lengths=[*range(0,17),31,32,33,63,64,65,127,128,129,255,256,257,511,512,1023,1024,2047,2048]
    for data in [0x20008000,0x08060000]:
      for length in lengths:
       for alignment in range(8):
        for edge in ['start','end']:
         pointer=(data+alignment if edge=='start' else data+PAGE-1-((-(length+alignment+1))&7)-length)
         assert pointer%8==alignment
         nul=pointer+length;group_end=(nul+8)&~7
         assert data<=pointer<=nul<data+PAGE and group_end<=data+PAGE
         for pattern in range(patterns):
          nonzero=(bytes([1])*length if pattern==0 else bytes([255])*length if pattern==1 else
                   bytes(rng.randrange(1,256) for _ in range(length)))
          page=bytearray(b'\xa5'*PAGE);at=pointer-data;page[at:at+length]=nonzero;page[at+length]=0
          u.mem_write(data,bytes(page));active.update(pointer=pointer,group_end=group_end)
          saved={r:(0xa17e0000+i*0x1023) for i,r in enumerate(SAVED)}
          for r,v in saved.items():u.reg_write(r,v)
          for r,v in [(UC_ARM_REG_R0,pointer),(UC_ARM_REG_R1,0x61616161),(UC_ARM_REG_R2,0x72727272),(UC_ARM_REG_R3,0x83838383),
                      (UC_ARM_REG_SP,SP),(UC_ARM_REG_LR,stop|1),(UC_ARM_REG_XPSR,0x01000000)]:u.reg_write(r,v)
          u.emu_start(entry|1,stop,count=100000)
          assert u.reg_read(UC_ARM_REG_PC)==stop and u.reg_read(UC_ARM_REG_R0)==length,(path.name,length,alignment,edge)
          assert u.reg_read(UC_ARM_REG_SP)==SP
          assert all(u.reg_read(r)==v for r,v in saved.items()),('callee saved',path.name)
          assert bytes(u.mem_read(data,PAGE))==bytes(page),'Input changed'
          calls+=1;greatest_extra=max(greatest_extra,group_end-(nul+1))
    return dict(ELF=str(path.resolve()),ELF_sha256=hashlib.sha256(path.read_bytes()).hexdigest(),entry=entry,
                symbol_bytes=size,alignment=entry%16,calls=calls,data_banks=['SRAM','Flash'],
                pointer_alignments=8,guard_edges=['leading guard page and exact-pointer read hook','trailing guard page immediately after final NUL group'],
                maximum_extra_bytes=greatest_extra,input_unchanged=True,callee_saved_and_SP=True)

def main():
    p=argparse.ArgumentParser(description=__doc__);p.add_argument('--elf',type=Path,action='append',required=True)
    p.add_argument('--output',type=Path,required=True);a=p.parse_args()
    result=dict(status='PASS_ACTUAL_PRODUCTION_STRLEN_GUARDS_AAPCS_HOST_ARM',results=[run(x) for x in a.elf],
                physical_IO=0,hardware_timing_claim=False,unchanged_full_candidate_corpus_replayed=False)
    with a.output.open('x') as stream:stream.write(json.dumps(result,indent=2)+'\n')
    print(json.dumps(result))
if __name__=='__main__':main()

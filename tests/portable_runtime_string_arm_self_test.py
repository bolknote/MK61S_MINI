#!/usr/bin/env python3
"""Run the actual standalone strcmp with ABI and read-bound checks."""
import argparse
from pathlib import Path
from unicorn import Uc, UC_ARCH_ARM, UC_MODE_MCLASS, UC_MODE_THUMB, UC_HOOK_MEM_READ
from unicorn.arm_const import UC_ARM_REG_R0, UC_ARM_REG_R1, UC_ARM_REG_R2, UC_ARM_REG_R4, UC_ARM_REG_R5, UC_ARM_REG_R6, UC_ARM_REG_R7, UC_ARM_REG_R8, UC_ARM_REG_R9, UC_ARM_REG_R10, UC_ARM_REG_R11, UC_ARM_REG_SP, UC_ARM_REG_LR
from run_portable_system_arm_tests import Elf

def main():
    parser=argparse.ArgumentParser(description=__doc__)
    parser.add_argument("elf",type=Path)
    args=parser.parse_args()
    elf=Elf(args.elf);uc=Uc(UC_ARCH_ARM,UC_MODE_MCLASS|UC_MODE_THUMB)
    uc.mem_map(0x20000000,65536);elf.load(uc)
    first,second,stop=0x20008000,0x20009000,0x2000FFFE
    bounds=[]
    def reads(machine,access,address,size,value,context):
        del machine,access,value,context
        assert any(begin<=address and address+size<=end for begin,end in bounds),(hex(address),size,bounds)
    uc.hook_add(UC_HOOK_MEM_READ,reads)
    registers=[UC_ARM_REG_R4,UC_ARM_REG_R5,UC_ARM_REG_R6,UC_ARM_REG_R7,UC_ARM_REG_R8,UC_ARM_REG_R9,UC_ARM_REG_R10,UC_ARM_REG_R11]
    cases=[(b"",b""),(b"A",b""),(b"",b"A"),(b"A",b"AB"),(b"AB",b"A"),(b"\x80",b"\x7f"),(b"\xff",b"\x80")]
    for length in [1,2,3,4,7,15,31,63,127,255]:
        value=bytes(1+index%255 for index in range(length))
        cases.append((value,value))
        for at in [0,length//2,length-1]:
            changed=bytearray(value);changed[at]=255 if changed[at]!=255 else 254
            cases.extend([(value,bytes(changed)),(bytes(changed),value)])
    tested=0
    for a,b in cases:
        reference=next((x-y for x,y in zip(a+b"\0",b+b"\0") if x!=y),0)
        for left in range(4):
            for right in range(4):
                p,q=first+left,second+right
                uc.mem_write(p,a+b"\0");uc.mem_write(q,b+b"\0")
                bounds[:]=[(p,p+len(a)+1),(q,q+len(b)+1)]
                for index,register in enumerate(registers):uc.reg_write(register,0xBADC0000+index)
                uc.reg_write(UC_ARM_REG_SP,0x2000F000);uc.reg_write(UC_ARM_REG_LR,stop|1)
                uc.reg_write(UC_ARM_REG_R0,p);uc.reg_write(UC_ARM_REG_R1,q)
                uc.emu_start(elf.symbols["strcmp"]|1,stop,count=10000)
                result=uc.reg_read(UC_ARM_REG_R0);result=result-(1<<32) if result>>31 else result
                assert result==reference,(a,b,result,reference)
                assert uc.reg_read(UC_ARM_REG_SP)==0x2000F000
                for index,register in enumerate(registers):assert uc.reg_read(register)==0xBADC0000+index
                tested+=1
    print(f"Standalone ARM strcmp: {tested} alignment/unsigned/NUL/ABI cases PASS")
    searched=0
    for length in [0,1,2,3,4,7,31,255,256,257,1024]:
        value=bytes(index%256 for index in range(length))
        for alignment in range(4):
            pointer=first+alignment
            uc.mem_write(pointer,value or b"x")
            bounds[:]=[(pointer,pointer+length),(0x2000EFC0,0x2000F000)]
            for wanted in [-257,-1,0,1,42,255,256,511]:
                expected=value.find(bytes([wanted&255]))
                for index,register in enumerate(registers):uc.reg_write(register,0xBADC0000+index)
                uc.reg_write(UC_ARM_REG_SP,0x2000F000);uc.reg_write(UC_ARM_REG_LR,stop|1)
                uc.reg_write(UC_ARM_REG_R0,pointer);uc.reg_write(UC_ARM_REG_R1,wanted&0xFFFFFFFF);uc.reg_write(UC_ARM_REG_R2,length)
                uc.emu_start(elf.symbols["memchr"]|1,stop,count=20000)
                assert uc.reg_read(UC_ARM_REG_R0)==(0 if expected<0 else pointer+expected),(length,alignment,wanted)
                assert uc.reg_read(UC_ARM_REG_SP)==0x2000F000
                for index,register in enumerate(registers):assert uc.reg_read(register)==0xBADC0000+index
                searched+=1
    print(f"Standalone ARM memchr: {searched} bounds/unsigned/zero-length/ABI cases PASS")

if __name__=="__main__":main()

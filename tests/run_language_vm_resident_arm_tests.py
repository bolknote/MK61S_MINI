#!/usr/bin/env python3
"""Run bytecode in the actual resident Flash executor after poisoning APP RAM.

Uses the existing ARM peripheral fixture. Display/keyboard/background are
stubbed; bytecode decoding, control, tagged integers, double EABI and selected float math run
in real resident code. This does not flash a physical device.
"""
import argparse
import struct
import math
import tempfile
from pathlib import Path

from run_portable_system_arm_tests import Machine,Elf,ROOT,run
from unicorn.arm_const import (UC_ARM_REG_SP,UC_ARM_REG_LR,UC_ARM_REG_R0,UC_ARM_REG_PC)

INTEGER_TAG = 0x7FFC0001


def decode_values(payload):
    return tuple(struct.unpack("<i", cell[:4])[0]
                 if struct.unpack("<I", cell[4:])[0] == INTEGER_TAG
                 else struct.unpack("<d", cell)[0]
                 for cell in (payload[i:i + 8] for i in range(0, len(payload), 8)))


class ResidentMachine(Machine):
    def __init__(self,path):
        super().__init__(path,False)
        self.elf=Elf(path)
        self.skip={value&~1 for name,value in self.elf.symbols.items()
                   if ("idle_main_process" in name or "_ZN3kbd4scanEv" in name or
                       "take_immediate_press" in name or "last_keyEv" in name or
                       "endUiTextEv" in name or "MK61Display5clearEv" in name)}
        self.entry=self.elf.symbol("execute_resident")
        assert self.entry<0x20000000,"executor must live in Flash"
        self.kind="resident-vm"
    def hook(self,uc,address,size,context):
        if address in getattr(self,"skip",set()):
            uc.reg_write(UC_ARM_REG_R0,0)
            uc.reg_write(UC_ARM_REG_PC,uc.reg_read(UC_ARM_REG_LR))
            return
        super().hook(uc,address,size,context)
    def execute(self,image,variables=None):
        code=self.workspace+4096
        values=self.workspace
        array=self.workspace+512
        request=self.input+128
        self.uc.mem_write(code,image)
        if variables is None:self.uc.mem_write(values,bytes(26*8))
        else:self.uc.mem_write(values,struct.pack("<26d",*variables))
        self.uc.mem_write(array,bytes(385*8))
        self.uc.mem_write(request,bytes(48))
        self.put(request,48,6,code,len(image),values,array,385)
        self.uc.mem_write(request+28,b"\x01\0\0\0")
        # There is no native executor APP or retained compiler code anywhere
        # in the complete dynamic APP/heap pool during execution.
        self.uc.mem_write(self.pool_begin,b"\xCD"*(self.pool_end-self.pool_begin))
        sp=self.stack_top
        self.uc.reg_write(UC_ARM_REG_SP,sp)
        self.uc.reg_write(UC_ARM_REG_LR,self.stop|1)
        self.uc.reg_write(UC_ARM_REG_R0,request)
        self.uc.emu_start(self.entry|1,self.stop,timeout=10000000,count=10000000)
        assert self.uc.reg_read(UC_ARM_REG_PC)==self.stop
        assert self.uc.reg_read(UC_ARM_REG_SP)==sp
        assert self.uc.reg_read(UC_ARM_REG_R0)==1
        error=self.uc.mem_read(request+36,1)[0]
        assert error==0,(error,self.lines,self.trace[-15:])
        assert bytes(self.uc.mem_read(self.pool_begin,self.pool_end-self.pool_begin))==b"\xCD"*(self.pool_end-self.pool_begin)
        return decode_values(bytes(self.uc.mem_read(values,26*8)))

def main():
    parser=argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--resident-elf",type=Path,required=True)
    parser.add_argument("--probe",type=Path,default=ROOT/"tmp/language-vm/probe")
    parser.add_argument("--local-float",action="store_true")
    args=parser.parse_args()
    cases=[("basic","10 A=14/5\n",2.8),
           ("basic","10 A=0\n20 FOR I=1 TO 3\n30 A=A+I\n40 NEXT I\n",6),
           ("focal","1.10 D 2\n1.20 E\n2.10 F I=1,3; S A=A+I\n",6)]
    if args.local_float:
        cases.append(("focal","1.10 S A=SQRT(2)\n1.20 E\n",
                      struct.unpack("<f",struct.pack("<f",math.sqrt(2)))[0]))
    with tempfile.TemporaryDirectory(prefix="mk61-resident-vm-") as directory:
        for language,source,expected in cases:
            text=Path(directory)/"source.txt";image=Path(directory)/"image.bvm"
            text.write_text(source)
            run([args.probe,language,text,image])
            m=ResidentMachine(args.resident_elf)
            values=m.execute(image.read_bytes())
            assert abs(values[0]-expected)<1e-12,(language,values[0],expected)
    print("resident VM ARM: Flash execution, poisoned APP pool, control and arithmetic PASS")

if __name__=="__main__":main()

#!/usr/bin/env python3
"""Run the actual APP reader: service input only after a completed C9 read.

The filesystem and bounded storage hook are intercepted independently. The
unchanged hook body/USB/IRQ/pinned-buffer contract is covered separately by
run_storage_input_arm_tests.py. No physical port is opened.
"""
import argparse
from pathlib import Path
import struct

from unicorn.arm_const import UC_ARM_REG_LR, UC_ARM_REG_PC, UC_ARM_REG_R0, UC_ARM_REG_R1, UC_ARM_REG_R2, UC_ARM_REG_R3, UC_ARM_REG_SP
from run_usb_screen_cold_buffers_arm_tests import Buffers


class Loader(Buffers):
    CONTEXT=0x2001C000
    OUTPUT=0x2001C100

    def __init__(self,path):
        self.read_ok=True;self.short=False;self.events=[]
        super().__init__(path)
        self.read=self.elf.symbol('_ZN13program_store13read_range_idEttPhtPt')&~1
        self.service=self.elf.symbol('_Z18storage_io_processv')&~1
        self.uc.mem_write(self.CONTEXT,struct.pack('<HH',42,1088))

    def hook(self,uc,address,size,context):
        if address==getattr(self,'read',None):
            file_id,offset,out,count=(uc.reg_read(r) for r in (UC_ARM_REG_R0,UC_ARM_REG_R1,UC_ARM_REG_R2,UC_ARM_REG_R3))
            assert file_id==42 and out==self.OUTPUT and 64<=offset<=1088 and count<=1024
            self.events.append('read')
            copied=count-1 if self.short else count
            uc.mem_write(out,bytes([0xA5])*copied)
            uc.mem_write(self.word(uc.reg_read(UC_ARM_REG_SP)),struct.pack('<H',copied))
            uc.reg_write(UC_ARM_REG_R0,int(self.read_ok))
        elif address==getattr(self,'service',None):
            assert self.events and self.events[-1]=='read','service preceded the C9 read'
            assert self.read_ok and not self.short
            self.events.append('service')
        else:
            super().hook(uc,address,size,context);return
        uc.reg_write(UC_ARM_REG_PC,uc.reg_read(UC_ARM_REG_LR))

    def payload(self,offset=0,size=128):
        self.events=[]
        return self.call('_ZN15loadable_module12_GLOBAL__N_1L16read_app_payloadEPvmPhj',self.CONTEXT,offset,self.OUTPUT,size)


def check(path,expect_unserviced):
    m=Loader(path)
    for offset in range(0,1024,128):
        assert m.payload(offset)==1
        assert m.events==(['read'] if expect_unserviced else ['read','service'])
        assert bytes(m.uc.mem_read(m.OUTPUT,128))==b'\xA5'*128
    for read_ok,short in ((False,False),(True,True)):
        m.read_ok=read_ok;m.short=short
        assert m.payload()==0 and m.events==['read']
    m.read_ok=True;m.short=False
    for offset,size in ((1025,1),(1024,1),(0,65536)):
        assert m.payload(offset,size)==0 and not m.events
    print('Original APP reader: missing input service REPRODUCED' if expect_unserviced else
          'APP reader: completed-read service, bytes/offsets, short/failing reads and bounds PASS',flush=True)


def main():
    ap=argparse.ArgumentParser(description=__doc__)
    ap.add_argument('--resident-elf',required=True,type=Path)
    ap.add_argument('--expect-unserviced',action='store_true')
    a=ap.parse_args();check(a.resident_elf,a.expect_unserviced)


if __name__=='__main__':main()

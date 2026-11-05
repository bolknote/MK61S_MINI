#!/usr/bin/env python3
"""Real resident scanner callbacks must permit a modal owner to scan again."""
import argparse
from pathlib import Path
import struct
from unicorn.arm_const import UC_ARM_REG_LR, UC_ARM_REG_PC, UC_ARM_REG_R0
from run_usb_screen_cold_buffers_arm_tests import Buffers


class Scanner(Buffers):
    def __init__(self,path,expect_locked):
        self.expect_locked=expect_locked;self.callbacks=0
        super().__init__(path)
        self.uc.mem_map(0x40000000,0x100000)
        self.uc.mem_map(0xE000E000,0x1000)
        self.now=2000000
        self.micros=self.elf.symbols.get('micros',0)&~1
        self.state=self.elf.symbol('_ZL10scan_state')
        self.events={self.elf.symbol('event_hold_key')&~1,self.elf.symbol('event_unhold_key')&~1}
        # The callback really calls the shipping sampler, preserving
        # the outer scanner's return address; no second consumer is installed.
        self.stub=self.STOP+0x100
        target=self.elf.symbol('_ZN3kbd4scanEv')
        self.uc.mem_write(self.stub,bytes.fromhex('10b5014b984710bd')+struct.pack('<I',target|1))
        self.uc.mem_write(self.elf.symbol('uwTick'),struct.pack('<I',2000))

    def hook(self,uc,address,size,context):
        if address in getattr(self,'events',set()):
            self.callbacks+=1
            state=bytes(uc.mem_read(self.state,1))[0]
            assert state==(2 if self.expect_locked else 1),('callback scanner lock',state)
            if self.expect_locked:
                uc.reg_write(UC_ARM_REG_PC,uc.reg_read(UC_ARM_REG_LR));return
            # Let the nested scan sample a real (all keys released) GPIO row.
            uc.mem_write(self.elf.symbol('_ZL20scan_line_started_us'),struct.pack('<I',self.now-1000))
            uc.reg_write(UC_ARM_REG_PC,self.stub|1);return
        if address==getattr(self,'micros',-1):
            uc.reg_write(UC_ARM_REG_R0,self.now)
            uc.reg_write(UC_ARM_REG_PC,uc.reg_read(UC_ARM_REG_LR));return
        super().hook(uc,address,size,context)

    def prepare(self):
        self.uc.mem_write(self.state,b'\x01')
        self.uc.mem_write(self.elf.symbol('_ZL20scan_line_started_us'),struct.pack('<I',self.now))
        self.uc.mem_write(self.elf.symbol('_ZL9scan_line'),struct.pack('<I',0))
        self.uc.mem_write(self.elf.symbol('_ZL16holded_scan_code'),struct.pack('<i',-1))


def main():
    p=argparse.ArgumentParser(description=__doc__);p.add_argument('--resident-elf',type=Path,required=True)
    p.add_argument('--expect-locked',action='store_true');args=p.parse_args()
    for release in (False,True):
        m=Scanner(args.resident_elf,args.expect_locked);m.prepare()
        if release:
            m.uc.mem_write(m.elf.symbol('_ZL21deferred_hold_release'),struct.pack('<ii',35,0))
        else:
            m.uc.mem_write(m.elf.symbol('_ZL16holded_scan_code'),struct.pack('<i',35))
            m.uc.mem_write(m.elf.symbol('_ZL18hold_quant_counter'),struct.pack('<i',-1))
            m.uc.mem_write(m.elf.symbol('_ZL10press_time'),struct.pack('<I',0))
        m.call('_ZN3kbd4scanEv')
        assert m.callbacks==1
        assert bytes(m.uc.mem_read(m.state,1))==b'\x01'
        assert m.word(m.elf.symbol('_ZL9scan_line'))==(0 if args.expect_locked else 1)
    print('Keyboard modal callbacks: '+('old scanner lock REPRODUCED' if args.expect_locked else
          'hold/release callbacks outside sampling guard, nested physical scan PASS'))


if __name__=='__main__':main()

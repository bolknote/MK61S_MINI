#!/usr/bin/env python3
"""Execute the linked M3 sleep code; model timer wake, not electrical power."""
from pathlib import Path
import argparse,hashlib,json,struct,sys
ROOT=Path(__file__).resolve().parents[1]
sys.path[:0]=[str(ROOT/'sdk/coproc'),str(ROOT/'tests')]
from elf32 import ELF
from unicorn_runtime import Uc
from unicorn import UC_ARCH_ARM,UC_MODE_MCLASS,UC_MODE_THUMB,UC_HOOK_CODE,UC_HOOK_MEM_WRITE
from unicorn.arm_const import UC_CPU_ARM_CORTEX_M3,UC_ARM_REG_SP,UC_ARM_REG_LR,UC_ARM_REG_PC,UC_ARM_REG_R0,UC_ARM_REG_PRIMASK,UC_ARM_REG_BASEPRI,UC_ARM_REG_FAULTMASK

class Machine:
    STOP=0x0800fff0
    SCR=0xe000ed10
    def __init__(self,path):
        self.elf=ELF(path);self.u=Uc(UC_ARCH_ARM,UC_MODE_MCLASS|UC_MODE_THUMB)
        self.u.ctl_set_cpu_model(UC_CPU_ARM_CORTEX_M3)
        for at,n in [(0x08000000,0x10000),(0x20000000,0x10000),(0x40000000,0x30000),(0xe000e000,0x2000)]:self.u.mem_map(at,n)
        for segment in self.elf.segments:
            if segment['data']:self.u.mem_write(segment['address'],segment['data'])
        self.waits=0;self.peripheral_writes=0;self.delay=True
        self.u.hook_add(UC_HOOK_CODE,self.code);self.u.hook_add(UC_HOOK_MEM_WRITE,self.write)
        self.u.reg_write(UC_ARM_REG_PRIMASK,0)
        self.put(self.address('systicks_counter'),0);self.put(0x40000024,100)
    def address(self,name):return self.elf.symbols[name]['value']
    def get(self,at):return struct.unpack('<I',self.u.mem_read(at,4))[0]
    def put(self,at,value):self.u.mem_write(at,struct.pack('<I',value&0xffffffff))
    def write(self,u,access,at,size,value,context):
        if not 0x20000000<=at<0x20010000:
            self.peripheral_writes+=1;raise AssertionError(('unexpected non-RAM write',hex(at),hex(value)))
    def code(self,u,pc,size,context):
        if bytes(u.mem_read(pc,2))==b'\x30\xbf':
            assert u.reg_read(UC_ARM_REG_PRIMASK)==1 and self.get(self.SCR)==0
            self.waits+=1
            if self.delay:self.put(0x40000010,1);self.put(0x40000024,0) # TIM2 IRQ pending at next millisecond.
            u.reg_write(UC_ARM_REG_PC,(pc+2)|1) # Keep Thumb state while modeling the wake.
    def call(self,name,arg=0):
        self.u.reg_write(UC_ARM_REG_SP,0x20004e00);self.u.reg_write(UC_ARM_REG_LR,self.STOP|1)
        self.u.reg_write(UC_ARM_REG_R0,arg)
        self.u.emu_start(self.address(name)|1,self.STOP,timeout=1000000,count=100000)
        assert self.u.reg_read(UC_ARM_REG_PC)==self.STOP and self.u.reg_read(UC_ARM_REG_SP)==0x20004e00,name
        result=self.u.reg_read(UC_ARM_REG_R0)
        if self.get(0x40000010)&1 and not self.u.reg_read(UC_ARM_REG_PRIMASK):
            self.put(self.address('systicks_counter'),self.get(self.address('systicks_counter'))+1)
            self.put(0x40000010,0) # Deliver timer accounting after unmask.
        return result
    def stats(self):return tuple(self.get(self.address('bios_sleep_stats')+i)for i in [0,4,8])

def run(path):
    m=Machine(path)
    assert m.call('bios_sleep_status')==0xd0
    m.call('bios_sleep_poll',1);assert m.waits==0
    m.call('bios_sleep_write',0xa5);assert m.call('bios_sleep_status')==0xd1
    m.call('bios_sleep_poll',0);assert m.waits==0
    m.call('bios_sleep_poll',1);assert m.waits==1 and m.stats()==(1,900,0)
    assert m.call('bios_sleep_status')==0xd3
    assert m.u.reg_read(UC_ARM_REG_PRIMASK)==0
    m.put(m.address('systicks_counter'),1999);m.call('bios_sleep_write',0xa5)
    m.put(m.address('systicks_counter'),3998);m.call('bios_sleep_poll',1);assert m.waits==2
    m.put(m.address('systicks_counter'),3999);m.call('bios_sleep_poll',1)
    assert m.waits==2 and m.call('bios_sleep_status')==0xd0 and m.stats()[2]==1
    m.call('bios_sleep_write',0xa5);m.call('bios_sleep_write',0x5a);m.call('bios_sleep_poll',1);assert m.waits==2
    m.put(m.address('systicks_counter'),0xfffffff0);m.call('bios_sleep_write',0xa5)
    m.put(m.address('systicks_counter'),0x7c0);m.call('bios_sleep_poll',1)
    assert m.call('bios_sleep_status')==0xd0 and m.stats()[2]==2
    m.call('bios_sleep_write',0xa5)
    for reg,value in [(UC_ARM_REG_PRIMASK,1),(UC_ARM_REG_BASEPRI,16),(UC_ARM_REG_FAULTMASK,1)]:
        m.u.reg_write(reg,value);m.call('bios_sleep_poll',1);assert m.u.reg_read(reg)==value;m.u.reg_write(reg,0)
    for scr in [2,4]:m.put(m.SCR,scr);m.call('bios_sleep_poll',1);assert m.get(m.SCR)==scr
    m.put(m.SCR,0);assert m.waits==2
    m.delay=False;before=m.stats()[1];m.call('bios_sleep_poll',1);assert m.stats()[1]==before and m.waits==3
    assert m.peripheral_writes==0
    return {'status':'PASS','elf_sha256':hashlib.sha256(Path(path).read_bytes()).hexdigest(),
        'physical_io':False,'electrical_power_measured':False,'timer_wake_modeled':True,'WFI_instructions_executed':m.waits,
        'peripheral_or_power_reset_clock_writes':m.peripheral_writes,
        'cases':['linked Cortex-M3 code','tagged enter/leave','module/transport guard','lease renewal/expiry/wrap',
                 'TIM2 pending rollover accounting','masked IRQ/basepri/faultmask preserved','deep sleep modes rejected','pending interrupt immediate return','stack preserved']}
if __name__=='__main__':
    p=argparse.ArgumentParser(description=__doc__);p.add_argument('--elf',type=Path,required=True);p.add_argument('--output',type=Path)
    a=p.parse_args();r=run(a.elf);out=json.dumps(r,indent=2)+'\n'
    if a.output:a.output.write_text(out)
    print(out,end='')

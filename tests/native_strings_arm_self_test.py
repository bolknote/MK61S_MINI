#!/usr/bin/env python3
"""Execute the production ARM string code with strict read/write bounds and independent byte oracles."""
import argparse
import random
from pathlib import Path
from unicorn import Uc,UC_ARCH_ARM,UC_MODE_MCLASS,UC_MODE_THUMB,UC_HOOK_MEM_READ,UC_HOOK_MEM_WRITE
from unicorn.arm_const import *
from check_stm32_vectors import ElfImage
STOP=0x080FF000;SP=0x2001FFF0;A=0x20001000;B=0x20001800;D=0x20003000
REGS=(UC_ARM_REG_R0,UC_ARM_REG_R1,UC_ARM_REG_R2,UC_ARM_REG_R3)
def signed(v):return v-(1<<32) if v&(1<<31) else v
def sign(v):return (v>0)-(v<0)
class Machine:
    def __init__(self,path):
        self.elf=ElfImage(path);self.uc=Uc(UC_ARCH_ARM,UC_MODE_MCLASS|UC_MODE_THUMB)
        self.uc.mem_map(0x08000000,0x100000);self.uc.mem_map(0x20000000,0x20000)
        self.elf.load(self.uc);self.reads=[];self.calls=0
        self.uc.hook_add(UC_HOOK_MEM_READ,self.read);self.uc.hook_add(UC_HOOK_MEM_WRITE,self.write)
    def read(self,uc,access,address,size,value,user):
        del uc,access,value,user
        ranges=[(0x08000000,STOP),(SP-1024,SP),(D,D+1024),*self.reads]
        assert any(lo<=address and address+size<=hi for lo,hi in ranges),('read outside string',hex(address),size,self.reads)
    def write(self,uc,access,address,size,value,user):
        del uc,access,value,user
        assert (SP-1024<=address and address+size<=SP) or (D<=address and address+size<=D+1024),('write outside destination/stack',hex(address),size)
    def call(self,name,*args):
        saved={reg:(0xA0712491+reg*0x1021)&0xFFFFFFFF for reg in range(UC_ARM_REG_R4,UC_ARM_REG_R11+1)}
        for reg,val in saved.items():self.uc.reg_write(reg,val)
        for reg,val in zip(REGS,(*args,0,0,0,0)):self.uc.reg_write(reg,val&0xFFFFFFFF)
        self.uc.reg_write(UC_ARM_REG_SP,SP);self.uc.reg_write(UC_ARM_REG_LR,STOP|1);self.uc.reg_write(UC_ARM_REG_XPSR,0x01000000)
        self.uc.emu_start(self.elf.symbols[name]|1,STOP,count=100000)
        assert self.uc.reg_read(UC_ARM_REG_PC)==STOP,(name,'did not return')
        assert self.uc.reg_read(UC_ARM_REG_SP)==SP,(name,'SP')
        for reg,val in saved.items():assert self.uc.reg_read(reg)==val,(name,'callee-saved',reg)
        self.calls+=1;return self.uc.reg_read(UC_ARM_REG_R0)
def run(path):
    m=Machine(path);rng=random.Random(0x4C494243)
    for iteration in range(1500):
        a=bytes(rng.randrange(1,256) for _ in range(rng.randrange(258)))
        b=a if iteration%3==0 else bytes(rng.randrange(1,256) for _ in range(rng.randrange(258)))
        ap=A+iteration%4;bp=B+(iteration//4)%4;n=rng.randrange(260)
        m.uc.mem_write(ap,a+b'\0');m.uc.mem_write(bp,b+b'\0');m.reads=[(ap,ap+len(a)+1),(bp,bp+len(b)+1)]
        blank=b'\xA7'*1024;m.uc.mem_write(D,blank)
        assert m.call('strlen',ap)==len(a)
        assert m.call('strnlen',ap,n)==min(len(a),n)
        c=(0,255,128,0x1234,-1,rng.randrange(256))[iteration%6];at=(a+b'\0').find(bytes([c&255]))
        assert m.call('strchr',ap,c)==(0 if at<0 else ap+at)
        assert sign(signed(m.call('strcmp',ap,bp)))==sign((a>b)-(a<b))
        assert sign(signed(m.call('strncmp',ap,bp,n)))==sign((a[:n]>b[:n])-(a[:n]<b[:n]))
        assert m.uc.mem_read(D,1024)==blank
        if 'memchr' in m.elf.symbols:
            at=(a+b'\0').find(bytes([c&255]));assert m.call('memchr',ap,c,len(a)+1)==(0 if at<0 else ap+at)
        for name in ('strcpy','strncpy','strncat'):
            if name not in m.elf.symbols:continue # Unexported, unused function may be section-GC'd.
            m.uc.mem_write(D,blank)
            expected=bytearray(blank)
            if name=='strcpy':
                expected[:len(a)+1]=a+b'\0';result=m.call(name,D,ap)
            elif name=='strncpy':
                value=(a+b'\0'*n)[:n];expected[:n]=value;result=m.call(name,D,ap,n)
            else:
                m.uc.mem_write(D,b'ABC\0');value=b'ABC'+a[:n]+b'\0';expected[:len(value)]=value;result=m.call(name,D,ap,n)
            assert result==D and m.uc.mem_read(D,1024)==expected,(name,iteration,n)
        assert m.uc.mem_read(ap,len(a)+1)==a+b'\0' and m.uc.mem_read(bp,len(b)+1)==b+b'\0'
    print(path.parent.name,m.calls,'ARM ISO string calls: byte oracles, bounded reads/writes, unsigned order, padding and ABI PASS',flush=True)
def main():
    p=argparse.ArgumentParser(description=__doc__);p.add_argument('--elf',action='append',type=Path,required=True)
    for path in p.parse_args().elf:run(path)
if __name__=='__main__':main()

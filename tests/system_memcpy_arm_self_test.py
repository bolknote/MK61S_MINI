#!/usr/bin/env python3
"""Execute production memcpy on M0+/M4: bounds, alignment, bytes and AAPCS.

Memory hooks reject even a one-byte source overread, misaligned M0 access or
write beyond the destination. Timing is measured separately on physical CPUs.
"""
import argparse,hashlib,json,random,shutil,subprocess,tempfile
from pathlib import Path
from check_stm32_vectors import ElfImage
from unicorn import Uc,UC_ARCH_ARM,UC_MODE_THUMB,UC_MODE_MCLASS,UC_HOOK_MEM_READ,UC_HOOK_MEM_WRITE,UC_MEM_WRITE
from unicorn.arm_const import (UC_CPU_ARM_CORTEX_M0,UC_CPU_ARM_CORTEX_M4,
    UC_ARM_REG_R0,UC_ARM_REG_R1,UC_ARM_REG_R2,UC_ARM_REG_R4,UC_ARM_REG_R11,
    UC_ARM_REG_SP,UC_ARM_REG_LR,UC_ARM_REG_PC,UC_ARM_REG_XPSR)
ROOT=Path(__file__).resolve().parents[1]
def verify(elf,cpu,names):
    e=ElfImage(elf)
    u=Uc(UC_ARCH_ARM,UC_MODE_THUMB|UC_MODE_MCLASS)
    u.ctl_set_cpu_model(UC_CPU_ARM_CORTEX_M0 if cpu=='m0' else UC_CPU_ARM_CORTEX_M4)
    u.mem_map(0x20000000,0x100000);u.mem_map(0x08000000,0x100000)
    u.mem_map(0x10000000,0x200000);u.mem_map(0x30000000,4096)
    e.load(u)
    stop=0x30000000;sp=0x200fe000;src=0x20020000;dst=0x20050000
    r=random.Random(610411)
    cases=[(n,s,d) for n in range(258) for s in range(4) for d in range(4)]
    cases += [(n,s,d) for n in (511,512,513,1023,1024,1025,4095,4096,4097,16383,16384,65535,65536) for s in range(4) for d in range(4)]
    cases += [(r.randrange(8193),r.randrange(16),r.randrange(16)) for _ in range(500)]
    cases += [(0,0,0)]
    active=[0,0,0,0,0]
    pattern=bytes(r.getrandbits(8) for _ in range(65664))
    saved={i:0x72816201+i*314 for i in range(UC_ARM_REG_R4,UC_ARM_REG_R11+1)}
    def access(machine,typ,addr,size,value,user):
     del machine,value,user
     n,s,d,code_start,code_end=active
     if cpu=='m0':assert size in (1,2,4) and addr%size==0,('alignment',hex(addr),size,active)
     if typ==UC_MEM_WRITE:
      assert (d<=addr and addr+size<=d+n) or (sp-64<=addr and addr+size<=sp),('write bound',hex(addr),size,active)
     else:
      assert (s<=addr and addr+size<=s+n) or (sp-64<=addr and addr+size<=sp) or (code_start<=addr and addr+size<=code_end),('read bound',hex(addr),size,active)
    u.hook_add(UC_HOOK_MEM_READ|UC_HOOK_MEM_WRITE,access)
    results=[]
    for name in names:
     for i,(n,so,do) in enumerate(cases):
      s=src+so;d=dst+do
      if i==len(cases)-1:s=d=0
      active[:]=[n,s,d,e.symbols[name]&~1,(e.symbols[name]&~1)+e.sizes[name]]
      u.mem_write(src-16,pattern[:n+64]);u.mem_write(dst-16,b'\x5A'*(n+64))
      expected=bytes(u.mem_read(s,n)) if n else b''
      for reg,v in saved.items():u.reg_write(reg,v)
      for reg,v in ((UC_ARM_REG_R0,d),(UC_ARM_REG_R1,s),(UC_ARM_REG_R2,n),(UC_ARM_REG_SP,sp),(UC_ARM_REG_LR,stop|1),(UC_ARM_REG_XPSR,0x01000000)):
       u.reg_write(reg,v)
      try:u.emu_start(e.symbols[name]|1,stop,count=1000000)
      except Exception:print('FAIL',name,n,so,do,hex(u.reg_read(UC_ARM_REG_PC)));raise
      assert u.reg_read(UC_ARM_REG_PC)==stop,(name,n,so,do,'return')
      assert u.reg_read(UC_ARM_REG_R0)==d and u.reg_read(UC_ARM_REG_SP)==sp,(name,n,so,do,'AAPCS return')
      assert all(u.reg_read(reg)==v for reg,v in saved.items()),(name,n,so,do,'callee saved')
      actual=bytes(u.mem_read(dst-16,n+64))
      want=b'\x5A'*(16+do)+expected+b'\x5A'*(48-do)
      assert actual==want,(name,n,so,do,'content')
      assert bytes(u.mem_read(src-16,n+64))==pattern[:n+64],(name,'source modified')
     row=dict(name=name,cases=len(cases),bytes=e.sizes.get(name),status='PASS');results.append(row);print(row,flush=True)
    return dict(cpu=cpu,elf_sha256=hashlib.sha256(elf.read_bytes()).hexdigest(),results=results)

def main():
    p=argparse.ArgumentParser(description=__doc__)
    p.add_argument('--arm-toolchain-bin',type=Path)
    p.add_argument('--elf',type=Path)
    p.add_argument('--cpu',choices=('m0','m4'))
    p.add_argument('--names',nargs='+',default=['memcpy'])
    p.add_argument('--output',type=Path)
    a=p.parse_args();results=[]
    if a.elf:
        assert a.cpu,'Pass --cpu with --elf'
        results.append(verify(a.elf,a.cpu,a.names))
    else:
        compiler=shutil.which('arm-none-eabi-gcc')
        tc=a.arm_toolchain_bin or (Path(compiler).parent if compiler else None)
        assert tc,'Pass --arm-toolchain-bin'
        variants=[('m0','sdk/portable/memory.c','memcpy',[]),
                  ('m4','sdk/portable/memory.c','memcpy',[]),
                  ('m4','code/system_memory.c','memcpy',['-DMK61_MEMORY_TEST_BUILD=1']),
                  ('m0','ports/picocalc/memory.c','__wrap_memcpy',['-DPICO_ON_DEVICE=1'])]
        with tempfile.TemporaryDirectory(prefix='mk61-memcpy-arm-') as tmp:
            elf=Path(tmp)/'copy.elf'
            for cpu,source,name,defines in variants:
                for lto in (False,True):
                    command=[str(tc/'arm-none-eabi-gcc'),'-mcpu='+('cortex-m0plus' if cpu=='m0' else 'cortex-m4'),
                        '-mthumb','-Os','-std=c11','-Wall','-Wextra','-Werror','-fno-builtin',
                        '-ffunction-sections','-fdata-sections',*(['-flto'] if lto else []),*defines,
                        str(ROOT/source),'-I'+str(ROOT/'code'),'-nostdlib',
                        '-Wl,--gc-sections,-Ttext=0x20000000,--section-start=.time_critical.memcpy=0x20001000,-e,'+name,
                        *(['-Wl,-u,__wrap___aeabi_memcpy,-u,__wrap___aeabi_memcpy4,-u,__wrap___aeabi_memcpy8'] if name=='__wrap_memcpy' else []),
                        '-o',str(elf)]
                    subprocess.run(command,check=True)
                    result=verify(elf,cpu,[name]);result.update(source=source,lto=lto)
                    if name=='__wrap_memcpy':
                        e=ElfImage(elf)
                        for alias in ('__wrap___aeabi_memcpy','__wrap___aeabi_memcpy4','__wrap___aeabi_memcpy8'):
                            assert e.symbols[alias]==e.symbols[name],alias
                        result['eabi_aliases']='PASS'
                    results.append(result)
    if a.output:a.output.write_text(json.dumps(results,indent=2)+'\n')
if __name__=='__main__':main()

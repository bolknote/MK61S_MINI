#!/usr/bin/env python3
"""Execute real memmove ARM code: overlapping spans, exact bounds and AAPCS."""
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
    u.mem_map(0,0x10000);u.mem_map(0x1fff0000,0x10000)
    u.mem_write(0,(ROOT/'research/rp2040-memset-2026-10-21/capture/bootrom.bin').read_bytes())
    u.mem_write(0x1fff0000,(ROOT/'research/stm32f411-rom-2026-10-21/capture/rom-a.bin').read_bytes())
    e.load(u)
    stop=0x30000000;sp=0x200fe000;base=0x20030000
    r=random.Random(610424)
    # All short lengths, all four alignments, both directions, adjacent words,
    # same address and the exact overlap/non-overlap boundary.
    cases=[]
    for n in range(258):
        for s in range(4):
            for delta in sorted(set([-n-1,-n,-31,-16,-15,-8,-7,-4,-3,-2,-1,0,1,2,3,4,7,8,15,16,31,n,n+1])):
                cases.append((n,s,delta))
    for n in (511,512,513,1023,1024,1025,4095,4096,4097,16384,65536):
        for s in range(4):
            for delta in (-n,-17,-4,-1,0,1,4,17,n):cases.append((n,s,delta))
    cases += [(r.randrange(8193),r.randrange(16),r.randrange(-8192,8193)) for _ in range(300)]
    cases += [(0,0,0)]
    active=[0,0,0]
    literals=[(s[3],s[3]+s[5]) for s in e.sections if s[2]&4 and s[1]!=8]
    if 'rom_move' in names:literals.extend([(0x2604,0x26ac),(0x1fff0a4c,0x1fff0a6e)])
    pattern=bytes(r.getrandbits(8) for _ in range(2*65536+128))
    saved={i:0x72816201+i*314 for i in range(UC_ARM_REG_R4,UC_ARM_REG_R11+1)}
    def access(machine,typ,addr,size,value,user):
        del machine,value,user
        n,s,d=active
        if cpu=='m0':assert size in (1,2,4) and addr%size==0,('alignment',hex(addr),size,active)
        if typ==UC_MEM_WRITE:
            assert (d<=addr and addr+size<=d+n) or (sp-64<=addr and addr+size<=sp),('write bound',hex(addr),size,active)
        else:
            assert (s<=addr and addr+size<=s+n) or (sp-64<=addr and addr+size<=sp) or any(
                start<=addr and addr+size<=end for start,end in literals),('read bound',hex(addr),size,active)
    u.hook_add(UC_HOOK_MEM_READ|UC_HOOK_MEM_WRITE,access)
    results=[]
    for name in names:
        for i,(n,so,delta) in enumerate(cases):
            s=base+so;d=s+delta
            low=min(s,d)-16;length=n+abs(delta)+32
            if i==len(cases)-1:s=d=0
            active[:]=[n,s,d]
            original=pattern[:length];u.mem_write(low,original)
            expected=bytearray(original)
            if n:expected[d-low:d-low+n]=original[s-low:s-low+n]
            for reg,v in saved.items():u.reg_write(reg,v)
            for reg,v in ((UC_ARM_REG_R0,d),(UC_ARM_REG_R1,s),(UC_ARM_REG_R2,n),(UC_ARM_REG_SP,sp),(UC_ARM_REG_LR,stop|1),(UC_ARM_REG_XPSR,0x01000000)):
                u.reg_write(reg,v)
            try:u.emu_start(e.symbols[name]|1,stop,count=1500000)
            except Exception:print('FAIL',name,n,so,delta,hex(u.reg_read(UC_ARM_REG_PC)),flush=True);raise
            assert u.reg_read(UC_ARM_REG_PC)==stop,(name,n,so,delta,'return')
            assert u.reg_read(UC_ARM_REG_R0)==d and u.reg_read(UC_ARM_REG_SP)==sp,(name,n,so,delta,'AAPCS return')
            assert all(u.reg_read(reg)==v for reg,v in saved.items()),(name,n,so,delta,'callee saved')
            assert bytes(u.mem_read(low,length))==expected,(name,n,so,delta,'content/guard')
        row=dict(name=name,cases=len(cases),bytes=e.sizes.get(name),status='PASS');results.append(row);print(row,flush=True)
    return dict(cpu=cpu,elf_sha256=hashlib.sha256(elf.read_bytes()).hexdigest(),results=results)

def main():
    p=argparse.ArgumentParser(description=__doc__)
    p.add_argument('--arm-toolchain-bin',type=Path);p.add_argument('--elf',type=Path)
    p.add_argument('--cpu',choices=('m0','m4'));p.add_argument('--names',nargs='+',default=['memmove'])
    p.add_argument('--output',type=Path)
    a=p.parse_args();results=[]
    if a.elf:
        assert a.cpu,'Pass --cpu with --elf'
        result=verify(a.elf,a.cpu,a.names)
        if a.output:a.output.write_text(json.dumps(result,indent=2)+'\n')
        return
    compiler=shutil.which('arm-none-eabi-gcc')
    tc=a.arm_toolchain_bin or (Path(compiler).parent if compiler else None)
    assert tc,'Pass --arm-toolchain-bin'
    variants=[('m0','sdk/portable/memory.c','memmove',[]),('m4','sdk/portable/memory.c','memmove',[]),
              ('m4','code/system_memory_fill_move.c','memmove',['-DMK61_MEMORY_TEST_BUILD=1']),
              ('m0','ports/picocalc/memory.c','__wrap_memmove',['-DPICO_ON_DEVICE=1'])]
    with tempfile.TemporaryDirectory(prefix='mk61-memmove-arm-') as tmp:
        elf=Path(tmp)/'move.elf'
        for cpu,source,name,defines in variants:
            for lto in (False,True):
                cmd=[str(tc/'arm-none-eabi-gcc'),'-mcpu='+('cortex-m0plus' if cpu=='m0' else 'cortex-m4'),
                     '-mthumb','-Os','-std=c11','-Wall','-Wextra','-Werror','-fno-builtin','-ffunction-sections','-fdata-sections',
                     *(['-flto'] if lto else []),*defines,str(ROOT/source),'-I'+str(ROOT/'code'),'-nostdlib',
                     '-Wl,--gc-sections,-Ttext=0x20000000,--section-start=.time_critical.memmove=0x20001000,-e,'+name,
                     *(['-Wl,-u,__wrap___aeabi_memmove,-u,__wrap___aeabi_memmove4,-u,__wrap___aeabi_memmove8'] if name=='__wrap_memmove' else []),'-o',str(elf)]
                subprocess.run(cmd,check=True)
                result=verify(elf,cpu,[name]);result.update(source=source,lto=lto)
                if name=='__wrap_memmove':
                    e=ElfImage(elf)
                    for alias in ('__wrap___aeabi_memmove','__wrap___aeabi_memmove4','__wrap___aeabi_memmove8'):assert e.symbols[alias]==e.symbols[name],alias
                    result['eabi_aliases']='PASS'
                results.append(result)
    if a.output:a.output.write_text(json.dumps(results,indent=2)+'\n')
if __name__=='__main__':main()

#!/usr/bin/env python3
"""Build/qualify Cortex-M4 hard-float math and compare executed instructions."""
import argparse
import hashlib
import json
import math
from pathlib import Path
import random
import statistics
import struct
import subprocess
import sys
from unicorn import Uc,UC_ARCH_ARM,UC_MODE_MCLASS,UC_MODE_THUMB,UC_HOOK_MEM_WRITE
from unicorn.arm_const import *
from check_stm32_vectors import ElfImage
from compact_math_arm_self_test import MathMachine,NAMES,bits,value,distance
from profile_m0_trig import corpora as trig_corpora,oracle as trig_reference

ROOT=Path(__file__).resolve().parents[1]

class Machine(MathMachine):
    def __init__(self,path,resident=False):
        self.elf=ElfImage(path)
        self.uc=Uc(UC_ARCH_ARM,UC_MODE_MCLASS|UC_MODE_THUMB)
        self.uc.ctl_set_cpu_model(UC_CPU_ARM_CORTEX_M4)
        self.uc.mem_map(0x08000000,0x100000)
        self.uc.mem_map(0x20000000,0x20000)
        self.uc.reg_write(UC_ARM_REG_C1_C0_2,0xF00000)
        self.uc.reg_write(UC_ARM_REG_FPEXC,0x40000000)
        self.elf.load(self.uc)
        if resident:
            from run_portable_system_arm_tests import Elf
            Elf(path).require_binary64_math(path)
            api=self.elf.symbols['_ZZN15loadable_module12app_servicesEvE3api']
            assert struct.unpack('<IHH',self.uc.mem_read(api,8))==(0x31535953,2,28)
            self.entry=struct.unpack('<I',self.uc.mem_read(api+16,4))[0]
            self.stack_top=self.elf.symbols['_estack']-16
        else:
            self.entry=self.elf.symbols['mk61_m4_math']
            self.stack_top=0x2001FFF0
        self.compact=True;self.instructions=0
        self.uc.hook_add(UC_HOOK_MEM_WRITE,self.check_write)

def build(source_root,out):
    sys.path.insert(0,str(ROOT/'tools'))
    from build_picocalc import compiler_bin
    tc=compiler_bin(None);out.mkdir(parents=True,exist_ok=True)
    flags=['-mcpu=cortex-m4','-mthumb','-mfpu=fpv4-sp-d16','-mfloat-abi=hard','-Os',
        '-fno-builtin','-ffunction-sections','-fdata-sections','-DMK61_NATIVE_RUNTIME=1',
        '-DMK61_USE_NATIVE_EABI=1','-DMK61_USE_M0_EABI=0','-DMK61_USE_COMPACT_LIBM=1',
        '-DMK61_MATH_BACKEND=0','-I'+str(source_root/'code'),'-I'+str(ROOT/'sdk/portable/include')]
    objects=[];commands=[]
    for source,lto in [(source_root/'code/compact_math.cpp',True),
        (source_root/'code/native_eabi.cpp',False),(source_root/'code/native_eabi_arm.S',False),
        (source_root/'code/native_eabi_fixed.S',False),(ROOT/'sdk/portable/memory.c',False),
        (ROOT/'tests/fixtures/m4_math_entry.cpp',True)]:
        obj=out/(source.name+'.o');objects.append(obj)
        cpp=source.suffix=='.cpp'
        cmd=[str(tc/('arm-none-eabi-g++' if cpp else 'arm-none-eabi-gcc')),*flags,
            '-flto' if lto else '-fno-lto',*(['-std=c++17','-fno-exceptions','-fno-rtti'] if cpp else []),
            '-Wall','-Wextra','-Werror','-c',str(source),'-o',str(obj)]
        subprocess.run(cmd,check=True);commands.append(cmd)
    elf=out/'math.elf'
    cmd=[str(tc/'arm-none-eabi-g++'),*flags,'-flto','-nostdlib','-Wl,-Ttext=0x08000000',
        '-Wl,-e,mk61_m4_math','-Wl,--undefined=mk61_m4_math','-Wl,-Map='+str(out/'math.map'),
        *map(str,objects),'-o',str(elf)]
    subprocess.run(cmd,check=True);commands.append(cmd)
    assert not subprocess.check_output([str(tc/'arm-none-eabi-nm'),'-u',str(elf)])
    (out/'build.json').write_text(json.dumps({'commands':commands,'source_root':str(source_root),
        'sha256':hashlib.sha256(elf.read_bytes()).hexdigest()},indent=2)+'\n')
    return elf

def corpora():
    groups=[(op,name,[(a,0) for a in inputs]) for op,name,inputs in trig_corpora() if op!='i2d']
    rng=random.Random(0x614004);n=128
    full=[(rng.getrandbits(1)<<63)|(rng.randrange(1,2047)<<52)|rng.getrandbits(52) for _ in range(n)]
    groups += [(op,'full_exponents',[(a,0) for a in full]) for op in ('sin','cos','tan')]
    for op in ('ln','log10'):
        for label,inputs in [('normal_exponents',[(rng.randrange(1,2047)<<52)|rng.getrandbits(52) for _ in range(n)]),
            ('normalized',[bits(rng.uniform(.5,2)) for _ in range(n)]),
            ('near_one_interval',[bits(rng.uniform(63/64,65/64)) for _ in range(n)]),
            ('near_one_ulps',[bits(1.)+i for i in range(-64,64)])]:
            groups.append((op,label,[(a,0) for a in inputs]))
    for label,limit in [('ordinary',32),('reduced',1),('small',1/64)]:
        groups.append(('atan',label,[(bits(rng.uniform(-limit,limit)),0) for _ in range(n)]))
    for label,limit in [('small_range',8),('normal_exponents',700)]:
        groups.append(('exp',label,[(bits(rng.uniform(-limit,limit)),0) for _ in range(n)]))
    for op in ('asin','acos'):
        groups.append((op,'normal',[(bits(rng.uniform(-1,1)),0) for _ in range(n)]))
    groups.append(('sqrt','normal_exponents',[(a&((1<<63)-1),0) for a in full]))
    groups.append(('pow','ordinary',[(bits(rng.uniform(.125,8)),bits(rng.uniform(-8,8))) for _ in range(n)]))
    return groups

def main():
    p=argparse.ArgumentParser(description=__doc__)
    p.add_argument('--elf',type=Path)
    p.add_argument('--source-root',type=Path,default=ROOT)
    p.add_argument('--build-dir',type=Path)
    p.add_argument('--baseline-elf',type=Path)
    p.add_argument('--resident',action='store_true',help='Call the full firmware public math service instead of the standalone test entry')
    p.add_argument('--qualification',action='store_true')
    p.add_argument('--samples',type=int,default=10000)
    p.add_argument('--require-improvement',action='store_true')
    p.add_argument('--json',type=Path,required=True)
    a=p.parse_args()
    own=a.elf or build(a.source_root.resolve(),a.build_dir.resolve())
    paths={'OWN':own}
    if a.baseline_elf:paths['BASE']=a.baseline_elf
    hashes={k:hashlib.sha256(v.read_bytes()).hexdigest() for k,v in paths.items()}
    machines={k:Machine(v,a.resident) for k,v in paths.items()};groups=[]
    cache={}
    def expected(op,x,y):
        if op in ('sin','cos','tan'):
            if x not in cache:cache[x]=trig_reference(x)
            return cache[x][('sin','cos','tan').index(op)]
        f={'ln':math.log,'log10':math.log10,'atan':math.atan,'exp':math.exp,'sqrt':math.sqrt,
           'asin':math.asin,'acos':math.acos}.get(op)
        return bits(f(value(x)) if f else math.pow(value(x),value(y)))
    for op,label,inputs in corpora():
        improved=op in ('sin','cos','tan','atan','ln','log10','exp')
        rows=[];counts={k:[] for k in paths};worst={k:0 for k in paths}
        for x,y in inputs:
            gold=expected(op,x,y);values={}
            for k,m in machines.items():
                got,count=m.call(NAMES.index(op),x,y,True);error=distance(got,gold)
                assert error<=(0 if op=='sqrt' else 4),(op,label,k,hex(x),hex(y),hex(got),hex(gold),error)
                counts[k].append(count);worst[k]=max(worst[k],error)
                values[k]={'result':f'{got:016X}','instructions':count,'ulp':error}
            if not improved and 'BASE' in values:
                assert values['OWN']['result']==values['BASE']['result'],(op,label,hex(x),hex(y),values)
            rows.append({'a':f'{x:016X}','b':f'{y:016X}','reference':f'{gold:016X}','implementations':values})
        stats={k:{'mean':statistics.mean(v),'min':min(v),'max':max(v),'worst_ulp':worst[k]} for k,v in counts.items()}
        if a.require_improvement:
            # LTO can change dispatcher/inlining/branch layouts by a few
            # instructions even for unchanged algorithms. Check their exact
            # results above and bound that diagnostic drift separately.
            limit=stats['BASE']['mean']+(0 if improved else 8)
            assert stats['OWN']['mean']<limit if improved else stats['OWN']['mean']<=limit,(op,label,stats)
        print(op,label,{k:round(v['mean'],3) for k,v in stats.items()},flush=True)
        groups.append({'operation':op,'stream':label,'stats':stats,'cases':rows})
    qualification={}
    if a.qualification:
        from m4_math_oracle import qualify
        qualification=qualify(machines['OWN'],a.samples)
    assert hashes=={k:hashlib.sha256(v.read_bytes()).hexdigest() for k,v in paths.items()}
    report={'status':'PASS','elf_sha256':hashes,'groups':groups,'qualification':qualification,
        'abi':'Cortex-M4 hard-float; R4-R11/D8-D15/SP preserved; bounded stack writes only.',
        'entry':'production public math service' if a.resident else 'standalone public operation dispatcher',
        'method':'Executed ARM instructions, including the same public operation dispatcher. No hardware/ROM arithmetic is mocked. This is not a hardware cycle/time measurement.',
        'unchanged_functions_gate':'asin/acos/sqrt/pow results bitwise identical to baseline; mean instruction drift limited to eight instructions for LTO/dispatcher layout. Optimized functions must improve strictly on every stream.',
        'require_improvement':a.require_improvement}
    a.json.parent.mkdir(parents=True,exist_ok=True)
    a.json.write_text(json.dumps(report,indent=2)+'\n')

if __name__=='__main__':main()

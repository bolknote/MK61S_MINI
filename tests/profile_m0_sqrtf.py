#!/usr/bin/env python3
"""Exact ARM sqrtf qualification and instruction comparison with external Qfplib.

--exhaustive-normalized executes all 2^24 binary32 inputs in [1,4),
covering every significand and both exponent parities of the normal kernel.
Guest memory protection allows writes only to the bounded test stack.
"""
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
import time
from native_eabi_m0_arm_self_test import Machine, SP
from check_stm32_vectors import ElfImage
from unicorn import UC_PROT_READ, UC_PROT_WRITE, UC_PROT_EXEC

ROOT=Path(__file__).resolve().parents[1]


def reference(a):
    """Exact integer oracle: square inequalities decide the rounded root."""
    magnitude=a&0x7FFFFFFF
    if magnitude>0x7F800000:return a|0x400000
    if not magnitude:return a
    if a>>31:return 0x7FC00000
    if magnitude==0x7F800000:return a
    exponent=(a>>23)-127;significand=(a&0x7FFFFF)|0x800000
    if a<0x800000:
        shift=24-a.bit_length();significand=a<<shift;exponent=-126-shift
    radicand=significand<<(23+(exponent&1))
    root=math.isqrt(radicand)
    root+=radicand-root*root>root
    out=exponent//2+127
    if root==1<<24:root>>=1;out+=1
    return (out<<23)|(root&0x7FFFFF)


def corpus():
    rng=random.Random(0x61409A9)
    legacy=[]
    for i in range(32):
        a=(rng.randrange(123,134)<<23)|rng.getrandbits(23)
        rng.randrange(123,134);rng.getrandbits(23)
        legacy.append(a)
    rng=random.Random(0x5A7F6140)
    groups={'legacy_32':legacy,
        'normal_exponents':[(rng.randrange(1,255)<<23)|rng.getrandbits(23) for _ in range(256)],
        'double_seed_range':[0x3F800000+rng.randrange(1<<24) for _ in range(256)]}
    edges=[]
    for exponent in (1,2,126,127,128,129,253,254):
        for fraction in range(0,1<<23,1<<17):
            for delta in (-1,0,1):
                a=(exponent<<23)+fraction+delta
                if 0x800000<=a<0x7F800000:edges.append(a)
    groups['segment_edges']=edges
    midpoints=[]
    for _ in range(128):
        root=(1<<23)|rng.getrandbits(23)
        numerator=(2*root+1)**2;odd=int(numerator>=1<<49)
        shift=25+odd;sig,tail=divmod(numerator,1<<shift)
        sig+=tail>1<<(shift-1) or (tail==1<<(shift-1) and sig&1)
        a=((127+odd)<<23)+sig-(1<<23)
        midpoints.extend((a-1,a,a+1))
    groups['rounding_midpoints']=midpoints
    groups['ieee_specials']=[0,0x80000000,1,2,3,0x100,0x10000,0x3FFFFF,0x7FFFFF,
        0x80000001,0x807FFFFF,0xBF800000,0xFF7FFFFF,0x7F800000,0xFF800000,
        0x7F800001,0x7FC12345,0xFF800001,0xFFC12345]
    return groups


def exhaustive(path,directory,toolchain,subnormals=False):
    sys.path.insert(0,str(ROOT/'tools'));from build_picocalc import compiler_bin
    directory.mkdir(parents=True,exist_ok=True)
    source=directory/'sqrt-block.c';target=directory/'sqrt-block.elf'
    source.write_text('''#include <stdint.h>
extern float mk61_m0_sqrtf(float);
uint32_t check_sqrt_block(uint32_t first,const uint32_t* expected,uint32_t count) {
 for(uint32_t i=0;i<count;++i) {
  union {uint32_t u;float f;} a,r;a.u=first+i;r.f=mk61_m0_sqrtf(a.f);
  if(r.u!=expected[i])return i+1;
 }
 return 0;
}
''')
    compiler=compiler_bin(toolchain)/'arm-none-eabi-gcc'
    subprocess.run([str(compiler),'-mcpu=cortex-m0plus','-mthumb','-mfloat-abi=soft','-Os',
        '-fno-builtin','-nostdlib','-Wl,-Ttext=0x08180000','-Wl,-e,check_sqrt_block',
        '-Wl,--just-symbols='+str(path.resolve()),str(source),'-o',str(target)],check=True)
    machine=Machine(path,True)
    image=ElfImage(target);image.load(machine.uc)
    machine.elf.symbols['check_sqrt_block']=image.symbols['check_sqrt_block']
    # The inner loop avoids Python callbacks on every PUSH/POP. Guest memory
    # permissions enforce the same bounded-write rule instead; R4-R11/SP are
    # checked on every block by Machine.call. Separate scalar tests also
    # verify each sqrtf call's ABI, IEEE result and permitted writes.
    machine.uc.hook_del(machine.write_hook)
    for base in (0x08000000,0x10000000):
        machine.uc.mem_protect(base,0x200000,UC_PROT_READ|UC_PROT_EXEC)
    machine.uc.mem_protect(0x20000000,0x42000,UC_PROT_READ)
    machine.uc.mem_protect(SP&~0xFFF,0x1000,UC_PROT_READ|UC_PROT_WRITE)
    machine.uc.mem_protect(0xD0000000,0x1000,UC_PROT_READ)
    address=0x08100000;block=4096;digest=hashlib.sha256();begin=time.monotonic()
    ranges=[('normalized',0x3F800000,1<<24)]
    if subnormals:ranges.append(('positive_subnormals',1,(1<<23)-1))
    for name,start,total in ranges:
        for offset in range(0,total,block):
            first=start+offset;count=min(block,total-offset)
            data=struct.pack('<'+str(count)+'I',*(reference(a) for a in range(first,first+count)))
            digest.update(data);machine.uc.mem_write(address,data)
            result=machine.call('check_sqrt_block',first|(address<<32),count)[0]&0xFFFFFFFF
            assert not result,('exhaustive sqrtf mismatch',hex(first+result-1))
            if (offset+count)%(1<<20)==0 or offset+count==total:
                print('Exhaustive '+name+':',offset+count,'/',total,flush=True)
    return {'status':'PASS','actual_arm_sqrtf_calls':sum(total for _,_,total in ranges),'blocks':machine.calls,
        'ranges':[{'name':name,'first':f'{start:08X}','last':f'{start+total-1:08X}','cases':total}
            for name,start,total in ranges],
        'reference_sha256':digest.hexdigest(),'wrapper_elf_sha256':hashlib.sha256(target.read_bytes()).hexdigest(),
        'elapsed_host_seconds':time.monotonic()-begin,
        'writes':'Guest memory protection: only the bounded stack page is writable; code, data, remaining RAM and SIO are read-only.'}


def main():
    parser=argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--owned-elf',type=Path,required=True)
    parser.add_argument('--baseline-elf',type=Path)
    parser.add_argument('--qfplib-elf',type=Path)
    parser.add_argument('--exhaustive-normalized',action='store_true')
    parser.add_argument('--exhaustive-subnormal',action='store_true',help='Also check every positive subnormal, with --exhaustive-normalized')
    parser.add_argument('--toolchain',type=Path)
    parser.add_argument('--output-dir',type=Path,required=True)
    parser.add_argument('--json',type=Path,required=True)
    args=parser.parse_args();args.output_dir.mkdir(parents=True,exist_ok=True)
    if args.exhaustive_subnormal and not args.exhaustive_normalized:
        parser.error('--exhaustive-subnormal requires --exhaustive-normalized')
    paths={'OWN':args.owned_elf}
    if args.baseline_elf:paths['BASE']=args.baseline_elf
    if args.qfplib_elf:paths['QFP']=args.qfplib_elf
    machines={name:Machine(path,True) for name,path in paths.items()}
    groups=[]
    for name,inputs in corpus().items():
        rows=[];counts={key:[] for key in machines}
        for a in inputs:
            expected=reference(a);values={}
            for key,machine in machines.items():
                if key=='QFP' and not 0x800000<=a<0x7F800000:continue
                symbol='qfp_fsqrt' if key=='QFP' else 'mk61_m0_sqrtf'
                result,_,instructions=machine.call(symbol,a,width=32,count=True)
                assert result&0xFFFFFFFF==expected,(name,key,hex(a),hex(result&0xFFFFFFFF),hex(expected))
                counts[key].append(instructions);values[key]=instructions
            rows.append({'input':f'{a:08X}','result':f'{expected:08X}','instructions':values})
        stats={key:{'mean':statistics.mean(v),'min':min(v),'max':max(v),'cases':len(v)}
            for key,v in counts.items() if v}
        groups.append({'name':name,'stats':stats,'cases':rows})
        print(name,{key:round(value['mean'],3) for key,value in stats.items()},flush=True)
    # A sqrtf call must not disturb an interrupted SIO division.
    state=struct.pack('<7I',17,3,0,0,5,2,3)
    owned=machines['OWN'];owned.uc.mem_write(0xD0000060,state)
    for inputs in corpus().values():
        for a in inputs[:32]:
            owned.exact('mk61_m0_sqrtf',a,0,reference(a),32)
            assert bytes(owned.uc.mem_read(0xD0000060,len(state)))==state
    report={'status':'PASS','elf_sha256':{key:hashlib.sha256(path.read_bytes()).hexdigest() for key,path in paths.items()},
        'groups':groups,'sio_pending_state_preserved':True,
        'oracle':'Exact integer isqrt and square remainder; quiet-NaN payloads and both zero signs checked bitwise.',
        'abi':'Scalar calls verify R4-R11/SP and stack-only writes; SIO state unchanged.',
        'note':'Executed ARM instructions, not RP2040 cycles or microseconds. Qfplib comparison is restricted to positive finite normal inputs because its IEEE coverage differs.'}
    if args.exhaustive_normalized:
        report['exhaustive_normalized']=exhaustive(args.owned_elf,args.output_dir,args.toolchain,args.exhaustive_subnormal)
    args.json.write_text(json.dumps(report,indent=2)+'\n')


if __name__=='__main__':main()

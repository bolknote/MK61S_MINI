#!/usr/bin/env python3
"""Profile and qualify all remaining resident M0+ conversions, comparisons, ln and atan."""
import argparse
import hashlib
import json
import math
from pathlib import Path
import random
import statistics
import subprocess
import sys

ROOT=Path(__file__).resolve().parents[1]
p=argparse.ArgumentParser(description=__doc__)
p.add_argument('--owned-elf',type=Path,required=True)
p.add_argument('--baseline-elf',type=Path)
p.add_argument('--qfplib-source',type=Path,required=True)
p.add_argument('--output-dir',type=Path,required=True)
p.add_argument('--json',type=Path,required=True)
p.add_argument('--qualification',action='store_true')
p.add_argument('--samples',type=int,default=10000)
p.add_argument('--require-no-gaps',action='store_true')
args=p.parse_args();WORK=args.output_dir.resolve();WORK.mkdir(parents=True,exist_ok=True)
sys.path[:0]=[str(ROOT/'tests'),str(ROOT/'tools')]
from native_eabi_m0_arm_self_test import Machine,bits,real,f_bits,f_real
from build_picocalc import compiler_bin

def sha(path):return hashlib.sha256(path.read_bytes()).hexdigest()
own_path=args.owned_elf.resolve()
qfp_source=args.qfplib_source.resolve()
metadata={'assembly_sha256':sha(qfp_source)}

# Match the boolean EABI comparison interface and unary atan interface by
# executing actual Thumb-1 adapters. Their instructions are included.
assembly=['.syntax unified','.cpu cortex-m0plus','.thumb','.text']
for op,condition in [('eq','eq'),('lt','lt'),('le','le'),('ge','ge'),('gt','gt')]:
    name='audit_dcmp'+op
    assembly += [f'.global {name}',f'.type {name},%function','.thumb_func',name+':',
        'push {r4,lr}','bl qfp_dcmp','cmp r0,#0',f'b{condition} 1f',
        'movs r0,#0','pop {r4,pc}','1: movs r0,#1','pop {r4,pc}',f'.size {name},.-{name}']
assembly += ['.global audit_atan','.type audit_atan,%function','.thumb_func','audit_atan:',
             'push {r4,lr}','movs r2,#0','ldr r3,=0x3ff00000','bl qfp_datan2','pop {r4,pc}',
             '.size audit_atan,.-audit_atan','.ltorg','.section .note.GNU-stack,"",%progbits']
adapter=WORK/'adapters.S';adapter.write_text('\n'.join(assembly)+'\n')
tc=compiler_bin(None);flags=['-mcpu=cortex-m0plus','-mthumb','-mfloat-abi=soft','-Os']
for source,target in [(qfp_source,WORK/'qfplib.o'),(adapter,WORK/'adapters.o')]:
    subprocess.run([str(tc/'arm-none-eabi-gcc'),*flags,'-c',str(source),'-o',str(target)],check=True)
qfp_path=WORK/'reference.elf'
subprocess.run([str(tc/'arm-none-eabi-gcc'),*flags,'-nostdlib','-Wl,-Ttext=0x08000000',
                '-Wl,-e,qfp_dadd',str(WORK/'qfplib.o'),str(WORK/'adapters.o'),'-o',str(qfp_path)],check=True)
machines={'OWN':Machine(own_path,True),'QFP':Machine(qfp_path,True)}
paths={'OWN':own_path,'QFP':qfp_path}
if args.baseline_elf:
    paths['BASE']=args.baseline_elf.resolve();machines['BASE']=Machine(paths['BASE'],True)
hashes={k:sha(v) for k,v in paths.items()}
rng=random.Random(0x6140A0D1);N=512;groups=[]

def add(op,stream,own,qfp,inputs,expected,input_width=64,result_width=64,kind='float'):
    counts={k:[] for k in machines};worst={k:0 for k in machines};mismatches={k:0 for k in machines};rows=[]
    mask=(1<<result_width)-1;sign=1<<(result_width-1)
    def ordered(x):return (~x&mask) if x&sign else x|sign
    for a,b in inputs:
        reference=expected(a,b)&mask;values={}
        for key,machine in machines.items():
            got,_,count=machine.call(qfp if key=='QFP' else own,a,b,width=input_width,count=True)
            got&=mask
            error=abs(ordered(got)-ordered(reference)) if kind=='float' else int(got!=reference)
            if key!='QFP':assert error<=(4 if op in ('ln','atan') else 0),(op,stream,key,hex(a),hex(b),hex(got),hex(reference),error)
            mismatches[key]+=int(got!=reference);worst[key]=max(worst[key],error);counts[key].append(count)
            values[key]={'result':f'{got:0{result_width//4}X}','instructions':count,'ulp' if kind=='float' else 'mismatch':error}
        rows.append({'a':f'{a:016X}','b':f'{b:016X}','reference':f'{reference:0{result_width//4}X}','implementations':values})
    stats={k:{'mean':statistics.mean(v),'min':min(v),'max':max(v),
              'worst_ulp' if kind=='float' else 'mismatches':worst[k] if kind=='float' else mismatches[k]} for k,v in counts.items()}
    outside=sum(abs(real(a))>1024 for a,b in inputs) if op=='atan' else 0
    comparable=(kind=='float' or not mismatches['QFP']) and not outside
    ratio=stats['OWN']['mean']/stats['QFP']['mean']
    groups.append({'operation':op,'stream':stream,'own_symbol':own,'qfplib_symbol':qfp,
        'input_width':input_width,'result_width':result_width,'same_operation_on_this_domain':comparable,
        'qfplib_outside_documented_domain':outside,
        'cases':rows,'stats':stats,'own_over_qfplib_instructions':ratio})
    if args.require_no_gaps and comparable:assert stats['OWN']['mean']<=stats['QFP']['mean'],(op,stream,stats)
    print(op,stream,{k:round(v['mean'],3) for k,v in stats.items()},'ratio',round(ratio,3),'error',worst,flush=True)

u32=[rng.getrandbits(32) for _ in range(N)]
i64=[rng.getrandbits(64) for _ in range(N)];u64=[rng.getrandbits(64) for _ in range(N)]
for name,own,qfp,inputs,width,signed in [('i2d','i2d','int2double',u32,32,True),('ui2d','ui2d','uint2double',u32,32,False),
    ('l2d','l2d','int642double',i64,64,True),('ul2d','ul2d','uint642double',u64,64,False)]:
    add(name,'random','__aeabi_'+own,'qfp_'+qfp,[(a,0) for a in inputs],
        lambda a,b,w=width,s=signed:bits(float(a-(1<<w) if s and a>>(w-1) else a)),input_width=width)

edge_rng=random.Random(0x61406464)
for name,qfp,signed in [('l2d','int642double',True),('ul2d','uint642double',False)]:
    short=[edge_rng.getrandbits(32) for _ in range(N)]
    if signed:short=[a-(1<<32) if a>>31 else a for a in short]
    sparse=[edge_rng.randrange(1<<n,1<<(n+1)) for n in range(64) for _ in range(8)]
    if signed:sparse=[a*(-1 if edge_rng.getrandbits(1) else 1) for a in sparse]
    for stream,values in [('small_magnitudes',short),('all_bit_lengths',sparse)]:
        add(name,stream,'__aeabi_'+name,'qfp_'+qfp,[(a&((1<<64)-1),0) for a in values],
            lambda a,b,s=signed:bits(float(a-(1<<64) if s and a>>63 else a)))

for op,qfp,limit,rw in [('d2iz','double2int',31,32),('d2uiz','double2uint',32,32),
                       ('d2lz','double2int64',63,64),('d2ulz','double2uint64',64,64)]:
    samples=[bits(math.ldexp(1+rng.random(),rng.randrange(-30,limit))) for _ in range(N)]
    add(op,'nonnegative_valid','__aeabi_'+op,'qfp_'+qfp,[(a,0) for a in samples],
        lambda a,b:int(real(a)),result_width=rw,kind='integer')
    if op in ('d2iz','d2lz'):
        samples=[bits(float(rng.randrange(-(1<<(limit-1)),1<<(limit-1)))) for _ in range(N)]
        add(op,'signed_integral','__aeabi_'+op,'qfp_'+qfp,[(a,0) for a in samples],
            lambda a,b:int(real(a)),result_width=rw,kind='integer')

floats=[(rng.getrandbits(1)<<31)|(rng.randrange(1,255)<<23)|rng.getrandbits(23) for _ in range(N)]
add('f2d','normal','__aeabi_f2d','qfp_float2double',[(a,0) for a in floats],lambda a,b:bits(f_real(a)),input_width=32)
doubles=[(rng.getrandbits(1)<<63)|((rng.randrange(-126,127)+1023)<<52)|rng.getrandbits(52) for _ in range(N)]
add('d2f','normal','__aeabi_d2f','qfp_double2float',[(a,0) for a in doubles],lambda a,b:f_bits(real(a)),result_width=32)

pairs=[(bits(rng.uniform(-100,100)),bits(rng.uniform(-100,100))) for _ in range(N)]
pairs[::4]=[(a,a) for a,b in pairs[::4]]
for op,test in [('eq',lambda a,b:a==b),('lt',lambda a,b:a<b),('le',lambda a,b:a<=b),
                ('ge',lambda a,b:a>=b),('gt',lambda a,b:a>b)]:
    add('dcmp'+op,'normal','__aeabi_dcmp'+op,'audit_dcmp'+op,pairs,
        lambda a,b,t=test:int(t(real(a),real(b))),result_width=32,kind='integer')

for stream,inputs in [('normal_exponents',[(rng.randrange(123,1924)<<52)|rng.getrandbits(52) for _ in range(N)]),
                      ('normalized',[bits(rng.uniform(.5,2.)) for _ in range(N)]),
                      ('near_one',[bits(1.)+i for i in range(-N//2,N//2)]),
                      ('near_one_interval',[bits(rng.uniform(63/64,65/64)) for _ in range(N)])]:
    add('ln',stream,'_ZN12compact_math2lnEd','qfp_dln',[(a,0) for a in inputs],lambda a,b:bits(math.log(real(a))))
for stream,inputs in [('ordinary',[bits(rng.uniform(-32,32)) for _ in range(N)]),
                      ('reduced',[bits(rng.uniform(-1,1)) for _ in range(N)]),
                      ('normal_exponents',[(rng.getrandbits(1)<<63)|(rng.randrange(123,1924)<<52)|rng.getrandbits(52) for _ in range(N)])]:
    add('atan',stream,'_ZN12compact_math4atanEd','audit_atan',[(a,0) for a in inputs],lambda a,b:bits(math.atan(real(a))))

qualification={}
if args.qualification:
    from m0_remaining_oracle import qualify
    qualification=qualify(machines['OWN'],args.samples)
assert hashes=={k:sha(v) for k,v in paths.items()}
report={'status':'PASS','elf_sha256':hashes,'qfplib_source':metadata,'seed':'0x6140A0D1','groups':groups,
    'qualification':qualification,'no_instruction_gaps':args.require_no_gaps,
    'notes':['Executed ARM instructions, not RP2040 cycles; the accepted Machine harness models ROM CLZ/memory intrinsics.',
        'Integer speed comparisons use common finite ranges: nonnegative fractional values or signed integral values. Qfplib rounds negative fractions toward -infinity; EABI truncates toward zero.',
        'Thumb-1 adapters for boolean comparisons and atan(x)=atan2(x,1) execute in the reference ELF; their overhead is included.',
        'Atan outside the documented Qfplib trig range ±1024 is diagnostic only.',
        'Qfplib has no direct asin, acos, log10 or pow equivalents. Resident float arithmetic is absent; float/double conversions remain.'],
    'adapter_source':adapter.read_text(),'profile_script_sha256':sha(Path(__file__))}
args.json.parent.mkdir(parents=True,exist_ok=True)
args.json.write_text(json.dumps(report,indent=2)+'\n')
print('WROTE',args.json,flush=True)

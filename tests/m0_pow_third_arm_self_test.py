#!/usr/bin/env python3
"""Prove the quotient bound and check the actual ARM pow cube division."""
import argparse
from pathlib import Path
from fractions import Fraction as F
import hashlib,json,random,subprocess,sys
root=Path(__file__).resolve().parents[1]
from native_eabi_m0_arm_self_test import Machine

parser=argparse.ArgumentParser(description=__doc__)
parser.add_argument('--toolchain',type=Path,required=True)
parser.add_argument('--output-dir',type=Path,default=root/'.build/m0-pow-third-test')
parser.add_argument('--samples',type=int,default=100000)
parser.add_argument('--source-root',type=Path,default=root)
parser.add_argument('--json',type=Path,required=True)
args=parser.parse_args();assert args.samples>=0
args.source_root=args.source_root.resolve()
work=args.output_dir.resolve();work.mkdir(parents=True,exist_ok=True)
helper=args.source_root/'code/native_eabi_m0_pow_third.inc'
has_linear='pow_exp_linear32' in helper.read_text()
# q is a lower approximation to n/3. The accumulated floor loss implies
# the exact residual is an integer in0..16; the correction is exhaustive.
c=F(1,4)+F(1,16);error=F(2)
for shift in [4,8,16]:
    c*=1+F(1,1<<shift);error=error*(1+F(1,1<<shift))+1
assert c==F((1<<32)-1,3*(1<<32))
assert 3*(error+F(1,3))<17
assert all((11*r)>>5==r//3 for r in range(17))
if has_linear:assert all((11*(r+1))>>5==(r+1)//3 for r in range(17))
wide_shiftadd='q+=q>>32' in helper.read_text()
chunked='const uint32_t top=uint32_t(a>>6)' in helper.read_text()
if chunked:
    assert all((171*t)>>9==t//3 for t in range(193))
    assert all((64*r+b+1)//3==((171*(64*r+b+1))>>9)
               for r in range(3) for b in range(64))
    third_residual=2
    third_proof='Exact32-bit quotient, residual0..2 and all192 six-bit tail pairs; rounded quotient for the complete38-bit domain.'
elif wide_shiftadd:
    c64=F(1,4)+F(1,16);loss64=F(2)
    for shift in [4,8,16,32]:
        c64*=1+F(1,1<<shift);loss64=loss64*(1+F(1,1<<shift))+1
    assert c64==F((1<<64)-1,3*(1<<64))
    assert F((1<<38)-1,1<<64)+3*loss64<20
    assert all((11*(r+1))>>5==(r+1)//3 for r in range(20))
    third_residual=19
    third_proof='Rational64-bit floor-loss bound gives residual0..19; exhaustive20-residual rounded correction.'
else:
    assert (63*43691)>>17==63//3
    assert all((h*43691)>>17==h//3 for h in range(64))
    third_residual=16
    third_proof='Rational32-bit floor-loss bound plus exhaustive17-residual correction and64-high-word division.'
# The existing residual/cube certificate bounds the argument of the new
# specialization. Keep the bound stricter than its six-bit high word.
h=F(1,2049)+(F(9,2)+F(1,1<<14)+2)/F(1<<70)
z=(1<<70)*h*h+1+F(1,1<<16)
assert (1<<70)*h<1<<59 and z<1<<48
assert ((1<<70)*h*z)/(1<<70)+F(35,64)<1<<38

def extract(path,signature):
    source=path.read_text();begin=source.index(signature);brace=source.index('{',begin);depth=1;end=brace+1
    while depth:
        depth+=(source[end]=='{')-(source[end]=='}');end+=1
    return source[begin:end]

wide=extract(args.source_root/'code/native_eabi_m0.cpp','__attribute__((always_inline)) inline U wide32')
old=extract(args.source_root/'code/native_eabi_m0_kernels.inc','__attribute__((always_inline)) inline U math62_third')
source='#include <stdint.h>\nusing U=uint64_t;\n'+wide+'\n'+old+'\n'
source+='#include "'+str(helper)+'"\n'
source+='extern "C" U test_new(U a) {return pow_log_third70(a);}\n'
source+='extern "C" U test_old(U a) {return math62_third(a);}\n'
source+='extern "C" uint32_t test_divide(uint32_t a) {return pow_divide3(a);}\n'
if has_linear:source+='extern "C" uint32_t test_linear(uint32_t a) {return pow_exp_linear32(a); }\n'
(work/'third-test.cpp').write_text(source)
compiler=args.toolchain
elf=work/'third-test.elf'
subprocess.run([str(compiler/'arm-none-eabi-g++'),'-mcpu=cortex-m0plus','-mthumb','-mfloat-abi=soft','-Os','-std=c++17','-fno-builtin','-fno-exceptions','-fno-rtti','-nostdlib','-Wl,-Ttext=0x08000000','-Wl,-e,test_new',str(work/'third-test.cpp'),'-o',str(elf)],check=True)
assert not subprocess.check_output([str(compiler/'arm-none-eabi-nm'),'-u',str(elf)])
machine=Machine(elf,True);rng=random.Random(0x2803)
edges={0,(1<<32)-1}
for bit in range(32):edges.update(x for x in [(1<<bit)-1,1<<bit,(1<<bit)+1] if x<1<<32)
for value in list(sorted(edges))+[rng.getrandbits(32) for _ in range(args.samples)]:
    assert machine.call('test_divide',value)[0]&0xffffffff==value//3,value
    if has_linear:assert machine.call('test_linear',value)[0]&0xffffffff==(2*value+1)//3,value
arguments=[(high<<32)|low for high in range(64) for low in sorted(edges)]
arguments += [rng.getrandbits(38) for _ in range(args.samples)]
digest=hashlib.sha256()
for value in arguments:
    got=machine.call('test_new',value)[0]
    assert got==(value+1)//3,(value,got,(value+1)//3)
    digest.update(value.to_bytes(8,'little')+got.to_bytes(8,'little'))
samples=[0,1,2,0xfffffffe,0xffffffff,(1<<37)-1,(1<<38)-1]
counts=[]
for value in samples:
    a=machine.call('test_new',value,count=True);b=machine.call('test_old',value,count=True)
    assert a[0]==b[0]
    counts.append(dict(argument=value,new_instructions=a[2],old_instructions=b[2]))
report=dict(status='PASS',standalone_elf_sha256=hashlib.sha256(elf.read_bytes()).hexdigest(),
    helper_sha256=hashlib.sha256(helper.read_bytes()).hexdigest(),
    exact_divide32_calls=args.samples+len(edges),exact_round_third38_calls=len(arguments),
    exact_linear32_calls=(args.samples+len(edges)) if has_linear else 0,
    max_shiftadd_residual=16,round_third_residual_bound=third_residual,rounding='Exact floor((n+1)/3), equal to RNE of n/3.',
    proof=third_proof+' Existing log70 rational enclosure certifies <2^38 input.',
    arm_abi='R4-R11,SP and bounded stack writes verified by every call.',sample_instructions=counts,reference_symbol='generic math62_third, not previous split specialization',result_sha256=digest.hexdigest())
args.json.parent.mkdir(parents=True,exist_ok=True)
args.json.write_text(json.dumps(report,indent=2)+'\n')
print(json.dumps(report,indent=2),flush=True)

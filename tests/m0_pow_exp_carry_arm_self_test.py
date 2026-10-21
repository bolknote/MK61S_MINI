#!/usr/bin/env python3
"""Verify pow exp high-product accuracy, including the merged cross carry."""
from pathlib import Path
from fractions import Fraction
import argparse,hashlib,json,random,subprocess,sys
root=Path(__file__).resolve().parents[1];sys.path[:0]=[str(root/'tests'),str(root/'tools')]
from native_eabi_m0_arm_self_test import Machine
from build_picocalc import compiler_bin
parser=argparse.ArgumentParser(description='Check the actual pow compensated high-product block on ARM against exact integers.')
parser.add_argument('--source-root',type=Path,default=root)
parser.add_argument('--toolchain')
parser.add_argument('--output-dir',type=Path,default=root/'.build/m0-pow-exp-carry-arm')
parser.add_argument('--samples',type=int,default=100000)
parser.add_argument('--json',type=Path,required=True)
args=parser.parse_args();assert args.samples>=0
args.source_root=args.source_root.resolve()
w=args.output_dir.resolve();w.mkdir(parents=True,exist_ok=True)
source=(args.source_root/'code/native_eabi_m0_pow_fast.inc').read_text()
def extract(text,signature):
 a=text.index(signature);b=text.index('{',a);n=1;c=b+1
 while n:n+=(text[c]=='{')-(text[c]=='}');c+=1
 return text[a:c]
common=(args.source_root/'code/native_eabi_m0.cpp').read_text();wide=extract(common,'__attribute__((always_inline)) inline U wide32');old=extract(common,'__attribute__((always_inline)) inline U exp_high_product')
a=source.index('  const U d=below?U(0)-delta:delta;',source.index('pow_exp_argument:'));b=source.index('  q=below?',a);block=source[a:b]
assembly_product='mk61_m0_pow_exp_product(q,d)' in block
text='#include <stdint.h>\nusing U=uint64_t;\n'+wide+'\n'+old+'\n'
if assembly_product:text+='extern "C" U mk61_m0_pow_exp_product(U,U);\n'
text+='extern "C" U test_new(U q,U delta) {const bool below=bool(delta>>63);\n'+block+'return correction;}\n'
text+='extern "C" U test_old(U q,U d) {return exp_high_product(q,d)+1;}\n'
(w/'product-test.cpp').write_text(text);compiler=compiler_bin(args.toolchain);elf=w/'product-test.elf'
extra=[]
if assembly_product:
    (w/'product.S').write_text('#include "'+str(args.source_root/'code/native_eabi_m0_pow_exp_product.inc')+'"\n')
    extra=['-DMK61_USE_M0_EABI=1','-DMK61_M0_RP2040_EABI=1',str(w/'product.S')]
subprocess.run([str(compiler/'arm-none-eabi-g++'),'-mcpu=cortex-m0plus','-mthumb','-mfloat-abi=soft','-Os','-std=c++17','-fno-builtin','-fno-exceptions','-fno-rtti','-nostdlib','-Wl,-Ttext=0x08000000','-Wl,-e,test_new',str(w/'product-test.cpp'),*extra,'-o',str(elf)],check=True)
assert not subprocess.check_output([str(compiler/'arm-none-eabi-nm'),'-u',str(elf)])
assert ((1<<32)-1)*((1<<22)-1)+((1<<31)-1)*((1<<32)-1)<1<<64
assert 12912720851596686+(1<<43)+(1<<31)<1<<54
# True high product minus the uncorrected estimate is the sum of the
# merged cross fraction and omitted low product, each in[0,1). Adding1
# therefore has absolute error<=1, including exactzero ->1.
m=Machine(elf,True);rng=random.Random(0x380164);S=1<<64
bound=Fraction(1,2)+Fraction(1,1<<15) if assembly_product else Fraction(1)
strict=Machine(elf,True,stack_bytes=32) if assembly_product else None
if assembly_product:
    limb=(1<<16)-1
    assert limb*limb*(1+2*(1<<16))<1<<49
    assert 3+4*(limb*limb>>16)+4<1<<18
    assert (1<<18)+limb*63<1<<32
    assert (limb*63>>16)+(32767*limb>>16)+6<1<<16
as_={0,1,(1<<62),(1<<63)-1};bs_={0,1,(1<<54)-1}
for bit in range(63):as_.update(x for x in [(1<<bit)-1,1<<bit,(1<<bit)+1] if 0<=x<1<<63)
for bit in range(54):bs_.update(x for x in [(1<<bit)-1,1<<bit,(1<<bit)+1] if 0<=x<1<<54)
pairs=[(a,b) for a in sorted(as_) for b in sorted(bs_)]
pairs +=[(rng.randrange(1<<62,1<<63),rng.getrandbits(54)) for _ in range(args.samples)]
digest=hashlib.sha256();largest=0
for i,(a,b) in enumerate(pairs):
 delta=((0-b)&(S-1)) if i&1 else b
 got=m.call('test_new',a,delta)[0];err=abs(got*S-a*b);assert err<=bound*S,(a,b,got,err)
 if assembly_product:
  omitted=(a&65535)*(b&65535)+(((a&65535)*((b>>16)&65535)+((a>>16)&65535)*(b&65535))<<16)
  assert got==(a*b-omitted+(1<<63))>>64
  assert strict.call('mk61_m0_pow_exp_product',a,b)[0]==got
 largest=max(largest,err);digest.update(a.to_bytes(8,'little')+b.to_bytes(8,'little')+got.to_bytes(8,'little'))
samples=[]
for a,b in [(0,0),(1<<62,0),((1<<63)-1,1<<53),( (1<<63)-1,(1<<54)-1)]:
 samples.append(dict(a=a,b=b,new_instructions=m.call('test_new',a,b,count=True)[2],old_instructions=m.call('test_old',a,b,count=True)[2]))
proof=('Thirteen retained16-bit products; omitted sum<2^49, rounded at bit63. Exact integer equality and column carry bounds.' if assembly_product else 'Two omitted fractions in[0,1), compensated by+1.')
report=dict(status='PASS',calls=len(pairs),elf_sha256=hashlib.sha256(elf.read_bytes()).hexdigest(),pow_source_sha256=hashlib.sha256(source.encode()).hexdigest(),bound_high64_units=float(bound),bound_exact=str(bound),largest_sample_error_numerator=largest,error_denominator=S,domain='a<2^63, abs(delta)<2^54; complete cross sum fits64bits.',proof=proof+' Actual source block compiled for ARM and checked against exact Python products.',abi='Every call checks R4-R11, SP and bounded stack writes.'+(' Product additionally has a strict32-byte frame.' if assembly_product else ''),samples=samples,digest_sha256=digest.hexdigest())
args.json.parent.mkdir(parents=True,exist_ok=True)
args.json.write_text(json.dumps(report,indent=2)+'\n');print(json.dumps(report,indent=2),flush=True)

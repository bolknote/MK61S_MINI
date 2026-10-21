#!/usr/bin/env python3
"""Check pow tail approximations against exact products and their global error bounds."""
from pathlib import Path
from fractions import Fraction as F
import argparse,hashlib,itertools,json,random,subprocess,sys
root=Path(__file__).resolve().parents[1];sys.path[:0]=[str(root/'tests'),str(root/'tools')]
from native_eabi_m0_arm_self_test import Machine
from build_picocalc import compiler_bin
parser=argparse.ArgumentParser(description='Certify and execute the compact normal-pow log tail on ARM.')
parser.add_argument('--source-root',type=Path,default=root)
parser.add_argument('--toolchain')
parser.add_argument('--output-dir',type=Path,default=root/'.build/m0-pow-tail-arm')
parser.add_argument('--samples',type=int,default=100000)
parser.add_argument('--json',type=Path,required=True)
args=parser.parse_args();assert args.samples>=0
args.source_root=args.source_root.resolve()
w=args.output_dir.resolve();w.mkdir(parents=True,exist_ok=True)
# Domain already certified for the unchanged residual/cube producer.
h=F(1,2049)+(F(9,2)+F(1,1<<14)+2)/F(1<<70)
z=(1<<70)*h*h+1+F(1,1<<16);cube_bound=h*z+F(35,64)
assert cube_bound<1<<37
# p approximates floor(a*b/2^32) by0,-1 or-2: its discarded fractions
# sum to[0,3). +1 therefore changes that integer by at most1; >>5
# preserves the one-unit bound against the old fourth floor.
M=(1<<16)-1
assert M*M+2*((M*M)>>16)+1<1<<32
# New fourth <=floor((2^31-1)*(2^32-1)/2^37)+1 <=2^26.
assert (((1<<31)-1)*((1<<32)-1)>>37)+1<1<<27
# For A<2^27,B<2^32, discard12/17 bits before multiplying. The
# omitted real contribution is strictly below4; the last floor loses <1.
# Adding2 gives a real difference in[-2,3), hence integer difference<=2.
assert F((1<<12)*(1<<32),1<<43)+F((1<<27)*(1<<17),1<<43)==4
assert ((1<<15)-1)**2<1<<32
# A one-unit fourth difference moves the old fifth floor by at most1.
# Thus the fifth integers differ by<=3; its coefficient changes by<=1.
assert F(1<<32,1<<43)<1
assert 3*52429<1<<18
assert ((1<<16)+3)*52429<1<<32
# The fourth/4 integer changes by<=1 as well: total log change<=2.
sys.path.insert(0,str(args.source_root/'tools'));from generate_m0_log70_table import certificate
old_bound=F(certificate()['main_error']);assert old_bound+2<16

common=(args.source_root/'code/native_eabi_m0.cpp').read_text()
def extract(text,signature):
 a=text.index(signature);b=text.index('{',a);n=1;c=b+1
 while n:n+=(text[c]=='{')-(text[c]=='}');c+=1
 return text[a:c]
wide=extract(common,'__attribute__((always_inline)) inline U wide32')
text='#include <stdint.h>\nusing U=uint64_t;\n'+wide+'\n'
text+='#include "'+str(args.source_root/'code/native_eabi_m0_pow_tail.inc')+'"\n'
text+='extern "C" U test_new(U cube,U raw) {const uint32_t t=uint32_t(raw),f=pow_log_fourth70(cube,t),g=pow_log_fifth70(f,t);return (U(f)<<32)|g;}\n'
text+='extern "C" U test_old(U cube,U raw) {const uint32_t t=uint32_t(raw),f=uint32_t(wide32(uint32_t(cube>>6),t)>>37),g=uint32_t(wide32(f,t)>>43);return (U(f)<<32)|g;}\n'
(w/'tail-test.cpp').write_text(text);compiler=compiler_bin(args.toolchain);elf=w/'tail-test.elf'
subprocess.run([str(compiler/'arm-none-eabi-g++'),'-mcpu=cortex-m0plus','-mthumb','-mfloat-abi=soft','-Os','-std=c++17','-fno-builtin','-fno-exceptions','-fno-rtti','-nostdlib','-Wl,-Ttext=0x08000000','-Wl,-e,test_new',str(w/'tail-test.cpp'),'-o',str(elf)],check=True)
assert not subprocess.check_output([str(compiler/'arm-none-eabi-nm'),'-u',str(elf)])
cs={0,1,(1<<37)-1};ts={0,1,(1<<32)-1}
for bit in range(37):cs.update(v for v in [(1<<bit)-1,1<<bit,(1<<bit)+1] if 0<=v<1<<37)
for bit in range(32):ts.update(v for v in [(1<<bit)-1,1<<bit,(1<<bit)+1] if 0<=v<1<<32)
rng=random.Random(0x4270);pairs=list(itertools.product(sorted(cs),sorted(ts)))+[(rng.getrandbits(37),rng.getrandbits(32)) for _ in range(args.samples)]
m=Machine(elf,True);digest=hashlib.sha256();maxf=maxg=maxtotal=0
for cube,t in pairs:
 packed=m.call('test_new',cube,t)[0];f=packed>>32;g=packed&0xffffffff
 f0=((cube>>6)*t)>>37;g0=(f0*t)>>43
 assert abs(f-f0)<=1,(cube,t,f,f0)
 assert abs(g-((f*t)>>43))<=2,(cube,t,g,(f*t)>>43)
 assert abs(g-g0)<=3,(cube,t,g,g0)
 df=((f+2)>>2)-((f0+2)>>2);dg=(((g+2)*52429)>>18)-(((g0+2)*52429)>>18)
 assert abs(df)<=1 and abs(dg)<=1
 maxf=max(maxf,abs(f-f0));maxg=max(maxg,abs(g-g0));maxtotal=max(maxtotal,abs(df)+abs(dg))
 digest.update(cube.to_bytes(8,'little')+t.to_bytes(4,'little')+packed.to_bytes(8,'little'))
samples=[]
for cube,t in [(0,0),((1<<36)-1,0x12345678),((1<<37)-1,0xffffffff)]:
 samples.append(dict(cube=cube,t=t,new_instructions=m.call('test_new',cube,t,count=True)[2],old_instructions=m.call('test_old',cube,t,count=True)[2]))
report=dict(status='PASS',cases=len(pairs),elf_sha256=hashlib.sha256(elf.read_bytes()).hexdigest(),helper_sha256=hashlib.sha256((args.source_root/'code/native_eabi_m0_pow_tail.inc').read_bytes()).hexdigest(),old_log_error=str(old_bound),new_log_error_bound=str(old_bound+2),new_log_error_bound_float=float(old_bound+2),unchanged_log_guard=16,extra_q70_error_bound=2,observed_maximum_fourth_difference=maxf,observed_maximum_fifth_difference=maxg,observed_total_rounded_term_change=maxtotal,samples=samples,digest_sha256=digest.hexdigest(),proof='Exact rational domain and global integer floor bounds; actual ARM helper against arbitrary-precision old products. R4-R11, SP and stack writes checked on every call.',scope='Pow normal logarithm only. Public ln/log10 and all lookup tables unchanged; no universal fallback totality claim.')
args.json.parent.mkdir(parents=True,exist_ok=True)
args.json.write_text(json.dumps(report,indent=2)+'\n');print(json.dumps(report,indent=2),flush=True)

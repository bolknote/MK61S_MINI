from pathlib import Path
import hashlib,json,struct,sys
sys.dont_write_bytecode=True
W=Path(__file__).resolve().parent;ROOT=W.parents[1]
P=ROOT/'.build/m0-asin-scaled-bound-v164-20261023'
B=ROOT/'.build/m0-exp-cached-product-20261024'
S=ROOT/'.build/m0-pow-square-ordinary-20261024'
Q=ROOT/'.build/m0-float-fma-qualification-20261023'
sys.path[:0]=[str(Q),str(Q/'support'),str(ROOT/'tests')]
from native_eabi_m0_arm_self_test import Machine,SP
from check_stm32_vectors import ElfImage
from m0_mpfr_oracle import Oracle,bits
from oracles import equal
from unicorn import UC_HOOK_CODE
from unicorn.arm_const import UC_ARM_REG_R0,UC_ARM_REG_R1
sha=lambda p:hashlib.sha256(p.read_bytes()).hexdigest()
base=P/'firmware/mk61s-picocalc-pico-h.elf'
rom=ROOT/'research/rp2040-memset-2026-10-21/capture/bootrom.bin'
ref=ROOT/'.build/m0-v138-execution-20261023/reference/reference.elf'
build=json.loads((W/'build.json').read_text())
resident=ElfImage(base)
table_address=resident.symbols['factor_rsqrt_seeds']
section=next(s for s in resident.named_sections.values() if s[3]<=table_address<s[3]+s[5])
seed_bytes=resident.bytes_at(section)[table_address-section[3]:table_address-section[3]+2048]
seeds=struct.unpack('<512I',seed_bytes)
states={'READY':struct.pack('<7I',0,0,0,0,0,0,1),'DIRTY':struct.pack('<7I',17,3,17,3,5,2,3)}
def machine(label):
 if label=='Qfplib':return Machine(ref,True)
 m=Machine(base,True,bootrom=rom)
 ElfImage(B/'candidate.elf').load(m.uc)
 ElfImage(S/'candidate.elf').load(m.uc)
 if label in ('control','candidate'):
  path=W/(label+'.elf');assert sha(path)==build['images'][label]['ELF_sha256']
  im=ElfImage(path);im.load(m.uc)
  m.elf.symbols.update({n:a for n,a in im.symbols.items() if n.startswith('mk61_m0_pow_')})
 return m
def point(x):
 exponent=x>>52;e=exponent-1023;p=e&1;m=(x&((1<<52)-1))|(1<<52)
 index=(m&((1<<52)-1))>>44;d=513+2*index;base=seeds[p*256+index]
 distance=abs(m-(d<<43));n=(distance-1)>>11 if distance else 0
 t=n//d;z32=t*t>>32;quadratic=(3*z32+4)>>3;cube=(z32*(t>>16))>>16;cubic=(5*cube+8)>>4
 negative=m<(d<<43)
 delta=(t if negative else -t)+2*quadratic+(2*cubic if negative else -2*cubic)
 correction=(base*abs(delta)+(1<<32))>>33
 seed=base-correction if delta<0 else min(0xffffffff,base+correction)
 a=m<<(10+p);b=seed*seed
 product=(a>>32)*(b>>32)+((a&0xffffffff)*(b>>32)>>32)+((a>>32)*(b&0xffffffff)>>32)
 factor=(3<<62)-product;q=factor*seed>>32
 return {'q':q,'factor':factor,'seed':seed,'n':n,'d':d,'base':base,'parity':p,'t':t}
def hook_point(m):
 captured=[];a=m.elf.symbols['mk61_m0_pow_rsqrt_point']&~1
 def hook(uc,*unused):captured.append(uc.reg_read(UC_ARM_REG_R0)|(uc.reg_read(UC_ARM_REG_R1)<<32))
 m.uc.hook_add(UC_HOOK_CODE,hook,begin=a,end=a)
 return captured

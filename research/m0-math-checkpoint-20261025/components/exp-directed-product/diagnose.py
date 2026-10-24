from pathlib import Path
import json,struct,sys
sys.dont_write_bytecode=True
ROOT=Path.cwd();W=Path(sys.argv[1]);Q=ROOT/'.build/m0-float-fma-qualification-20261023';P=ROOT/'.build/m0-asin-scaled-bound-v164-20261023'
sys.path[:0]=[str(Q),str(Q/'support'),str(ROOT/'tests')]
from native_eabi_m0_arm_self_test import Machine
from check_stm32_vectors import ElfImage
from m0_mpfr_oracle import Oracle
from oracles import equal
m=Machine(P/'firmware/mk61s-picocalc-pico-h.elf',True,bootrom=ROOT/'research/rp2040-memset-2026-10-21/capture/bootrom.bin');im=ElfImage(W/'candidate.elf');im.load(m.uc);m.elf.symbols['xexp']=im.symbols['mk61_m0_exp']
o=Oracle()
for word in ['4085F424184F6DC5','C041265824E2113C','C0862312E96F5DF9','3FDAFC33A999FC26','3F60BF166C07292D','3DF0000000000000']:
 x=int(word,16);expected=o.reference('exp',x);out=[]
 for state in (struct.pack('<7I',0,0,0,0,0,0,1),struct.pack('<7I',17,3,17,3,5,2,3)):
  m.uc.mem_write(0xd0000060,state);got,_,cost=m.call('xexp',x,count=True);assert equal(got,expected,64);out.append(cost)
 print(word,out)

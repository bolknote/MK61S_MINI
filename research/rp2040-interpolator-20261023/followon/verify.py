#!/usr/bin/env python3
"""Bounded actual-Thumb checks, including independent POP/BASE01 and exact roots."""
from pathlib import Path
import argparse,hashlib,json,random,struct,sys
from math import isqrt
HERE=Path(__file__).resolve().parent
ROOT=HERE.parents[2]
OUT=ROOT/'.build/rp2040-interpolator-20261023/followon'
sys.path.insert(0,str(ROOT/'tests'))
from native_eabi_m0_arm_self_test import Machine,nan
from m0_mpfr_oracle import Oracle
from unicorn import UC_HOOK_MEM_READ
MASK=(1<<32)-1

def signed(v,bits=32):return v-(1<<bits) if v>>(bits-1) else v

class Model(Machine):
 def __init__(self,elf):
  super().__init__(elf,True,stack_bytes=32768)
  self.uc.hook_add(UC_HOOK_MEM_READ,self.interp_read,begin=0xd0000080,end=0xd00000ff)
 def write(self,uc,access,address,size,value,user):
  if any(section[2]&1 and section[3]<=address and address+size<=section[3]+section[5] for section in self.elf.sections):return
  if 0xd0000080<=address<0xd0000100:
   base=address&~63;off=address-base;assert size==4 and off in (0,4,8,12,16,44,48,52,56,60),(hex(address),size)
   if off in (52,56):
    target=base+off-52;old=int.from_bytes(uc.mem_read(target,4),'little');uc.mem_write(target,struct.pack('<I',(old+value)&MASK))
   elif off==60:
    c0,c1=struct.unpack('<2I',uc.mem_read(base+44,8))
    for lane in range(2):
     v=(value>>(16*lane))&65535;ctrl=c1 if c0&(1<<21) else (c0,c1)[lane]
     if ctrl&(1<<15):v=signed(v,16)&MASK
     uc.mem_write(base+8+4*lane,struct.pack('<I',v))
   return
  super().write(uc,access,address,size,value,user)
 def interp_read(self,uc,access,address,size,value,user):
  base=address&~63;off=address-base;assert size==4
  if off in (0,4,8,12,16,44,48,60):return
  assert off in (20,24,28,32,36,40,52,56),hex(address)
  raw=struct.unpack('<16I',uc.mem_read(base,64));lanes=[]
  for lane in range(2):
   ctrl=raw[11+lane];lo=(ctrl>>5)&31;hi=(ctrl>>10)&31;assert lo<=hi
   a=raw[1-lane] if ctrl&(1<<16) else raw[lane]
   v=(a>>(ctrl&31))&(((1<<(hi-lo+1))-1)<<lo)
   if ctrl&(1<<15) and v&(1<<hi):v|=MASK^((1<<(hi+1))-1)
   lanes.append(v&MASK)
  if off in (52,56):result=lanes[(off-52)//4]
  else:
   if raw[11]&(1<<21):
    a,b=raw[2:4]
    if raw[12]&(1<<15):a,b=signed(a),signed(b)
    results=(lanes[1]&255,(a+(b-a)*(lanes[1]&255)//256)&MASK,(raw[4]+lanes[0])&MASK)
   else:
    results=((raw[2]+(raw[0] if raw[11]&(1<<18) else lanes[0]))&MASK,
             (raw[3]+(raw[1] if raw[12]&(1<<18) else lanes[1]))&MASK,
             (raw[4]+lanes[0]+lanes[1])&MASK)
   result=results[((off-20)//4)%3]
   if off<32:
    for lane in range(2):uc.mem_write(base+4*lane,struct.pack('<I',results[1-lane if raw[11+lane]&(1<<17) else lane]))
  uc.mem_write(address,struct.pack('<I',result))

from exact_oracle import root_oracle

def fixtures():
 rng=random.Random(0x204002)
 edge=[0,1<<63,1,2,3,0xfffffffffffff,0x10000000000000,0x7fefffffffffffff,
       0x7ff0000000000000,0xfff0000000000000,0x7ff0000000000001,0xfff8123456789012,
       0xbff0000000000000,0x3ff0000000000000,0x4000000000000000,0x4010000000000000]
 edge+=[(e<<52)|((1<<52)-1 if e&1 else 0) for e in (1,2,3,511,512,513,1021,1022,1023,1024,1025,1535,1536,2044,2045,2046)]
 randoms=[(rng.randrange(1,2047)<<52)|rng.getrandbits(52) for _ in range(32)]
 cells=[((1023+(j&1))<<52)|((j*7%256)<<44)|((j*11%256)<<36)|((1<<36)-1 if j&2 else 0) for j in range(32)]
 return [edge,randoms,cells]

def main():
 p=argparse.ArgumentParser();p.add_argument('--samples',type=int,default=600);a=p.parse_args()
 m=Model(OUT/'kernels.elf');oracle=Oracle();rng=random.Random(0x514002);groups=fixtures()
 text='// Independent exact integer root oracles; deterministic full-function streams.\n#include <stdint.h>\n'
 for name,rows in [('fo_inputs',groups),('fo_sqrt_expected',[[root_oracle(b) for b in row] for row in groups]),('fo_rsqrt_expected',[[root_oracle(b,True) for b in row] for row in groups])]:
  text+='static const uint64_t '+name+'[3][32]={\n'+''.join(' {'+','.join('UINT64_C(0x%016x)'%v for v in row)+'},\n' for row in rows)+'};\n'
 (HERE/'vectors.h').write_text(text)
 cases=[x for row in groups for x in row]
 cases += [((1023+p)<<52)|(j<<44)|low for p in (0,1) for j in range(256) for low in (0,(1<<44)-1)]
 cases += [(rng.randrange(1,2047)<<52)|rng.getrandbits(52) for _ in range(a.samples)]
 counts={};worst_ln=0;skip_wrong={'sqrt':0,'rsqrt':0};digest=hashlib.sha256()
 m.call('fo_lookup_setup',0);m.call('fo_root_setup',0)
 for b in cases:
  for kind in ('sqrt','rsqrt'):
   expected=root_oracle(b,kind=='rsqrt')
   for suffix in ('base','new_cpu','new_interp'):
    name='fo_'+kind+'_'+suffix;got=m.call(name,b)[0]
    assert (nan(got) if nan(expected) else got==expected),(name,hex(b),hex(got),hex(expected))
    counts[name]=counts.get(name,0)+1;digest.update(struct.pack('<QQ',b,got))
   bad=m.call('fo_'+kind+'_skip_refine',b)[0]
   skip_wrong[kind]+=int(not nan(expected) and bad!=expected)
  m.call('fo_lookup_setup',0)
  left=m.call('fo_ln_cpu',b)[0];right=m.call('fo_ln_interp',b)[0]
  assert left==right,('ln',hex(b),hex(left),hex(right))
  counts['ln_pair']=counts.get('ln_pair',0)+1
  if 0<b<0x7ff0000000000000:
   expected=oracle.reference('ln',b)
   def order(x):return ((1<<64)-1)^x if x>>63 else x|(1<<63)
   worst_ln=max(worst_ln,abs(order(left)-order(expected)))
  m.call('fo_root_setup',0)
 for group in (0,1):
  for j in range(24):
   seed=rng.getrandbits(64);n=(1,2,31,32,255,256,1023,1024)[j%8]
   m.call('fo_texture_setup' if group==0 else 'fo_audio_setup',0)
   names=('fo_texture_cpu','fo_texture_pop') if group==0 else ('fo_audio_cpu','fo_audio_interp')
   outputs=[];returns=[]
   for name in names:
    returns.append(m.call(name,seed,n)[0]);outputs.append(bytes(m.uc.mem_read(m.elf.symbols['fo_output'],n*(group+1))))
   assert returns[0]==returns[1] and outputs[0]==outputs[1],(group,j,hex(seed),n)
   phase=seed&0xffffffff;v=seed>>32;expected=bytearray()
   for i in range(n):
    if not group:
     x,y=(phase>>16)&63,(v>>16)&63;expected.append(((x*13+y*29)^(x*y*3+71))&255)
     phase=(phase+(0xffff6000 if seed&1 else 0xc000))&MASK;v=(v+(0x15555 if seed&2 else 0x5555))&MASK
    else:
     index=(phase>>16)&255
     def sample(k):return ((k*977+((k*k*37)^0x5123))&65535)-32768
     aa,bb=sample(index),sample((index+1)&255);value=aa+(bb-aa)*((phase>>8)&255)//256
     expected.extend(struct.pack('<h',value));phase=(phase+((seed>>32)|1))&MASK
   assert outputs[0]==expected,('independent POP/audio oracle',group,j)
   counts['texture' if group==0 else 'audio']=counts.get('texture' if group==0 else 'audio',0)+2
 assert skip_wrong['sqrt']>0 and skip_wrong['rsqrt']>0,skip_wrong
 report=dict(status='PASS',physical_timing=False,actual_arm_calls=m.calls,cases=len(cases),checked=counts,
   seed_refinement_omission_wrong_cases=skip_wrong,ln_control_worst_ulp=worst_ln,
   ln_candidate_bit_identical=True,full_sqrt_rsqrt_correct=True,mpfr_version=oracle.version,
   digest=digest.hexdigest(),elf_sha256=hashlib.sha256((OUT/'kernels.elf').read_bytes()).hexdigest(),
   scope='Finite targeted corpus and independent exact integer/MPFR references. No all-input proof or hardware timing claim.')
 (OUT/'offline-report.json').write_text(json.dumps(report,indent=2)+'\n');print(json.dumps(report,indent=2))
if __name__=='__main__':main()

"""Model every observed near-ln loss using the actual retained product."""
from pathlib import Path
from fractions import Fraction as F
import hashlib
import json
import struct
import sys

sys.dont_write_bytecode=True
W=Path(__file__).resolve().parent
ROOT=W.parents[1]
P=ROOT/'.build/m0-asin-scaled-bound-v164-20261023'
BASE=ROOT/'.build/m0-ln-enclosure-20261024'
Q=ROOT/'.build/m0-float-fma-qualification-20261023'
sys.path.insert(0,str(Q));sys.path.insert(0,str(Q/'support'))
from native_eabi_m0_arm_self_test import Machine
from check_stm32_vectors import ElfImage
from m0_mpfr_oracle import Oracle
from oracles import round_ratio

q=json.loads((BASE/'qualification.json').read_text())
selected=sorted({int(r['x'],16) for r in q['remaining_slower_correct_Qfplib']})
elf=ElfImage(BASE/'candidate.elf')
name=next(n for n in elf.symbols if 'log_near_table' in n)
address=elf.symbols[name]
section=next(s for s in elf.named_sections.values() if s[3]<=address<s[3]+s[5])
data=elf.bytes_at(section)
start=address-section[3]
table=[struct.unpack_from('<QQ',data,start+16*i) for i in range(256)]
m=Machine(P/'firmware/mk61s-picocalc-pico-h.elf',True)
o=Oracle();records=[];calls=0
for raw in selected:
    if not 0x3fef808000000001<=raw<=0x3ff0400000000000:
        continue
    negative=raw<0x3ff0000000000000
    s=(raw&((1<<52)-1))|(1<<52)
    a=(((1<<53)-s)<<9) if negative else ((s-(1<<52))<<10)
    n=(a+(1<<48))>>49
    if not n or (negative and n==128):
        continue
    index=128-n if negative else 128+n
    R,low=table[index-1]
    center=n<<49
    delta=abs(a-center)
    small=a<center
    subtract=negative^small
    add=subtract==negative
    h=m.call('mk61_m0_log_product54',delta,R)[0] if delta else 0
    calls+=bool(delta)
    t=h>>26
    z=(t*t>>18)+(t*(h&((1<<26)-1))>>43)+1
    hr=(h+(1<<25))>>26
    zr=(z+(1<<12))>>13
    cube=(hr*zr+(1<<30))>>31
    third=(cube+1)//3
    fourth=(zr*zr+(1<<43))>>44
    even=((z+1)>>1)+((fourth+2)>>2)
    odd=h+third
    correction=odd+even if subtract else odd-even
    if not delta:correction=0
    value=low+(correction if add else -correction)
    shift=value.bit_length()-53
    half=1<<(shift-1)
    tail=value&((1<<shift)-1)
    distance=abs(tail-half)
    r2=z-2*((z+1)>>1)
    r3=cube-3*third
    r4=fourth-4*((fourth+2)>>2)
    bias=-4*r3-(1 if subtract else -1)*(6*r2+3*r4)
    upper=(tail>half)==add
    plain=(distance>=4 or (not delta and distance>=1) or
           (distance>0 and 12*distance+(-bias if upper else bias)>=(24 if upper else 27)))
    den=8192+(-n if negative else n)
    residue=(delta<<21)-h*den
    assert abs(F(residue,den))<F(69,128)
    aware=(distance>=4 or (not delta and distance>=1) or
           (distance>0 and (den*(12*distance-bias)+12*residue>=18*den if upper
                           else den*(12*distance+bias)-12*residue>=21*den)))
    got=round_ratio(value,1,-70,64,negative)
    expected=o.reference('ln',raw)
    if plain or aware:assert got==expected,(hex(raw),hex(got),hex(expected))
    records.append(dict(x=f'{raw:016X}',n=n,negative=negative,delta=delta,h=h,subtract=subtract,add=add,
        distance=distance,tail_side='above' if tail>half else 'below' if tail<half else 'midpoint',
        r2=r2,r3=r3,r4=r4,bias12=bias,upper=upper,den=den,residue=residue,
        plain_accepts=plain,residual_accepts=aware,model_correct=got==expected,
        model_bits=f'{got:016X}',expected=f'{expected:016X}'))
out=dict(status='PROSPECTIVE_NEAR_LN_MODEL_NOT_RUNTIME',records=records,near_loss_inputs=len(records),
    actual_ARM_product_calls=calls,plain_accepts=sum(r['plain_accepts'] for r in records),
    residual_accepts=sum(r['residual_accepts'] for r in records),MPFR_version=o.version,
    parent_ELF_sha256=hashlib.sha256((BASE/'candidate.elf').read_bytes()).hexdigest(),hardware_accessed=False)
(W/'model.json').write_text(json.dumps(out,indent=2)+'\n')
print(json.dumps({k:v for k,v in out.items() if k!='records'},indent=2))
print(json.dumps([{k:r[k] for k in ['x','distance','bias12','residue','plain_accepts','residual_accepts','model_correct']}
                  for r in records],indent=2))

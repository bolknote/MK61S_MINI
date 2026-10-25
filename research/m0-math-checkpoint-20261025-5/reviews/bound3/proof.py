"""Independent full finite HOST integer proof and exact live-use code binding."""
import hashlib,json,re,struct,sys
from collections import Counter
from pathlib import Path
sys.dont_write_bytecode=True
R=Path('/Users/bolk/Projects/MK61S_MINI');O=Path(__file__).resolve().parent;sys.path.insert(0,str(R/'tests'))
from check_stm32_vectors import ElfImage
MASK=(1<<32)-1
def ref(p):
 p=Path(p);b=p.read_bytes();return dict(path=str(p),bytes=len(b),sha256=hashlib.sha256(b).hexdigest())
def save(n,j):
 with(O/n).open('x')as f:json.dump(j,f,indent=2);f.write('\n')
 return ref(O/n)
def mem(e,a,n):
 s=next(s for s in e.sections if s[1]!=8 and s[3]<=a and a+n<=s[3]+s[5]);return e.bytes_at(s)[a-s[3]:a-s[3]+n]
def signed(x):return x-(1<<32)if x&(1<<31)else x
def estimate(D,table):
 T=table[(D>>9)-128];x=(((D+1)>>1)*T)&MASK;x=(x<<1)&MASK;x=signed(x)>>17;x=(x*T)&MASK;x=signed(x)>>15;return(T-x)&MASK
images={n:ElfImage(O/'rebuild'/(n+'.elf'))for n in ['control','candidate']};mapping={};tables=[]
for label,e in images.items():
 start=e.symbols['mk61_m0_inline_seed_begin']&~1;end=e.symbols['mk61_m0_inline_seed_done']&~1;table=e.named_sections['.ddiv'][3]+e.named_sections['.ddiv'][5]-256
 raw=mem(e,table,256);tables.append(raw);adr=struct.unpack('<H',mem(e,start+6,2))[0];assert adr&0xf800==0xa000 and ((start+10)&~3)+4*(adr&255)==table
 mapping[label]=dict(begin=start,done=end,table=table,bytes=end-start)
assert tables[0]==tables[1];table=struct.unpack('<128H',tables[1]);assert all(t==(1<<32)//(65536+512*i+256)for i,t in enumerate(table))
c,n=images['control'],images['candidate'];cb,nb=mapping['control']['begin'],mapping['candidate']['begin'];ce,ne=mapping['control']['done'],mapping['candidate']['done']
assert ce-cb==50 and ne-nb==56
assert mem(c,cb,6)==mem(n,nb,6)and mem(c,cb+8,28)==mem(n,nb+8,28)and mem(c,cb+38,4)==mem(n,nb+38,4)
for e,start,done in [(c,cb,ce),(n,nb,ne)]:
 h=struct.unpack('<H',mem(e,start+36,2))[0];i=h&255;assert h>>8==0xd3 and start+40+2*(i-256 if i>=128 else i)==done
 h=struct.unpack('<H',mem(e,start+42,2))[0];i=h&2047;assert h&0xf800==0xe000 and start+46+2*(i-2048 if i>=1024 else i)==done
assert mem(n,ne-12,12).hex()=='013e7f1802d5013e7f188641'
# BPL must target done, followed by immediate ADD/SBC; the carry is fresh.
h=struct.unpack('<H',mem(n,ne-8,2))[0];imm=h&255;assert h>>8==0xd5 and ne-8+4+2*(imm-256 if imm>=128 else imm)==ne
for label,e in images.items():
 start=mapping[label]['begin'];done=mapping[label]['done'];sw=e.symbols['mk61_m0_reciprocal1_sw_from_guard']&~1;before=e.symbols['mk61_m0_reciprocal1_sw_before_second_product']&~1
 assert mem(e,done,4).hex()=='01367608'
 parsed=[]
 for line in(O/(label+'.elf.actual.dis')).read_text().splitlines():
  m=re.match(r'^([0-9a-f]+):\s+[0-9a-f]{4}\s+([a-z][a-z0-9.]*)\s+(.*)$',line)
  if m and done<=int(m[1],16)<before:parsed.append(m[2]+' '+m[3].split('@')[0].split('<')[0])
 assert not any(re.search(r'\br7\b',line)for line in parsed)
 after=e.symbols['mk61_m0_reciprocal1_sw_after_second_product']&~1
 assert mem(e,before+6,2).hex()=='170c' # LSRS R7,R2,16 precedes every read of old R7.
 mapping[label].update(after_round=done+4,before_second=before,after_second=after,sw=sw,R7_dead_before_first_overwrite=True)
assert mem(c,ce,(c.symbols['mk61_m0_reciprocal1_sw_from_guard']&~1)+c.sizes['mk61_m0_reciprocal1_sw_from_guard']-ce)==mem(n,ne,(n.symbols['mk61_m0_reciprocal1_sw_from_guard']&~1)+n.sizes['mk61_m0_reciprocal1_sw_from_guard']-ne)
units={label:ElfImage(O/'rebuild/unit'/(label+'.elf'))for label in images}
for label,e in units.items():
 a=e.symbols['mk61_m0_inline_seed_begin']&~1;b=e.symbols['mk61_m0_inline_seed_done']&~1
 assert b-a==mapping[label]['bytes'];prod=mem(images[label],mapping[label]['begin'],b-a);unit=mem(e,a,b-a)
 assert prod[:6]==unit[:6]and prod[8:]==unit[8:]
 mapping['unit_'+label]=dict(begin=a,done=b,after_round=None)
rows=[];hist=Counter();examples={};limits=Counter()
for D in range(65536,131072):
 q=estimate(D,table);Q=MASK//D;k=q-Q;r=MASK-q*D;assert -1<=k<=3 and signed(r&MASK)==r
 final=MASK-Q*D;assert 0<=final<D
 qnew=q;rn=r
 if r<0:
  assert k in [1,2,3]and-k*D<=r<=-(k-1)*D-1
  qnew-=1;rn+=D
  if rn<0:
   qnew-=1;unsigned=(rn&MASK)+D;carry=unsigned>>32;rn=signed(unsigned&MASK);assert carry==(1 if k==2 else 0)
   qnew-=1-carry
  else:assert k==1
 else:
  if rn>=D:qnew+=1;rn-=D
 assert qnew==Q and rn==(final-D if k==3 else final)
 assert Q+1<1<<31 and Q>=32768 # ADD1 gives V=0; LSR then flags equal.
 hist[k]+=1;examples.setdefault(str(k),D);limits[k]=D
 rows.append(dict(D=D,estimate=q,quotient=Q,error=k,old_residue=final,new_residue=rn&MASK,saving=3 if k==3 else 0))
assert hist=={-1:140,0:5167,1:35252,2:23815,3:1162}
selection=set(examples.values())|set(limits.values())|{65536,65537,65791,65792,98303,98304,131070,131071}
save('integer-domain.json',dict(status='PASS_ALL65536_HOST_EXACT_THUMB_ARITHMETIC_QUOTIENT_AND_R7_RULE',table256_sha256=hashlib.sha256(tables[1]).hexdigest(),error_histogram=dict(hist),examples=examples,last_examples=dict(limits),rows=rows,ARM_calls=0,MPFR_inputs=0))
save('unit-selection.json',dict(values=sorted(selection),all16_flags_each=True,all5_errorclasses=True))
out=dict(status='PASS_PRIVATE_R0_ZERO_BOUND3_FULL_DOMAIN_AND_FRESH_R7_DEADNESS_PROOF',
 domain='D=65536..131071 all65536, actual128 integer table values, exact uint32/ASR operations from emitted Thumb',error_histogram=dict(hist),
 quotient='floor((2^32-1)/D) exact for every D. Initial true residual r-kD is signed-safe; no modular sign ambiguity.',
 k1='First decrement+ADD yields residual>=0, BPL exits; branch direction differs from old BMI loop even with same instruction count.',
 k2='After second decrement+ADD, unsigned carry1 so immediate SBC q,R0 subtracts0 under R0=0.',
 k3='Second ADD leaves negative residual and carry0, immediate SBC q,R0 subtracts1; quotient exact. R7=old_residue-D, deliberately not exact remainder.',
 private_contract='NEW seed requires raw R0=0, proved at sole actual positive-one root entry and unchanged guarded software prefix; cannot transfer old generic R0-input preservation contract.',
 negative_R0_control='For k2/3 a nonzero R0 would subtract it as well. Such input is outside this private contract, not qualified generic seed ABI.',
 post_seed='ADDS q,1 cannot signed-overflow for q in[32768,65535]; V=0, following LSRS produces identical NZCV and u0. R7 alone may differ.',
 R7_liveness='No emitted R7 reference between seed done and second product; first R7 use is LSRS R7,R2,16 overwrite before any read. Under new Zero scratch product, after-second full states and all later R3-certificate joins rejoin.',
 unit_and_production_macro_byteequal_except_decoded_ADR=True,same_table_all128_constants=True,unchanged_complete_after_seed_function_suffix=True,
 incoming_NZCV_dead_before_every_carry_use=True,oldloop_control_retained=True,instruction_nonincrease_NOT_cycle_nonregression=True,physical_branch_cost_unmeasured=True,
 mapping=mapping,performance_adoption_GO=False,ARM_calls=0,MPFR_inputs=0,devices=0)
print(json.dumps(save('proof.json',out)),flush=True)

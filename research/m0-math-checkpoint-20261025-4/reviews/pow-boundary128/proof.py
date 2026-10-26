"""Source equivalence proof witnesses, actual linked calls, loader hazard."""
import ast,hashlib,json,random,re,struct,subprocess,sys
from pathlib import Path
sys.dont_write_bytecode=True
R=Path('/Users/bolk/Projects/MK61S_MINI');O=Path(__file__).resolve().parent;W=R/'.build/m0-pow-boundary128-20261025'
P=R/'.build/m0-asin-scaled-bound-v164-20261023';SQ=R/'.build/m0-pow-square128-r2-20261025'
sys.path.insert(0,str(R/'tests'));from check_stm32_vectors import ElfImage
def ref(p):
 p=Path(p);b=p.read_bytes();return dict(path=str(p),bytes=len(b),sha256=hashlib.sha256(b).hexdigest())
def memory(e,a,n):
 s=next(s for s in e.sections if s[1]!=8 and s[3]<=a and a+n<=s[3]+s[5]);return e.bytes_at(s)[a-s[3]:a-s[3]+n]
def parse(text):
 out={}
 for line in text.splitlines():
  m=re.match(r'^\s*([0-9a-f]+):\s+((?:[0-9a-f]{4}\s+)+)([a-z][a-z0-9.]*)\s*(.*)',line)
  if m:out[int(m[1],16)]=(2*len(m[2].split()),m[3].split('.')[0],m[4].split('@')[0].strip())
 return out
# Algebra for old carry-based guard, including low32=FFFFFFFF special case.
M32=(1<<32)-1;M64=(1<<64)-1;rng=random.Random(0xB1282025);tests=[]
for hi in [0,1,0xfffff,0x100000,0x100001,0x7feffffe,0x7fefffff,0x7ff00000,0x80000000,M32]:
 for lo in [0,1,0x7fffffff,0xfffffffe,M32]:tests.append((hi,lo))
tests +=[(rng.getrandbits(32),rng.getrandbits(32))for _ in range(1024)]
for hi,lo in tests:
 carryA=int(lo==M32);r4=(hi-0x7fefffff-(1-carryA))&M32;carryB=int(lo!=M32)
 accepted=0x7fdfffff+r4+carryB>=1<<32;cell=(hi<<32)|lo
 assert accepted==(0x0010000000000000<=cell<0x7fefffffffffffff)
 if accepted:
  coef=2*((cell&((1<<52)-1))|(1<<52))+1;high=coef<<10
  assert high&M32==((lo<<11)&M32)|1024
  assert high>>32==((((hi&0xfffff)|0x100000)<<11)|(lo>>21))
# This complements the universal bitfield/carry proof; it is not a corpus.
for n in [0,1,2,3,4,7,8,127,128,129,0x7fffffff,0x80000000,M32]:
 old=[];new=[];x=n
 if x>=2:
  while True:
   old.append(1);previous=x;x>>=1
   if previous<=3:break
 x=n
 while x>1:new.append(1);x>>=1
 assert len(old)==len(new)
# Equivalence of split words to the exact modular inverse endpoint tests.
inversechecks=0
for H in [0,1,(1<<63)-1,1<<63,(1<<63)+1,M64]:
 for L in [0,1,M32,1<<32,M64]:
  for rad in [0,1,16,255,M32]:
   h0,h1=H&M32,H>>32;l0,l1=L&M32,L>>32
   new0=-1 if h1>0x80000000 or(h1==0x80000000 and h0)or l1 or l0>rad else 0
   assert new0==(-1 if H>1<<63 or L>rad else 0)
   newm1=1 if h1!=M32 or h0!=M32 or L<((-rad)&M64)else 0
   assert newm1==(1 if H!=M64 or L<((-rad)&M64)else 0)
   inversechecks+=1
# Fresh linked disassembly binds each real retained caller and new BL target.
tc=Path(json.loads((W/'build.json').read_text())['commands'][0][0]).parent
source=(R/'.build/m0-exp-cached-product-independent-20261024/bind_rebuild.py').read_text()
fn=next(n for n in ast.parse(source).body if isinstance(n,ast.FunctionDef)and n.name=='relocs')
exec(compile(ast.Module(body=[fn],type_ignores=[]),'<accepted-relocs>','exec'),globals())
obj=ElfImage(W/'RP-candidate.o');resident=ElfImage(P/'firmware/mk61s-picocalc-pico-h.elf');symbols=[]
for tab in obj.sections:
 if tab[1]!=2:continue
 names=obj.bytes_at(obj.sections[tab[6]])
 for off in range(0,tab[5],tab[9]):
  n,v,z,info,other,idx=struct.unpack_from('<IIIBBH',obj.bytes_at(tab),off)
  if info&15==2 and z:symbols.append((obj.string(names,n),v&~1,z,idx))
oldname='_ZL16root128_boundaryRK13PowInteger128jby';actual=[]
for section,rows in relocs(obj).items():
 for offset,kind,target in rows:
  if target!=oldname or kind!=10:continue
  idx=next(i for i,s in enumerate(obj.sections)if s==obj.named_sections[section])
  owner,address,size,_=next(s for s in symbols if s[3]==idx and s[1]<=offset<s[1]+s[2])
  pc=(resident.symbols[owner]&~1)+offset-address
  dis=subprocess.check_output([str(tc/'arm-none-eabi-objdump'),'-d','--start-address='+hex(pc),'--stop-address='+hex(pc+18),str(P/'firmware/mk61s-picocalc-pico-h.elf')],text=True)
  ins=parse(dis);assert ins[pc][1]=='bl'and int(ins[pc][2].split()[0],16)==0x10150000
  assert any(op=='cmp'and args.startswith('r0,')for sz,op,args in ins.values())and not any(re.search(r'\b(?:r12|ip)\b',args)for sz,op,args in ins.values()),(owner,hex(pc),ins)
  actual.append(dict(owner=owner,pc=hex(pc),fresh_actual_call_disassembly=dis))
assert len(actual)==4 and {r['owner']for r in actual}=={'pow_root128_decide'}
code=parse((O/'candidate.elf.actual.dis').read_text());calls=[]
for pc,(size,op,args)in code.items():
 if 0x101e0000<=pc<0x101e00d4 and op=='bl':calls.append(int(args.split()[0],16))
assert set(calls)=={0x1014f720,0x100f9c9c,0x100f9268}and len(calls)==3
assert all(not re.search(r'\b(?:r12|ip)\b',args)for pc,(size,op,args)in code.items()if 0x101e0000<=pc<0x101e00d4)
# A HOST byte-level negative control: applying an old168 bank after the new
# table bank destroys exactly14 bytes at the new entry. Never execute it.
table=ElfImage(R/'.build/m0-pow-exp-table-product-20261025/candidate.elf')
overlay=ElfImage(R/'.build/m0-exp-directed-product-20261024/candidate.elf')
ts=table.symbols['mk61_m0_pow_exp_table_product']&~1;old=overlay.named_sections['.product_ram'];a=max(ts,old[3]);b=min(ts+20,old[3]+old[5])
assert old[5]==168 and b-a==14 and a==ts
expected=memory(table,ts,20);after=bytearray(expected);after[:14]=overlay.bytes_at(old)[ts-old[3]:ts-old[3]+14]
assert bytes(after)!=expected
out=dict(status='PASS_SOURCE_GUARD_MIDPOINT_LOOP_ENDPOINT_AND_FRESH_LINKED_CALLER_PROOF',
 guard_proof='Old carry guard: low!=FFFFFFFF admits hi00100000..7FEFFFFF; low==FFFFFFFF admits hi00100000..7FEFFFFE. Exactly [0010000000000000,7FEFFFFFFFFFFFFF).',
 guard_and_initialization_HOST_spot_checks=len(tests),midpoint_identity='C=2*((cell&fraction)|2^52)+1; H=C<<10, L=radius=0, exponent=biased-1023; word shifts have disjoint OR fields.',
 same_loop_floor_log2_unsigned_denominator=True,production_power_of_two_domain=[1<<k for k in range(8)],
 inductive_step='Same actual accepted Square12824-byte modular transform, including radius+16 for nonzeroL, carry/normalization and exponent/radius32 wrap; previous inline copy implements that transform.',
 square_proof_reused=ref(R/'.build/m0-pow-square128-independent-20261025/proof.json'),
 inverse_endpoint_rule_HOST_spot_checks=inversechecks,inverse_rules='e>0=>-1;e<-1=>+1;e=0 tests H>2^63 or L>radius;e=-1 tests H!=2^64-1 or L<(-radius mod2^64). Radius0 threshold preserved.',
 noninverse_same372byte_compare_original_power_and_identical_midpoint=True,zero_side_remains_undecided=True,
 all24_midpoint_fields_same_no_interval_radius_or_RNE_policy_change=True,
 ABI='Pointer,u32,bool occupy R0,R1,R2; aligned uint64 fourth argument is incomingSP[0:8], R3 unused. 8-byte tail preserves R0-R2/SP/LR/cell; ordinary int32 R0 return; no R12 extra contract.',
 fresh_actual_four_retained_callers=actual,new_linked_BL_targets=[hex(a)for a in calls],new_code212_literal16_section228=True,
 rejected80bit_code_absent_by_exact_one_slot_source_diff_object_and_link_closure=True,
 new_code_undefined_calls_only_accepted_square_original_mul_original_compare=True,
 shared_product_R12_unchanged_component_reuse_not_new_integrated_guard=True,
 old168_overlay_negative_control=dict(overwritten_new_entry_bytes=14,old_overlay=ref(R/'.build/m0-exp-directed-product-20261024/candidate.elf'),old_bank_bytes=168,overlap_start=hex(ts),preflight_rejects_corrupted_entry=True,ARM_calls=0),
 preservation_not_general_pow_totality=True,CPU_only=True,ARM_calls=0,MPFR_inputs=0,device_IO=0)
with (O/'proof.json').open('x')as f:json.dump(out,f,indent=2);f.write('\n')
print(json.dumps(ref(O/'proof.json')),flush=True)

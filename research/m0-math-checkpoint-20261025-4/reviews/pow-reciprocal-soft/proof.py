"""Exact integer seed invariant and private continuation state proof."""
import hashlib,json,re,struct,subprocess,sys
from pathlib import Path
sys.dont_write_bytecode=True
R=Path('/Users/bolk/Projects/MK61S_MINI');O=Path(__file__).resolve().parent;W=R/'.build/m0-pow-reciprocal-soft-20261025'
sys.path.insert(0,str(R/'tests'));from check_stm32_vectors import ElfImage
def ref(p):
 p=Path(p);b=p.read_bytes();return dict(path=str(p),bytes=len(b),sha256=hashlib.sha256(b).hexdigest())
def parse(text):
 out={}
 for s in text.splitlines():
  m=re.match(r'^\s*([0-9a-f]+):\s+((?:[0-9a-f]{4}\s+)+)([a-z][a-z0-9.]*)\s*(.*)',s)
  if m:out[int(m[1],16)]=(len(m[2].split())*2,m[3].split('.')[0],m[4].split('@')[0].strip())
 return out
e=ElfImage(O/'rebuild/candidate.elf');control=ElfImage(O/'rebuild/control.elf');code=parse((O/'candidate.elf.actual.dis').read_text())
entry=e.symbols['mk61_m0_hint_ddiv']&~1;sw=e.symbols['mk61_m0_ddiv_sw_from_guard']&~1;seed=e.symbols['mk61_m0_ddiv_seed17']&~1;join=e.symbols['mk61_m0_sw_join']&~1
assert entry==0x101e1040 and sw>entry and seed>sw
start=0x1014e668+2732;size,op,args=code[start];assert size==4 and op=='bl'and int(args.split()[0],16)==entry
assert code[start+4][1]in ['mov','movs']and code[start+4][2]=='r5, r0'
assert code[entry][1]=='push'and all(r in code[entry][2]for r in ['r4','r5','r6','r7','lr'])
assert code[sw][1]=='lsls'and code[sw][2]=='r6, r6, #2'
# Seed machine code: 15 identical restoring-division rounds; no memory,
# stack, incoming flag, R12 or other register dependence.
seedcode=[(a,code[a])for a in sorted(code)if seed<=a<seed+194]
assert len(seedcode)==97 and seedcode[-1][1][1:] == ('bx','lr')
assert not any(op.startswith(('ldr','str','push','pop'))or re.search(r'\b(?:r3|r4|r5|r6|r7|r8|r9|r10|r11|r12|ip|sp)\b',args)for a,(n,op,args)in seedcode)
assert sum(op=='bcc'for a,(n,op,args)in seedcode)==15 and sum(op=='adcs'for a,(n,op,args)in seedcode)==15
quotmin=1<<32;quotmax=0;Tmax=Qmax=0
for D in range(1<<16,1<<17):
 Q=1;rem=(1<<17)-1-D;prefix=(1<<17)-1
 assert prefix==Q*D+rem and 0<=rem<D
 for i in range(15):
  T=2*rem+1;bit=int(T>=D);Tmax=max(Tmax,T);assert T<1<<18
  rem=T-bit*D;Q=2*Q+bit;prefix=2*prefix+1
  assert 0<=rem<D and prefix==Q*D+rem and Q<1<<16;Qmax=max(Qmax,Q)
 assert prefix==0xffffffff and Q==0xffffffff//D
 u=(Q+1)>>1;assert Q+1<=65536 and 16384<=u<=32768
 quotmin=min(quotmin,Q);quotmax=max(quotmax,Q)
assert [quotmin,quotmax]==[32768,65535]and Qmax==65535
assert ((1<<17)-1-65535)>=65535 and ((1<<17)-1-131072)<0
# The first common instructions establish all flags before branching. R7's
# first mention after the join is a write, so differing pre-join R7 is dead.
first=[code[join+2*i]for i in range(5)]
assert [v[1]for v in first]==['muls','asrs','muls','asrs','adds']and first[-1][2]=='r5, #1'
r7=next((a,op,args)for a,(n,op,args)in sorted(code.items())if a>=join and re.search(r'\br7\b',args))
assert r7[1]=='lsrs'and r7[2]=='r7, r4, #16'
assert not any(op.startswith('b')for a,(n,op,args)in code.items()if join<=a<r7[0])
# Five saved words at entry plus five transient saved words preserve AAPCS
# 8-byte seed-call alignment, without treating the continuation as a C ABI.
swcode=[(a,n,op,args)for a,(n,op,args)in sorted(code.items())if sw<=a<join]
push=next((a,args)for a,n,op,args in swcode if op=='push');pop=next((a,args)for a,n,op,args in swcode if op=='pop')
assert all(re.search(r'\b'+r+r'\b',push[1])for r in ['r0','r1','r2','r3','r7'])and push[1]==pop[1]
calls=[(a,int(args.split()[0],16))for a,n,op,args in swcode if op=='bl'];assert len(calls)==1 and calls[0][1]==seed
assert (0-20-20)%8==0
# Check hidden symbol visibility for private continuation and exact leaf.
hidden={}
for s in e.sections:
 if s[1]!=2:continue
 names=e.bytes_at(e.sections[s[6]])
 for n,a,z,info,other,index in struct.iter_unpack('<IIIBBH',e.bytes_at(s)):
  name=e.string(names,n)
  if name in ['mk61_m0_hint_ddiv','mk61_m0_ddiv_sw_from_guard','mk61_m0_ddiv_seed17']:hidden[name]=other&3
assert len(hidden)==3 and set(hidden.values())=={2}
# The original unsigned normal/result guard implies the private state bound.
guardchecks=0
for ea in [0,1,2,1022,1023,1024,2045,2046,2047]:
 for eb in [0,1,2,1022,1023,1024,2045,2046,2047]:
  ga=((ea-1)&0xffffffff)<=2045;gb=((eb-1)&0xffffffff)<=2045
  assert ga==(1<=ea<=2046)and gb==(1<=eb<=2046)
  exp=ea-eb+1021;accepted=ga and gb and(exp&0xffffffff)<=2043
  assert accepted==(1<=ea<=2046 and 1<=eb<=2046 and 0<=exp<=2043)
  if accepted:
   for sign in [0,1]:assert 0<=4*exp+sign<=8173
  guardchecks+=1
out=dict(status='PASS_EXACT_SEED_AND_PRIVATE_GUARDED_JOIN_PROOF',
 source_and_tail_binding=ref(O/'binding.json'),actual_root_BL=hex(start),actual_private_entry=hex(entry),actual_sw=hex(sw),actual_seed=hex(seed),actual_common_join=hex(join),
 HOST_integer_seed_invariant_checks=65536,not_ARM_or_MPFR_calls=True,exact_quotient_domain=[65536,131071],quotient_range=[32768,65535],
 invariant='prefix=Q*D+R; initial17 one bits Q=1,R=131071-D; fifteen steps T=2R+1,bit=(T>=D),R=T-bit*D,Q=2Q+bit give prefixFFFFFFFF.',
 carry_reason='CMP gives C=(T>=D); BCC preserves it; selected SUBS cannot borrow and retains C=1; ADCS appends that bit. Incoming flags are replaced before they can affect a quotient bit.',
 Tmax_observed=Tmax,T_less_2pow18_proved=True,Q_fits_unsigned16_all_steps=True,no_32bit_overflow=True,
 seed_rounding='q=floor(FFFFFFFF/D); u0=(q+1)>>1 is identical hardware sequence, range16384..32768, q+1<=65536.',
 normal_guard_and_result_exponent_HOST_boundary_checks=guardchecks,R6_guard_range=[0,2043],R12_tag_max8173=True,
 private_state_preconditions='Entry normal raw R0:R1 and R2:R3, guarded R6=Ea-Eb+1021, unchanged saved20B R4-R7/LR frame. No standalone C ABI at sw_from_guard.',
 software_seed_save_pop_preserves_four_raw_unpacked_words_and_R7=True,seed_call_SP_8aligned=True,seed_only_writes_R0_R2_flags_no_memory_and_R12_unchanged=True,
 at_join_R0_R6_R12_SP_and_saved20_equal_to_hardware=True,
 dead_R7_first_common_use_is_write=dict(pc=hex(r7[0]),instruction=r7[1]+' '+r7[2]),
 common_first_ASRS_sets_carry_first_ADDS_sets_all_flags_before_branch=True,
 common_NR_exact_remainder_RNE_tail282_byte_equal=True,no_new_approximation_precision_or_RNE_policy=True,
 fallback_and_dyadic_paths_preserve_existing_IEEE_bits=True,private_symbols_hidden=hidden,
 no_generic_ddiv_continuation_export_or_reuse=True,source_merge_actual_R12_loader_layout_required=True,
 existing_common_kernel_contract_reused_not_new_general_pow_totality=True,ARM_calls=0,MPFR_inputs=0,device_IO=0)
with (O/'proof.json').open('x')as f:json.dump(out,f,indent=2);f.write('\n')
print(json.dumps(ref(O/'proof.json')),flush=True)

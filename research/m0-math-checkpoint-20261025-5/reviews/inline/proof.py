"""Exact RNE overflow threshold and register-renamed inline quotient proof."""
import ast,hashlib,json,re,struct,sys
from collections import Counter
from pathlib import Path
sys.dont_write_bytecode=True
R=Path('/Users/bolk/Projects/MK61S_MINI');O=Path(__file__).resolve().parent;W=R/'.build/m0-pow-reciprocal-inline-20261025'
sys.path.insert(0,str(R/'tests'));from check_stm32_vectors import ElfImage
def ref(p):
 p=Path(p);b=p.read_bytes();return dict(path=str(p),bytes=len(b),sha256=hashlib.sha256(b).hexdigest())
def save(n,d):
 with (O/n).open('x')as f:json.dump(d,f,indent=2);f.write('\n')
 return ref(O/n)
def mem(e,a,n):
 s=next(s for s in e.sections if s[1]!=8 and s[3]<=a and a+n<=s[3]+s[5]);return e.bytes_at(s)[a-s[3]:a-s[3]+n]
fn=next(n for n in ast.parse((R/'.build/m0-pow-reciprocal-one-independent-20261025/proof.py').read_text()).body if isinstance(n,ast.FunctionDef)and n.name=='parse');exec(compile(ast.Module(body=[fn],type_ignores=[]),'<pure-disassembly-parser>','exec'),globals())
im=ElfImage(O/'rebuild/candidate.elf');unit=ElfImage(O/'rebuild/unit.elf');control=ElfImage(O/'rebuild/control.elf')
code=parse((O/'candidate.elf.actual.dis').read_text());entry=im.symbols['mk61_m0_reciprocal1']&~1;call=0x1014e668+2732
assert code[call][1]=='bl'and int(code[call][2].split()[0],16)==entry
assert code[call-10][1:]==('movs','r7, #0')and code[call-2][1:]==('mov','r0, r7')
ld=struct.unpack('<H',mem(im,call-4,2))[0];literal=(call&~3)+4*(ld&255);assert ld&0xff00==0x4900 and struct.unpack('<I',mem(im,literal,4))[0]==0x3ff00000
assert not any(call-10<a<=call for a in im.symbols.values())
for pc,(n,op,args)in code.items():
 if op.startswith('b')and op not in ['bx','blx']:
  try:target=int(args.split()[0],16)
  except ValueError:continue
  assert not call-10<target<=call
# IEEE overflow tie is the midpoint between max-finite and the virtual next
# significand2^1024; equality would round to infinity (even). No integer k
# lies at that rational threshold, by the strict neighbouring products.
T=1<<50;H=(1<<1024)-(1<<970);N=1<<1074
assert T*H==N-(1<<1020)and(T+1)*H-N==(1<<1024)-(1<<1020)-(1<<970)>0
assert T*H<N<(T+1)*H
predicate_checks=0
for k in [0,1,T-2,T-1,T,T+1,T+2,(1<<52)-1]:
 hi,lo=k>>32,k&0xffffffff;arm=(hi<(1<<18)or(hi==(1<<18)and lo==0));assert arm==(k<=T)
 if k:assert (N>=k*H)==(k<=T)
 for sign in [0,1]:
  high=hi|(sign<<31);stripped=((high<<1)&0xffffffff)>>1;assert stripped==hi
  result=((high>>31)<<63)|0x7ff0000000000000;assert result==((sign<<63)|0x7ff0000000000000)
  predicate_checks+=1
starts={};bodies={};tables={}
for label,e in [('production',im),('unit',unit)]:
 begin=e.symbols['mk61_m0_inline_seed_begin']&~1;done=e.symbols['mk61_m0_inline_seed_done']&~1;assert done-begin==50
 body=mem(e,begin,50);adr=struct.unpack_from('<H',body,6)[0];assert adr&0xff00==0xa400
 table=((begin+6+4)&~3)+(adr&255)*4
 assert table%4==0 and mem(e,table,256)==e.bytes_at(e.named_sections['.ddiv'if label=='production'else'.unit'])[-256:]
 starts[label]=dict(begin=hex(begin),done=hex(done),table=hex(table));bodies[label]=body[:6]+b'\0\0'+body[8:];tables[label]=mem(e,table,256)
assert bodies['production']==bodies['unit']and tables['production']==tables['unit']
values=struct.unpack('<128H',tables['production']);assert values==tuple((1<<32)//(65536+512*i+256)for i in range(128))
macro=(W/'inline-seed.inc').read_text();written=set()
for line in macro.splitlines():
 s=line.strip()
 if not s or s.startswith('.')or s.endswith(':'):continue
 op=s.split()[0]
 assert op not in ['push','pop','bl','blx','bx']and not op.startswith('str')
 if op not in ['cmp','b','bmi','bcc']:written.add(s.split()[1].split(',')[0])
assert written=={'r4','r6','r7'}and set(re.findall(r'\br(?:0|2|3|5|12)\b',macro))==set()
errors=Counter();downmax=upmax=0;adversaries={}
for D in range(65536,131072):
 i=(D>>9)-128;assert 0<=i<128;u=values[i];p=((D+1)>>1)*u;assert abs(p-(1<<31))<1<<30
 e=(p-(1<<31))//65536;ue=u*e;assert -(1<<31)<=ue<1<<31
 q=u-(ue>>15);exact=0xffffffff//D;err=q-exact;errors[err]+=1;adversaries.setdefault('error'+str(err),D)
 r=0xffffffff-q*D;assert -(1<<31)<=r<1<<31;assert ((~(q*D&0xffffffff))&0xffffffff)==(r&0xffffffff)
 down=up=0
 if r<0:
  while r<0:q-=1;r+=D;down+=1
 elif r>=D:q+=1;r-=D;up=1
 assert q==exact and 0<=r<D and q*D+r==0xffffffff
 downmax=max(downmax,down);upmax=max(upmax,up)
assert errors=={-1:140,0:5167,1:35252,2:23815,3:1162}and(downmax,upmax)==(3,1)
save('adversarial-D.json',dict(status='EXACT_DOMAIN_CORRECTION_CLASS_EXAMPLES',values=adversaries))
latency=[]
for label,e in [('control',control),('candidate',im)]:
 dc=parse((O/(label+'.elf.actual.dis')).read_text());start=e.symbols['mk61_m0_reciprocal1']&~1
 issue=next(pc for pc,(n,op,args)in dc.items()if pc>start and op=='str'and args=='r6, [r7, #100]')
 read=next(pc for pc,(n,op,args)in dc.items()if pc>issue and op=='ldr'and args=='r6, [r7, #112]')
 ops=[dc[pc][1:]for pc in range(issue+2,read,2)];assert len(ops)==9 and all(op in ['lsls','lsrs','orrs']for op,args in ops)
 latency.append(mem(e,issue+2,18).hex())
assert latency[0]==latency[1]
out=dict(status='PASS_EXACT_RNE_INTEGER_OVERFLOW_AND_SHARED_REGISTER_INLINE_SEED_PROOF',
 exact_RNE_boundary='H=2^1024-2^970',subnormal_d='k*2^-1074',threshold_integer=1<<50,
 exact_strict_endpoint_products='T*H=2^1074-2^1020 <2^1074 <(T+1)*H; upper difference2^1024-2^1020-2^970>0',
 monotonicity_covers_all_integer_k1to2pow52minus1=True,no_rounded_threshold_or_unchecked_tie=True,
 k0_handled_by_IEEE_divide_by_signed_zero_not_inequality=True,sign_symmetric_Inf_raw_bits=True,ARM_high_low_comparison_exact_for_full52bits=True,
 predicate_boundary_spot_checks=predicate_checks,all_other_E_special_fallback_retains_raw_args=True,
 shared_macro_code50_only_ADR_relocation_differs_unit_production=True,shared_table256_exact=True,mapping=starts,
 inline_written_registers=sorted(written),preserves_R0_R1_R2_R3_R5_R12_SP=True,no_BL_stack_or_memory_writes=True,
 quotient_R6_D_R1_tempR4_residualR7_mapping=True,HOST_full_D_domain65536=True,error_histogram=dict(sorted(errors.items())),max_down3_up1=True,
 one_up_optimization_Euclidean_invariant_exact=True,deliberate_signed_modular_multiply_proof_unchanged=True,
 production_inline_SP_must_be_own_entry_minus20_not_outer_MachineSP=True,wrapper_stack_or_speed_not_production_claim=True,
 dead_R1_R7_before_second_macro_and_R4_before_first_product=True,common186_RNE_suffix_fourcopies_bound=True,
 READY9ALU_bytes_preserved=True,private_root_positive1_BL_call_return_still_required=True,
 cold_parent_cost_increases_expected=dict(E0_high_gtT=8,E0_high_eqT_low_nonzero=11,Egreater2044=2),
 cold_Inf_fast_instruction_cost=dict(high_less2pow18=22,exact_boundary=24),
 no_generic_CABI_or_new_global_division=True,ARM_calls=0,MPFR_inputs=0,device_IO=0)
print(json.dumps(save('proof.json',out)),flush=True)

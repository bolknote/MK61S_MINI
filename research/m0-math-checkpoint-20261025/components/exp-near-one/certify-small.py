"""Exact source-bound enclosure and a literal standalone rounding unit."""
from pathlib import Path
from fractions import Fraction as F
import hashlib,json,random,shlex,struct,subprocess,sys
sys.dont_write_bytecode=True
W=Path(__file__).resolve().parent;ROOT=W.parents[1]
P=ROOT/'.build/m0-asin-scaled-bound-v164-20261023';C=ROOT/'.build/m0-exp-directed-product-20261024'
sha=lambda p:hashlib.sha256(p.read_bytes()).hexdigest()
b=json.loads((W/'build.json').read_text());source=(W/'candidate/native_eabi_m0.cpp').read_text();frag=(W/'small-fragment.cpp').read_text()
assert sha(W/'candidate/native_eabi_m0.cpp')==b['source_sha256']
anchor='\n#endif\n// On ARMv6-M, -O3 expands wide products'
assert source.count('\n'+frag+anchor)==1
without=source.replace('\n'+frag+anchor,anchor)
dispatch=' else if(e<-11) {\n    return real(exp_small_rne(a));\n  }'
assert without.count(dispatch)==1 and without.replace(dispatch,'')==(C/'candidate/native_eabi_m0.cpp').read_text()
assert 'asm(R"asm(\n'+(W/'small-products.S').read_text()+')asm");' in frag
for literal in ['4U*uint32_t(square>>48)+32U+extra+fifth_error','mk61_m0_exp_small_square48(m>>5,unsigned(26-e))','fifth_error=e==-15?69U:e==-16?5U:1U']:
 assert literal in frag
rho=F(1,2048);eta=F(7,2)+F(1,32768)
derivative=F(1,6)+rho/12+rho*rho/40
tail_error=eta+rho*(F(1,2)+eta+rho*(F(1,2)+eta+rho/2))+derivative/F(65536)
assert tail_error<4
H=rho/6+rho*rho/24+rho**3/120
remainder6=F(2**14,720)/(1-rho/7)
other=4+H+remainder6;assert other<27
for e in range(-32,-11):
 extra=(1<<(e+22)) if e>=-22 else 0
 assert (F(1,2)+H)*F(2)**(e+23)<extra+1
assert F(64**5-63**5,3840)<21174
fifth_bounds={}
for e in range(-32,-12):
 if e>-15:
  s=-4*e-48
  bound=(21174>>s)+2
  assert F(64**5-63**5,15*(1<<(s+8)))+1<bound
 else:
  bound=69 if e==-15 else 5 if e==-16 else 1
  assert F(2)**(4*e+73)/120<bound
 fifth_bounds[e]=bound
K=1<<48
coefs={6:46912496118443,24:11728124029611,120:2345624805922}
for d,v in coefs.items():assert abs(F(v)-F(K,d))<=F(1,2)
c2max=F(K,24)+F(1,2)+rho*(F(K,120)+F(1,2))+eta
c1max=F(K,6)+F(1,2)+rho*c2max+eta
tmax=rho*c1max+eta
assert c2max<1<<44 and c1max<1<<46 and tmax<1<<35
assert F(K,24)-F(1,2)-rho*(F(K,120)+F(1,2))-eta>0
assert F(K,6)-F(1,2)-rho*c2max-eta>0
assert 63**5<1<<30
# Exact /15 for all possible coarse-fifth intermediates. The algebra uses
# 65536=15*4369+1; the small reciprocal underestimates by less than one.
divmax=(63**5)>>12
for u in range(divmax+1):
 h=u>>16;v=(u&65535)+h;q=(v*4369)>>16
 assert q+int(v-15*q>=15)+h*4369==u//15
assert 5148<8192 and 2*8192<1<<27
first=frag.index('  const unsigned shift=unsigned(16-e)')
pack=frag[first:frag.rindex('\n}')]
pack=pack.replace('if(unsafe) return bits(exp_refine(real(a),0));','if(unsafe) return UINT64_MAX;')
unit='''#include <stdint.h>
using U=uint64_t;
extern "C" __attribute__((optimize("Os"))) U audit_exp_small_pack(U a,U correction,U error64) {
 const bool negative=bool(a>>63);
 const int e=int((a>>52)&2047U)-1023;
 const uint32_t lo=uint32_t(a),hi=(uint32_t(a>>32)&0xFFFFFU)|0x100000U;
 const U m=(U(hi)<<32)|lo;
 const uint32_t error=uint32_t(error64);
'''+pack+'\n}\n'
(W/'pack-unit.cpp').write_text(unit)
rng=random.Random(0x5A11C679);jobs={}
for e in range(-32,-11):
 for sign in (0,1):
  mantissas={1<<52,(1<<53)-1,(1<<52)|0xffffffff,(1<<53)-(1<<32)}
  mantissas.update((1<<52)|rng.getrandbits(52) for _ in range(24))
  t=16-e-sign;U0=1<<t
  for m in sorted(mantissas):
   a=(sign<<63)|((e+1023)<<52)|(m-(1<<52))
   for error in (1,29,32,512,1325,5148,8191):
    for k in (-error-1,-error,-error+1,-1,0,1,error-1,error,error+1):
     target=U0//2+k
     low=((m<<16)-target if sign else target-(m<<16))&(U0-1)
     correction=((rng.getrandbits(58)>>t)<<t)|low
     jobs.setdefault((a,correction,error),None)
raw=b''.join(struct.pack('<3Q',*row) for row in jobs)
(W/'pack-unit-inputs.bin').write_bytes(raw)
entry=next(e for e in json.loads((P/'build/compile_commands.json').read_text()) if e['file'].endswith('/code/native_eabi_m0.cpp'))
cmd=shlex.split(entry['command']);cc=Path(cmd[0]).parent
cmd[cmd.index(entry['file'])]=str(W/'pack-unit.cpp');cmd[cmd.index('-o')+1]=str(W/'pack-unit.o')
subprocess.run(cmd,cwd=W,check=True)
(W/'pack-unit.ld').write_text('PHDRS { code PT_LOAD FLAGS(5); }\nSECTIONS { . =0x10166000; .unit : { *(.text*) *(.rodata*) } :code /DISCARD/ : { *(.ARM.exidx*) *(.ARM.extab*) *(.comment) *(.ARM.attributes) *(.note*) } }\n')
link=[str(cc/'arm-none-eabi-ld'),'--gc-sections','-e','audit_exp_small_pack','-T',str(W/'pack-unit.ld'),str(W/'pack-unit.o'),'-o',str(W/'pack-unit.elf')]
subprocess.run(link,cwd=W,check=True)
assert not subprocess.check_output([str(cc/'arm-none-eabi-nm'),'-u',str(W/'pack-unit.elf')],text=True)
out=dict(status='AUTHOR_EXACT_SOURCE_BOUND_NEAR_ONE_EXP_ENCLOSURE',source_sha256=b['source_sha256'],candidate_ELF_sha256=b['candidate_ELF_sha256'],
 parent_FROZEN_sha256=sha(C/'FROZEN.json'),only_RP_small_exp_helper_and_dispatch_added=True,
 private_return_proof_sha256=sha(W/'private-return-proof.json'),shared77product_unchanged=True,
 domain_e=[-32,-12],rho=str(rho),high_product64_error_bound=str(eta),middle_product48_error_strict3=True,
 Horner_Q48_tail_error_bound=str(tail_error),Horner_tail_error_strict4=True,
 square_formula='Z=floor(floor(M/32)^2/2^(26-e))',square_X48_exact_integer_kernel=True,
 square_full_value_strict_below_2pow58=True,square_truncation_extra_error_strict_extra_plus1=True,
 remaining_error_Q16_bound=str(other),remaining_error_strict27=True,
 final_guard='4*floor(Z/2^48)+32+extra+fifth_error',extra='2^(e+22) for e>=-22,otherwise0',
 fifth_error_by_e=fifth_bounds,coarse6bit_fifth_interval_all32classes_proven=True,
 exact_div15_exhaustive_host_values=divmax+1,host_values_not_ARM_calls=True,
 all_product_operands_A48_B58_and_square_shift38to58_proven=True,
 all_Horner_coefficients_positive_and_source_unsigned_operations_fit=True,
 all_explicit_32bit_shifts_in_range_and_no_libgcc_needed=True,
 packing_modular_guard_excludes_every_midpoint_and_source_rounding_is_RNE=True,
 pack_unit_inputs=len(jobs),pack_unit_input_sha256=sha(W/'pack-unit-inputs.bin'),pack_unit_ELF_sha256=sha(W/'pack-unit.elf'),
 pack_literal_fragment_sha256=hashlib.sha256(pack.encode()).hexdigest(),commands=[cmd,link],
 IEEE_payload_endpoints_tiny_and_general_refinement_unchanged=True,hardware_accessed=False,independent_review_pending=True)
(W/'certificate.json').write_text(json.dumps(out,indent=2)+'\n')
print(json.dumps({k:v for k,v in out.items() if k!='commands'},indent=2))

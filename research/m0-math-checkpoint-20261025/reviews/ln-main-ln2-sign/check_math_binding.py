"""Independent narrow ln2-direction proof and full private artifact binding."""
from pathlib import Path
from fractions import Fraction as F
from collections import Counter
import hashlib,json,re,subprocess,sys
sys.dont_write_bytecode=True
R=Path('/Users/bolk/Projects/MK61S_MINI');P=R/'.build/m0-ln-main-ln2-sign-20261024';PAR=R/'.build/m0-ln-near-q77-linear-20261024';O=Path(__file__).resolve().parent
H=lambda p:hashlib.sha256(Path(p).read_bytes()).hexdigest()
def read(p):return json.loads(Path(p).read_text())
def pin(p):return dict(path=str(p),bytes=Path(p).stat().st_size,sha256=H(p))
assert H(P/'HANDOFF.md')=='f09c4d0b224e7fbc6872ec2763ee9f1c91db9f0c27ccc56f123ee9fcae4423fb'
assert H(P/'result.json')=='12b8ce5010e7804d5259119e7eb5e403eec0021065646d35f84718c1461c0b8f'
r=read(P/'result.json')
for n,h in r['files'].items():assert H(P/n)==h,n
inputs=read(P/'input-pins.json')['files']
for n,h in inputs.items():assert H(R/n)==h,n
premise=R/'.build/m0-ln-raw-cold-entry-independent-20261024/Q77-parent-premise-closure.json'
assert H(premise)=='d5bb11662781f4d0ce212dd07f6b555e0c602a6a6f2f5c56eae3d590ca63a3c9'
assert read(premise)['required_parent_reviews_both_component_GO']
assert r['parent_result_sha256']==H(PAR/'result.json') and (P/'control.elf').read_bytes()==(PAR/'candidate.elf').read_bytes()
source=(P/'native_eabi_m0_log70.inc').read_text();parent=(PAR/'native_eabi_m0_log70.inc').read_text()
assertion='''
static_assert(refine_log_two_high==((log70_two_high<<24)|uint32_t(log70_two_low>>40)) &&
    refine_log_two_low>(log70_two_low<<24),"Q70 ln2 must be a strict lower bound");'''
anchor='enum : uint32_t {ln_main_radius=8U,ln_near_radius=4U};'
expected=parent.replace(anchor,anchor+assertion)
old='  if(uint32_t(tail-(half-guard))<=2*guard) return ln_refine(x);'
new='''  if(uint32_t(tail-(half-guard))<=2*guard) {
#if defined(MK61_M0_RP2040_EABI) && MK61_M0_RP2040_EABI
    // Q70 ln2 rounds down. Its exponent contribution cannot move a
    // point from above the midpoint to below it.
    if(error<=ln_main_radius || tail<half+ln_main_radius) return ln_refine(x);
#else
    return ln_refine(x);
#endif
  }'''
assert expected.count(old)==1;expected=expected.replace(old,new)
start=expected.index('  if(uint32_t(tail-(half-guard))<=2U*guard) {',expected.index('inline double ln_main_pack70'));end=expected.index('\n  const uint32_t lo=',start)
block=expected[start:end];inside=block[block.index('\n')+1:block.rfind('\n  }')]
newblock='''  if(uint32_t(tail-(half-guard))<=2U*guard) {
    // The generic polynomial bound is13.400121<14; the ln2 error
    // on exponent paths is nonpositive in the final magnitude.
    if(!exponent_error || tail<half+14U) {
'''+''.join('  '+line+'\n' for line in inside.splitlines())+'''    }
  }'''
assert expected[:start]+newblock+expected[end:]==source
def function(s,name):
 i=s.index(name+'(');i=s.index('{',i);a=i;depth=1;i+=1
 while depth:depth+=(s[i]=='{')-(s[i]=='}');i+=1
 return s[a:i]
for name in ['ln_pack70','ln_main_pack70']:assert function(source,name)==function((P/'pack-unit.cpp').read_text(),name)
for n in ['native_eabi_m0.cpp','native_eabi_m0_log70_center.inc','native_eabi_m0_log70_ratio.inc','native_eabi_m0_log_subnormal.inc','native_eabi_m0_log10.inc','ratio.S']:assert (P/n).read_bytes()==(PAR/n).read_bytes(),n
# Callsite admission: only nonzero general exponents have error>8 (exact)
# or exponent_error>0 (raw); the inherited near call passes radius4.
assert source.count('return ln_pack70(')==3 and source.count('return ln_main_pack70(')==2
for s in ['return ln_pack70(low,high,negative?D::Sign:0,ln_near_radius,x);','if(!k) return ln_pack70(low,high,0,ln_main_radius,x);','return ln_pack70(result,upper,k<0?D::Sign:0,ln_main_radius+(n+1)/2,x);','if(!k) return ln_main_pack70(low,high,0,0,uint32_t(h),x);','return ln_main_pack70(result,upper,k<0?D::Sign:0,(n+1)/2,uint32_t(h),x);']:assert s in source
# Constants come from exactly the included/pinned V164 source tables.
code=R/'.build/m0-asin-scaled-bound-v164-20261023/source/code'
def constant(path,name):
 m=re.search(r'\b'+name+r'\s*=\s*(?:UINT64_C\((\d+)\)|(\d+)U)',path.read_text());assert m,name;return int(m[1] or m[2])
L70=(constant(code/'native_eabi_m0_log70_table.inc','log70_two_high')<<64)|constant(code/'native_eabi_m0_log70_table.inc','log70_two_low')
L94=(constant(code/'native_eabi_m0_refine_table.inc','refine_log_two_high')<<64)|constant(code/'native_eabi_m0_refine_table.inc','refine_log_two_low')
assert L70==818323753292969962226 and L94==13729194366926868337785367782
# Independent64-term atanh(1/3) enclosure; no generator/certificate execution.
t=F(1,3);z=t*t;lo=F(0)
for i in range(64):lo+=2*t/(2*i+1);t*=z
hi=lo+2*t/(129*(1-z))
def nearest(x):
 q,r=divmod(x.numerator,x.denominator);return q+(2*r>x.denominator or (2*r==x.denominator and q&1))
assert nearest(lo*(1<<70))==nearest(hi*(1<<70))==L70
assert nearest(lo*(1<<94))==nearest(hi*(1<<94))==L94
err_lo=F(L70)-hi*(1<<70);err_hi=F(L70)-lo*(1<<70)
assert -F(1,2)<err_lo<err_hi<0 and L94-(L70<<24)==7924966
prior=read(R/'.build/m0-ln-main-raw-split-family-independent-20261024/math-binding.json')
raw=F(prior['full_generic_bound']);arg=F(prior['total_argument_bound']);exact=raw-(arg-1)/(1-F(1,2048))
assert exact==F(read(R/'.build/m0-ln-enclosure-20261024/certificate.json')['main_bound']) and exact<8 and raw<14
# Word multiplications form n*L70 exactly. All intermediate sums fit64/32.
assert ((1<<32)-1)*1023+((1<<32)-1)<1<<64
assert (L70>>64)*1023+((1<<64)-1)*1023//(1<<64)<1<<32
# Both k signs have magnitude n*L70 +/- logm, hence identical negative
# exponent error n*epsilon. Upper shortcut cannot cross the lower midpoint.
# Next midpoint is at least2048 farther; check exact strict endpoints for
# every admitted n, including ceil-half parity (no binary64 corpus sweep).
checks=0;worst={}
for n in range(1,1024):
 extra=(n+1)//2
 for kind,bound,radius,maxd in [('exact',exact,8,7+extra),('raw',raw,14,15+extra)]:
  elo=-bound+n*err_lo;ehi=bound+n*err_hi
  assert radius-ehi>0 and maxd-elo<2048
  worst[kind]=max(worst.get(kind,F(0)),maxd-elo);checks+=2
# k belongs to[-1022,1023]; n0 never receives a new shortcut. Width64
# lowest-binade lower gap is inherited; new above-midpoint branch moves
# upwards and cannot skip the next midpoint even at binade carry.
assert [1-1023,2046-1023]==[-1022,1023]
sys.path.insert(0,str(R/'tests'));from check_stm32_vectors import ElfImage
def alloc(e):return {n:('NOBITS',s[5]) if s[1]==8 else ('BYTES',e.bytes_at(s)) for n,s in e.named_sections.items() if s[2]&2}
aa,bb=alloc(ElfImage(P/'control-full.o')),alloc(ElfImage(P/'candidate-full.o'))
changed={n:[len(aa.get(n,('BYTES',b''))[1]),len(bb.get(n,('BYTES',b''))[1])] for n in aa.keys()|bb.keys() if aa.get(n)!=bb.get(n)}
assert changed=={'.text.ln_main_raw':[1360,1368],'.text.mk61_m0_ln_positive':[1264,1272]}
candidate,control=ElfImage(P/'candidate.elf'),ElfImage(P/'control.elf')
assert candidate.bytes_at(candidate.named_sections['.rodata'])==control.bytes_at(control.named_sections['.rodata'])
assert (P/'candidate-ratio.o').read_bytes()==(P/'control-ratio.o').read_bytes()
for n in ['generic_M0','M4_soft','M4_hard']:assert (P/(n+'-candidate.o')).read_bytes()==(P/(n+'-control.o')).read_bytes()==(PAR/(n+'-candidate.o')).read_bytes()
resident=ElfImage(R/'.build/m0-asin-scaled-bound-v164-20261023/firmware/mk61s-picocalc-pico-h.elf');bindings=read(P/'candidate-build.json')['resident_bindings']
for n,a in bindings.items():assert resident.symbols[n if n not in ['memcpy','memset'] else '__wrap_'+n]==a,n
(O/'rebuild').mkdir(exist_ok=True);commands=[];rebuilt={}
for manifest,names in [('candidate-build.json',['candidate-full.o','candidate-ratio.o','candidate.elf']),('pack-unit-build.json',['pack-unit.o','pack-unit.elf'])]:
 changes={str(P/n):str(O/'rebuild'/n) for n in names}
 for command in read(P/manifest)['commands']:
  argv=[changes.get(x,x) for x in command];p=subprocess.run(argv,capture_output=True);assert p.returncode==0,p.stderr.decode();commands.append(argv)
 for n in names:assert (P/n).read_bytes()==(O/'rebuild'/n).read_bytes(),n;rebuilt[n]=H(O/'rebuild'/n)
# Static assert changes no executable bytes; do not count pre-assert probes.
for n in ['candidate-full.o','candidate.elf']:assert (P/n).read_bytes()==(P/'trials/before-static-assert'/n).read_bytes()
# Saved profile accounting, independent of author labels/derived summaries.
q=read(P/'qualification.json');old={(e['x'],e['SIO']):e for e in read(PAR/'qualification.json')['rows']};seen=set();hist=Counter();groups={s:Counter() for s in ['READY','DIRTY']};ploss=set();closs=set();newloss=[]
def eq(a,b):return a==b or ((a&0x7fffffffffffffff)>0x7ff0000000000000 and (b&0x7fffffffffffffff)>0x7ff0000000000000)
for row in q['rows']:
 key=row['x'],row['SIO'];assert key not in seen;seen.add(key)
 for n,v in row['outputs'].items():assert row['correct'][n]==eq(int(v,16),int(row['expected'],16))
 assert row['outputs']['candidate']==row['outputs']['parent']==row['outputs']['resident']
 if key in old:assert row['outputs']['parent']==old[key]['outputs']['candidate'] and row['instructions']['parent']==old[key]['instructions']['candidate']
 pi,ci,qi=(row['instructions'][n] for n in ['parent','candidate','Qfplib']);groups[key[1]]['equal' if ci==pi else 'slower' if ci>pi else 'faster']+=1
 if ci>pi:hist[ci-pi]+=1
 if row['correct']['Qfplib']:
  if pi>qi:ploss.add(row['x'])
  if ci>qi:closs.add(row['x'])
  if ci>qi>=pi:newloss.append(key)
assert len(old)==118044 and set(old)<=seen and len(seen)==120988
assert hist==Counter({3:5,4:2}) and len(ploss)==4 and len(closs)==3 and not newloss
assert ploss-closs=={'5FFA5B2647E9E2C7'}
out=dict(status='PASS_LN2_SIGN_RATIONAL_PROOF_AND_FULL_PRIVATE_BINDING',target={n:pin(P/n) for n in ['HANDOFF.md','result.json','native_eabi_m0_log70.inc','candidate.elf']},accepted_parent_chain_closure=pin(premise),sealed_artifacts=len(r['files']),input_pins=len(inputs),source_only_two_upper_predicates_and_static_assert=True,exact_inline_fragments_bound_to_unit=True,near_other_code_tables_ASM_BSS_deps_same=True,changed_allocated_sections=changed,code_growth_bytes=16,new_tables_RAM_libgcc=False,generic_M0_M4_controls_byteexact=True,M4_excluded_TUs_not_whole_build=True,actual_resident_bindings=39,L70=str(L70),L94=str(L94),Q94_minus_Q70_shifted=7924966,independent_log2_series_terms=64,ln2_Q70_error_lower=str(err_lo),ln2_Q70_error_upper=str(err_hi),ln2_Q70_error_float=[float(err_lo),float(err_hi)],exact_main_polynomial_bound=str(exact),raw_main_polynomial_bound=str(raw),word_product_nL70_exact=True,actual_k_domain=[-1022,1023],n0_new_gate_absent=True,near_error4_gate_absent=True,n_domain_checked=[1,1023],all_n_integer_interval_checks=checks,maximum_next_midpoint_reach={k:str(v) for k,v in worst.items()},next_midpoint_min_distance=2048,all_RNE_upper_and_next_midpoint_bounds_strict=True,whole_private_CPP_ASM_ELF_and_unit_rebuild_byteexact=True,rebuild_hashes=rebuilt,rebuild_commands=commands,static_assert_executable_bytes_equal_preassert=True,preassert_probes_not_qualified_again=True,saved_profile_recount=dict(parent_rows_retained=118044,total_rows=120988,groups={k:dict(v) for k,v in groups.items()},regression_histogram=dict(hist),old_raw_losses=4,new_raw_losses=3,fixed_raw='5FFA5B2647E9E2C7',new_correct_Qfp_deficits=0),hardware_accessed=False)
(O/'math-binding.json').write_text(json.dumps(out,indent=2)+'\n');print(json.dumps({k:v for k,v in out.items() if k not in ['rebuild_commands','ln2_Q70_error_lower','ln2_Q70_error_upper','maximum_next_midpoint_reach']},indent=2))

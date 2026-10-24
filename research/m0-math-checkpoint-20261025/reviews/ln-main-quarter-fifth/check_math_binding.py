"""Independent bounded quarter/fifth error and actual whole-ELF binding."""
from pathlib import Path
from collections import Counter
from fractions import Fraction as F
import hashlib,json,re,subprocess,sys
sys.dont_write_bytecode=True
from bounds import S,A,bounds,emitted,actual,remainders,bias,error_interval,predicate
R=Path('/Users/bolk/Projects/MK61S_MINI');P=R/'.build/m0-ln-main-quarter-fifth-20261024';PAR=R/'.build/m0-ln-main-ln2-sign-20261024';O=Path(__file__).resolve().parent
H=lambda p:hashlib.sha256(Path(p).read_bytes()).hexdigest()
def read(p):return json.loads(Path(p).read_text())
def pin(p):return dict(path=str(p),bytes=Path(p).stat().st_size,sha256=H(p))
assert H(P/'HANDOFF.md')=='37590bc6604dc21cca8362ca4712e6fb51caa9be2d03082282ce37b5f5062ca3'
assert H(P/'result.json')=='60c79f7973c18466d67d3f0d473cd63eb597f378ddb9bb53732edebde6caaf58'
r=read(P/'result.json')
for n,h in r['files'].items():assert H(P/n)==h,n
inputs=read(P/'input-pins.json')['files']
for n,h in inputs.items():assert H(R/n)==h,n
parent_review=R/'.build/m0-ln-main-ln2-sign-independent-20261024/FINAL-REVIEW.json'
assert H(parent_review)=='0581902367266ea7a154f15141ec40a1d27aeab9f9ff72033a3f535cc9a7f147'
assert r['parent_result_sha256']==H(PAR/'result.json') and (P/'control.elf').read_bytes()==(PAR/'candidate.elf').read_bytes()
source=(P/'native_eabi_m0_log70.inc').read_text();parent=(PAR/'native_eabi_m0_log70.inc').read_text()
def span(s,name):
 i=s.index(name+'(');start=s.rfind('__attribute__',0,i);a=s.index('{',i);end=a+1;d=1
 while d:d+=(s[end]=='{')-(s[end]=='}');end+=1
 return start,end
def fn(s,name):a,z=span(s,name);return s[a:z]
for name in ['ln_main_coefficient_accept','ln_pack70','ln_main_pack70']:assert fn(source,name)==fn((P/'pack-unit.cpp').read_text(),name)
# Remove just the new helper and two packer replacements, then reverse the
# exact metadata forwarding. The entire remaining source must be parent.
normal=source
helper='#if defined(MK61_M0_RP2040_EABI) && MK61_M0_RP2040_EABI\n// Only cold points need the exact fourth/fifth coefficient remainders.\n'+fn(source,'ln_main_coefficient_accept')+'\n#endif\n'
assert normal.count(helper)==1;normal=normal.replace(helper,'')
for name in ['ln_pack70','ln_main_pack70']:normal=normal.replace(fn(normal,name),fn(parent,name))
for new,old in [(',x,fourth,fifth);',',x);')]:normal=normal.replace(new,old)
pattern=r'#if defined\(MK61_M0_RP2040_EABI\) && MK61_M0_RP2040_EABI\n(  (?:if\(!k\) )?return ln_pack70\([^\n]+,uint32_t\(h\),fourth,fifth\);)\n#else\n(  (?:if\(!k\) )?return ln_pack70\([^\n]+\);)\n#endif'
seen=[]
def undo(m):
 assert m[1].replace(',uint32_t(h),fourth,fifth);',');')==m[2];seen.append(m[1]);return m[2]
normal=re.sub(pattern,undo,normal);assert len(seen)==2 and normal==parent
for n in ['native_eabi_m0.cpp','native_eabi_m0_log70_center.inc','native_eabi_m0_log70_ratio.inc','native_eabi_m0_log_subnormal.inc','native_eabi_m0_log10.inc','ratio.S']:assert (P/n).read_bytes()==(PAR/n).read_bytes(),n
# Independent interval arithmetic sums each signed source-operation error.
bands={}
for minimum in [2049,2081,3585]:
 b=bounds(minimum);bands[str(minimum)]={k:([str(v[0]),str(v[1])] if isinstance(v,tuple) else str(v)) for k,v in b.items()}
 for negative in [False,True]:
  L,U=actual(minimum,negative);lr,ur=emitted(minimum,negative);assert L<lr and U<ur
 # Both shifted operands of actual fourth/fifth products fit32bits.
 assert (S*b['h'])/(1<<27)<1<<33
 assert (S*b['h']**3+b['cube'])/64<1<<32
 assert S*b['h']**4+b['fourth_upper']<1<<32
# The actual rounded argument is below1/2048 strictly, making t<2^32.
assert F(1,2049)+A/S<F(1,2048)
# 52429=(2^18+1)/5: quotient fraction at most4/5, added error<1/5.
# Thus the multiply-shift equals floor((fifth+2)/5) for ALL fifth<65536.
assert 5*52429==(1<<18)+1 and F(65537,5*(1<<18))<F(1,5)
assert 65537*52429<1<<32
for v in [0,1,2,3,4,5,65530,65531,65532,65533,65534,65535]:
 assert ((v+2)*52429>>18)==(v+2)//5
for v in range(4):assert ((v+2)&3)-2==v-4*((v+2)//4)
# Source nearest /3 uses exact word quotients and final residue>=2.
assert 3*0xAAAAAAAB==(1<<33)+1 and F((1<<32)-1,3*(1<<33))+F(2,3)<1
for rh in range(3):
 for rl in range(3):assert ((rh+rl)//3,(rh+rl)%3)==(int(rh+rl>=3),rh+rl-3*int(rh+rl>=3))
# Host checks all actual denominator bands and parity recovery, not an ARM sweep.
for den in range(2049,4096,2):
 minimum=3585 if den>=3585 else 2081 if den>=2081 else 2049
 assert F(1,den)+A/S<F(1,minimum-1) and A*den<32768
 for negative in [False,True]:assert all(x<y for x,y in zip(actual(den,negative),emitted(den,negative)))
for k in range(-1022,1024):assert 2*((abs(k)+1)//2)-(((k+1023)^1)&1)==abs(k)
# Restore coefficient extrema for the cheaper gates. Exact argument is
# floor(H)+1, so its log error is one-sided, bounded by1/(1-hmax).
b=bounds(2049);N=b['nonlinear'];h=b['h'];pl,pu=b['positive'];nl,nu=b['negative']
cheap=dict(raw_positive_lower=pl+F(9,10),raw_negative_lower=nl+F(9,10),raw_positive_upper=pu+F(13,20),raw_negative_upper=nu+F(13,20),exact_positive_lower=pl-N+F(9,10),exact_negative_lower=nl-N+F(9,10)+1/(1-h),exact_positive_upper=pu-N+F(13,20)+1/(1-h),exact_negative_upper=nu-N+F(13,20))
for name,limit in [('raw_positive_lower',4),('raw_negative_lower',3),('raw_positive_upper',6),('raw_negative_upper',6),('exact_positive_lower',4),('exact_negative_lower',4),('exact_positive_upper',7),('exact_negative_upper',6)]:assert cheap[name]<limit
# Endpoint: index<=31/den<=2111, offset_hi>=1022 implies H>=Hmin.
# Raw h may be below H: use Hmin-A/S, not the producer's unadjusted Hmin.
minimum_H=F(255,256*2111);minimum_raw_h=minimum_H-A/S;assert minimum_raw_h>0
endpoint_raw=S*minimum_raw_h**6/(6*(1+h));endpoint_exact=S*minimum_H**6/(6*(1+h))
assert cheap['raw_positive_lower']-endpoint_raw<1 and cheap['exact_positive_lower']-endpoint_exact<1
cheap['endpoint_raw_lower_after_remainder']=cheap['raw_positive_lower']-endpoint_raw
cheap['endpoint_exact_lower_after_remainder']=cheap['exact_positive_lower']-endpoint_exact
# Global predicate proof uses strict L/U radii: satisfying the emitted
# interval at d implies the true error lies strictly within (-d,d) on the
# relevant side. Check adverse endpoints and equality around all biases.
checks=0;biases=set()
for den in [2049,2079,2081,3583,3585,4095]:
 edge=(A*den).__ceil__()-1
 for negative in [False,True]:
  for sign in [False,True]:
   for n in [0,1,1023]:
    for f4 in range(4):
     for f5 in range(5):
      biases.add(bias(f4,f5,negative))
      for residue in [-edge,0,edge]:
       elo,ehi=error_interval(sign,n,den,residue,negative,f4,f5)
       L,U=emitted(den,negative);B=bias(f4,f5,negative)
       if sign:L,U=U,L;B=-B
       ori=-residue if negative!=sign else residue
       for above,bound in [(True,U+B-F(ori,den)),(False,L-B+F(ori,den)+F(n,2))]:
        critical=-((-bound.numerator)//bound.denominator)
        for d in {max(0,critical-1),max(0,critical),max(0,critical+1)}:
         ok=predicate(d,above,sign,n,den,residue,negative,f4,f5)
         if ok:assert (ehi<d if above else elo>-d)
         checks+=1
assert max(abs(x) for x in biases)==F(9,10)
max_expr=(40*527+190+20*1023)*4095+36*4095+40*((A*4095).__ceil__()-1)
assert max_expr<1<<28
max_error=F(19,4)+F(9,10)+A+F(1023,2)
assert max_error<1024 and max_error-F(1022,2)<512
sys.path.insert(0,str(R/'tests'));from check_stm32_vectors import ElfImage
def alloc(e):return {n:('NOBITS',s[5]) if s[1]==8 else ('BYTES',e.bytes_at(s)) for n,s in e.named_sections.items() if s[2]&2}
aa,bb=alloc(ElfImage(P/'control-full.o')),alloc(ElfImage(P/'candidate-full.o'))
changed={n:[len(aa.get(n,('BYTES',b''))[1]),len(bb.get(n,('BYTES',b''))[1])] for n in aa.keys()|bb.keys() if aa.get(n)!=bb.get(n)}
assert changed=={'.text.ln_main_raw':[1368,1744],'.text.mk61_m0_ln_positive':[1272,1784]}
c,p=ElfImage(P/'candidate.elf'),ElfImage(P/'control.elf');assert c.bytes_at(c.named_sections['.rodata'])==p.bytes_at(p.named_sections['.rodata'])
assert (P/'candidate-ratio.o').read_bytes()==(P/'control-ratio.o').read_bytes()
for n in ['generic_M0','M4_soft','M4_hard']:assert (P/(n+'-candidate.o')).read_bytes()==(P/(n+'-control.o')).read_bytes()==(PAR/(n+'-candidate.o')).read_bytes()
resident=ElfImage(R/'.build/m0-asin-scaled-bound-v164-20261023/firmware/mk61s-picocalc-pico-h.elf');bindings=read(P/'candidate-build.json')['resident_bindings']
for n,a in bindings.items():assert resident.symbols[n if n not in ['memcpy','memset'] else '__wrap_'+n]==a,n
(O/'rebuild').mkdir(exist_ok=True);commands=[];rebuilt={}
for manifest,names in [('candidate-build.json',['candidate-full.o','candidate-ratio.o','candidate.elf']),('pack-unit-build.json',['pack-unit.o','pack-unit.elf'])]:
 replacements={str(P/n):str(O/'rebuild'/n) for n in names}
 for command in read(P/manifest)['commands']:
  argv=[replacements.get(x,x) for x in command];p=subprocess.run(argv,capture_output=True);assert p.returncode==0,p.stderr.decode();commands.append(argv)
 for n in names:assert (P/n).read_bytes()==(O/'rebuild'/n).read_bytes(),n;rebuilt[n]=H(O/'rebuild'/n)
# Recount saved rows, never relabel old controls or parent regressions away.
q=read(P/'qualification.json');prior={(x['x'],x['SIO']):x for x in read(PAR/'qualification.json')['rows']};seen=set();hist=Counter();groups={s:Counter() for s in ['READY','DIRTY']};ploss=set();closs=set();newloss=[]
def eq(a,b):return a==b or ((a&0x7fffffffffffffff)>0x7ff0000000000000 and (b&0x7fffffffffffffff)>0x7ff0000000000000)
for row in q['rows']:
 key=row['x'],row['SIO'];assert key not in seen;seen.add(key)
 for n,v in row['outputs'].items():assert row['correct'][n]==eq(int(v,16),int(row['expected'],16))
 assert row['outputs']['candidate']==row['outputs']['parent']==row['outputs']['resident']
 if key in prior:assert row['instructions']['parent']==prior[key]['instructions']['candidate'] and row['outputs']['parent']==prior[key]['outputs']['candidate']
 pi,ci,qi=(row['instructions'][n] for n in ['parent','candidate','Qfplib']);groups[key[1]]['equal' if ci==pi else 'slower' if ci>pi else 'faster']+=1
 if ci>pi:hist[ci-pi]+=1
 if row['correct']['Qfplib']:
  if pi>qi:ploss.add(row['x'])
  if ci>qi:closs.add(row['x'])
  if ci>qi>=pi:newloss.append(key)
assert len(prior)==120988 and set(prior)<=seen and len(seen)==177178
assert sum(hist.values())==85604 and dict(sorted(hist.items()))=={int(k):v for k,v in sorted(r['regression_instruction_histogram'].items(),key=lambda x:int(x[0]))}
assert len(ploss)==14 and len(closs)==5 and len(ploss-closs)==9 and not newloss
endpoint=read(R/'.build/m0-ln-main-endpoint-lower-20261024/probe.json');endpoint_losses={x['x'] for x in endpoint['rows'] if x['correct']['Qfplib'] and x['instructions']['parent']>x['instructions']['Qfplib']};assert len(endpoint_losses)==7 and endpoint_losses<=ploss-closs
out=dict(status='PASS_INDEPENDENT_QUARTER_FIFTH_BOUNDS_AND_WHOLE_PRIVATE_BINDING',target={n:pin(P/n) for n in ['HANDOFF.md','result.json','native_eabi_m0_log70.inc','candidate.elf']},accepted_parent_review=pin(parent_review),sealed_artifacts=len(r['files']),input_pins=len(inputs),source_other_than_helper_packers_and_metadata_forwarding_exact_parent=True,exact_inline_unit_functions=True,bands=bands,cheap_bounds={k:str(v) for k,v in cheap.items()},endpoint_raw_h_bound_corrected_for_seed_error=True,endpoint_raw_remainder=str(endpoint_raw),endpoint_exact_remainder=str(endpoint_exact),producer_Hmin_to_computed_h_difference_float=float(endpoint_exact-endpoint_raw),fifth_division_proven_for_all65536_values_without_sweep=True,nearest_third_word_division_error_at_most_one_third=True,all2046_normal_k_parity_cases=True,all1024_den_band_ranges=True,signed_residue_abs_below=32768,independent_adverse_interval_gate_checks=checks,exact_bias_range=[str(min(biases)),str(max(biases))],max_signed_gate_expression_abs_bound=max_expr,neighbor_midpoint_bound=str(max_error),lowest_binade_neighbor_gap_safe=True,changed_allocated_sections=changed,object_linked_growth_bytes=888,no_new_tables_RAM_libgcc=True,other_allocated_sections_near_Q77_tables_ASM_equal=True,generic_M0_M4_controls_byteexact=True,M4_excluded_TU_not_whole_build=True,actual_resident_bindings=39,whole_CPP_ASM_entire_ELF_and_unit_rebuild_byteexact=True,rebuild_hashes=rebuilt,rebuild_commands=commands,saved_accounting=dict(parent_rows_retained=120988,total_rows=177178,groups={k:dict(v) for k,v in groups.items()},parent_regression_rows=85604,regression_histogram=dict(hist),expanded_parent_raw_losses=14,child_raw_losses=5,fixed_raw_losses=9,new_correct_Qfp_deficits=0,all7_earlier_endpoint_probe_parent_losses_fixed=True,additional_old_control_losses_beyond_endpoint_probe=sorted(ploss-endpoint_losses),remaining_raw_inputs=sorted(closs)),author_stack_cost=dict(child=648,parent=640,bare=72),hardware_accessed=False)
(O/'math-binding.json').write_text(json.dumps(out,indent=2)+'\n');print(json.dumps({k:v for k,v in out.items() if k not in ['rebuild_commands','bands','endpoint_raw_remainder','endpoint_exact_remainder']},indent=2))

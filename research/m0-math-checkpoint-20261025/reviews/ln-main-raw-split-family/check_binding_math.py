"""Independent source-bound residual proof and private artifact binding only."""
from pathlib import Path
from fractions import Fraction as F
from collections import Counter
import hashlib,json,struct,subprocess,sys
sys.dont_write_bytecode=True
ROOT=Path('/Users/bolk/Projects/MK61S_MINI')
P=ROOT/'.build/m0-ln-main-raw-split-family-20261024'
PAR=ROOT/'.build/m0-log-ratio-small-limb-20261024'
O=Path(__file__).resolve().parent
H=lambda p:hashlib.sha256(Path(p).read_bytes()).hexdigest()
def read(p):return json.loads(Path(p).read_text())
def pin(p):return dict(path=str(p),bytes=Path(p).stat().st_size,sha256=H(p))
assert H(P/'HANDOFF.md')=='a9222d24f1dd4491667b697ade1f0a378d8bf5750ce293eaaac73efda157dc2b'
assert H(P/'result.json')=='406533549b8d7bf94fcd95e7fe396497561f91590df6096d74bec1dde1caad82'
r=read(P/'result.json')
for name,digest in r['files'].items():assert H(P/name)==digest,name
inputs=read(P/'input-pins.json')['files']
for name,digest in inputs.items():assert H(ROOT/name)==digest,name
review=ROOT/'.build/m0-log-ratio-small-limb-independent-20261024/FINAL-REVIEW.json'
assert read(review)['target']['result.json']['sha256']==r['parent_result_sha256']==H(PAR/'result.json')
assert (P/'control.elf').read_bytes()==(PAR/'candidate.elf').read_bytes()
source=(P/'native_eabi_m0_log70.inc').read_text();parent=(PAR/'native_eabi_m0_log70.inc').read_text()
entry='__attribute__((optimize("Os"))) MK61_SOFT_PCS double mk61_m0_ln(double x) {'
a=source.index('#if defined(MK61_M0_RP2040_EABI) && MK61_M0_RP2040_EABI\n// The exact signed h residual')
b=source.index(entry,a)
assert source[:a]==parent[:parent.index(entry)]
dispatch='''#if defined(MK61_M0_RP2040_EABI) && MK61_M0_RP2040_EABI
  if(uint32_t(uint32_t(b)+64U)>128U &&
      (*reinterpret_cast<volatile uint32_t*>(UINT32_C(0xD0000078))&2U)) return ln_main_raw(b);
#endif
'''
assert source[b:].count(dispatch)==1 and source[b:].replace(dispatch,'')==parent[parent.index(entry):]
def body(text,name):
 start=text.index(name+'(');start=text.index('{',start);depth=1;end=start+1
 while depth:depth+=(text[end]=='{')-(text[end]=='}');end+=1
 return text[start:end]
old=body(parent,'mk61_m0_ln');old=old[old.index('  const int k='):]
raw=body(source,'ln_main_raw');raw=raw[raw.index('  const int k='):]
assert raw.count('const U h=mk61_m0_log_product46(delta,reciprocal);')==1
old=old.replace('  const U h=log70_residual(delta,index);','  const uint32_t* row=log10_table[index];\n  const U reciprocal=(U(row[1])<<32)|(row[0]&~63U);\n  const U h=mk61_m0_log_product46(delta,reciprocal);')
old=old.replace('return ln_pack70(low,high,0,ln_main_radius,x);','return ln_main_pack70(low,high,0,0,uint32_t(h),x);').replace('return ln_pack70(result,upper,k<0?D::Sign:0,ln_main_radius+(n+1)/2,x);','return ln_main_pack70(result,upper,k<0?D::Sign:0,(n+1)/2,uint32_t(h),x);')
assert old==raw
for name in ['native_eabi_m0.cpp','native_eabi_m0_log70_center.inc','native_eabi_m0_log70_ratio.inc','native_eabi_m0_log_subnormal.inc','native_eabi_m0_log10.inc','ratio.S']:assert (P/name).read_bytes()==(PAR/name).read_bytes(),name
assert body((P/'pack-unit.cpp').read_text(),'ln_main_pack70')==body(source,'ln_main_pack70')
sys.path.insert(0,str(ROOT/'tests'));from check_stm32_vectors import ElfImage
def alloc(e):return {n:('NOBITS',s[5]) if s[1]==8 else ('BYTES',e.bytes_at(s)) for n,s in e.named_sections.items() if s[2]&2}
candidate=ElfImage(P/'candidate.elf');control=ElfImage(P/'control.elf')
resident=ElfImage(ROOT/'.build/m0-asin-scaled-bound-v164-20261023/firmware/mk61s-picocalc-pico-h.elf')
bindings=read(P/'candidate-build.json')['resident_bindings']
for name,address in bindings.items():
 actual=resident.symbols.get(name if name not in ['memcpy','memset'] else '__wrap_'+name)
 assert actual==address,(name,address,actual)
aa,bb=alloc(ElfImage(P/'control-full.o')),alloc(ElfImage(P/'candidate-full.o'))
changed={n:[len(aa.get(n,('BYTES',b''))[1]),len(bb.get(n,('BYTES',b''))[1])] for n in aa.keys()|bb.keys() if aa.get(n)!=bb.get(n)}
assert changed=={'.text.mk61_m0_ln':[1272,1300],'.text.ln_main_raw':[0,1356]},changed
assert candidate.bytes_at(candidate.named_sections['.rodata'])==control.bytes_at(control.named_sections['.rodata'])
assert (P/'candidate-ratio.o').read_bytes()==(P/'control-ratio.o').read_bytes()==(PAR/'candidate-ratio.o').read_bytes()
def symbol_bytes(e,part,size):
 n=next(n for n in e.symbols if part in n and e.sizes.get(n)==size);address=e.symbols[n]
 sec=next(s for s in e.named_sections.values() if s[3]<=address<address+size<=s[3]+s[5]);return e.bytes_at(sec)[address-sec[3]:address-sec[3]+size]
table=symbol_bytes(candidate,'log10_table',16384)
for index in range(1024):
 lo,hi,_,_=struct.unpack_from('<4I',table,index*16);R=(hi<<32)|(lo&~63);den=2049+2*index
 assert R==((1<<75)//den)&~63
# Existing retained9-product lemma: omitted16bit products00,01,10 have
# total below2^49+2^32, followed by half-up rounding AND source +4 bias.
# Bias recenters the missing interval [0,8+2^-14) around4.
omitted=F((1<<49)+(1<<32),1<<46)
product=max(F(9,2),omitted-4+F(1,2))
A=product+2 # R rounds down by less64, delta<=2^41 => argument error<2.
assert A==F(106497,16384)
# Re-derive the error excluding the SIGNED LINEAR argument term; shared
# polynomial operation bounds are the exact accepted parent operations.
S=1<<70;h=F(1,2048);square=1+F(1,1<<16);cube=F(35,64)+h*square
third=F(1,2)+cube/3
fourth=1+63*h*64+S*h**3/F(1<<43)+h*cube
fifth=1+h*fourth+S*h**4/F(1<<43);c=F(52429,1<<18)
fifth_term=c*fifth+max(2*c+(c-F(1,5))*S*h**5,1-2*c)
series_tail=S*h**6/(6*(1-h))
B=A*h/(1-h)+F(1,2)+(F(1,2)+square/2)+third+(F(1,2)+fourth/4)+fifth_term+series_tail
assert B<7 and A+B<16 and F(1,2049)+A/S<h
assert (A*4095).__ceil__()<=32768
# r is actual exact delta*2^29-h*den. Its small absolute value means the
# low-word modular subtraction, then target signed conversion recovers r.
# The test is sufficient for every residual, since error=-v*r/den+e,
# |e|<B+extra. Algebraic substitution reduces the accepted upper/lower
# endpoint to (7-B)>0, even at equality in the integer predicate.
gate_checks=0
for den in [2049,2051,3071,4093,4095]:
 edge=(A*den).__ceil__()-1
 for extra in [0,1,2,255,511,512]:
  for residue in [-edge,-1,0,1,edge]:
   assert -(1<<15)<residue<(1<<15)
   for orientation in [-1,1]:
    error=-orientation*F(residue,den)
    for distance in [0,1,6+extra,7+extra,8+extra,15+extra,16+extra]:
     if distance and den*(distance-7-extra)+orientation*residue>=0:assert error+B+extra<distance
     if distance and den*(distance-7-extra)-orientation*residue>=0:assert error-B-extra>-distance
     gate_checks+=2
# No signed overflow/invalid shift in the admitted general-normal domain.
assert 519*4095+(A*4095).__ceil__()<(1<<22)
assert F(1,65)*S-528>(1<<63) # excluded x near1 => magnitude width>=64
assert sum(F(7,10)**j/F([1,1,2,6,24][j]) for j in range(5))>2 # exp(.7)>2 => ln2<.7
assert 1024*F(7,10)*S+528<(1<<80)
assert 17<512 and 528<1024 # lower binade half-cell width64 vs widths>=65
assert F(1,2)*S-528>(1<<68) # k>=1 or k<=-2 cannot produce width64
for lo in [0,1,63,64,65,0x7fffffff,0xffffffbf,0xffffffc0,0xffffffc1,0xffffffff]:
 family=((lo+64)&0xffffffff)<=128
 assert family==(lo<=64 or lo>=0xffffffc0)
 assert family==((((-lo)&0xffffffff)+64)&0xffffffff<=128)
# Independently rebuild complete private objects/ELF and exact pack unit.
(O/'rebuild').mkdir(exist_ok=True);commands=[];rebuilt={}
for manifest,names in [('candidate-build.json',['candidate-full.o','candidate-ratio.o','candidate.elf']),('pack-unit-build.json',['pack-unit.o','pack-unit.elf'])]:
 replacements={str(P/n):str(O/'rebuild'/n) for n in names}
 for command in read(P/manifest)['commands']:
  argv=[replacements.get(x,x) for x in command];p=subprocess.run(argv,capture_output=True);assert p.returncode==0,p.stderr.decode();commands.append(argv)
 for n in names:assert (O/'rebuild'/n).read_bytes()==(P/n).read_bytes(),n;rebuilt[n]=H(O/'rebuild'/n)
contexts={}
for name in ['generic_M0','M4_soft','M4_hard']:
 assert alloc(ElfImage(P/(name+'-control.o')))==alloc(ElfImage(P/(name+'-candidate.o')))
 contexts[name]=dict(allocated_bytes=sum(s[5] for s in ElfImage(P/(name+'-candidate.o')).named_sections.values() if s[2]&2),identical=True,whole_platform_qualification=False)
# Saved profile accounting is recomputed, NOT replayed ARM or MPFR corpus.
q=read(P/'qualification.json');prior={(r['x'],r['SIO']):r for r in read(PAR/'qualification.json')['rows']};seen=set();groups={s:Counter() for s in ['READY','DIRTY']};reg=Counter();ploss=set();closs=set();fixed=set();new=[]
def numeq(a,b):return a==b or ((a&0x7fffffffffffffff)>0x7ff0000000000000 and (b&0x7fffffffffffffff)>0x7ff0000000000000)
for row in q['rows']:
 key=row['x'],row['SIO'];assert key not in seen;seen.add(key)
 for n,value in row['outputs'].items():assert row['correct'][n]==numeq(int(value,16),int(row['expected'],16))
 assert row['outputs']['candidate']==row['outputs']['parent']==row['outputs']['resident']
 if key in prior:assert row['instructions']['parent']==prior[key]['instructions']['candidate'] and row['outputs']['parent']==prior[key]['outputs']['candidate']
 pi,ci,qi=(row['instructions'][n] for n in ['parent','candidate','Qfplib'])
 groups[key[1]]['faster' if ci<pi else 'slower' if ci>pi else 'equal']+=1
 if ci>pi:reg[ci-pi]+=1
 if row['correct']['Qfplib']:
  if pi>qi:ploss.add(row['x'])
  if ci>qi:closs.add(row['x'])
  if ci>qi>=pi:new.append(key)
assert set(prior)<=seen and len(prior)==68876 and len(seen)==97536
assert reg==Counter({4:32670,8:12096})
assert len(ploss)==73 and len(closs)==49 and len(ploss-closs)==24 and not new
out=dict(status='PASS_SOURCE_DERIVED_RAW_MAIN_RESIDUAL_PROOF_AND_WHOLE_PRIVATE_ELF_BINDING',target={n:pin(P/n) for n in ['HANDOFF.md','result.json','native_eabi_m0_log70.inc','candidate.elf']},accepted_parent_review=pin(review),sealed_artifacts=len(r['files']),input_pins=len(inputs),same_parent_control_ELF=True,source_isolation_exact=True,exact_polynomial_retained=True,exact_inline_pack_unit=True,changed_allocated_sections=changed,other_allocated_code_data_BSS_same=True,ratio_ASM_same=True,new_tables_RAM_dependencies=False,contexts=contexts,actual_resident_bindings_verified=len(bindings),memcpy_memset_actual_wrap_aliases=True,actual_reciprocal_rows_checked=1024,seed_product_bound=str(product),total_argument_bound=str(A),nonlinear_and_rounding_base=str(B),full_generic_bound=str(A+B),base_float=float(B),full_float=float(A+B),independent_extreme_gate_checks=gate_checks,gate_algebra_all_residuals='Upper/lower predicate substitutes to distance-error>(7-B)+nonnegative/den>0, for all integer residuals, all den2049..4095, extra0..512.',signed_low32_exact_residual_bound=32768,maximum_integer_gate_abs_below=1<<22,valid_pack_widths=[64,80],valid_pack_shifts=[11,27],lowest_binade_half_cell_correlation=True,full_rebuild_byteexact=True,rebuild_hashes=rebuilt,rebuild_commands=commands,saved_accounting=dict(retained_parent_rows=68876,all_rows=97536,groups={k:dict(v) for k,v in groups.items()},regression_histogram=dict(reg),expanded_parent_raw_losses=73,expanded_child_raw_losses=49,fixed_raw=24,new_raw_losses=0),hardware_accessed=False,whole_ln_speed_GO=False)
(O/'math-binding.json').write_text(json.dumps(out,indent=2)+'\n');print(json.dumps({k:out[k] for k in ['status','sealed_artifacts','input_pins','base_float','full_float','saved_accounting']},indent=2))

from pathlib import Path
from fractions import Fraction as F
import json,hashlib,sys,struct,re,subprocess
sys.dont_write_bytecode=True
ROOT=Path('/Users/bolk/Projects/MK61S_MINI');P=ROOT/'.build/m0-ln-near-q77-linear-20261024';O=Path(__file__).resolve().parent;PAR=ROOT/'.build/m0-ln-raw-cold-entry-20261024'
H=lambda p:hashlib.sha256(Path(p).read_bytes()).hexdigest()
def read(p):return json.loads(Path(p).read_text())
def pin(p):return dict(path=str(p),sha256=H(p))
assert H(P/'HANDOFF.md')=='9eca0b99b5ac212d605a22e054dc15afe784fac61ea6e9e52783ffbb35566b19' and H(P/'result.json')=='87b5b9e32fd6465aefabcd81db263745aa2f789ba72857c3777d060f3e11f191'
r=read(P/'result.json');files=r['files']
for name,digest in files.items():
 expected=digest if isinstance(digest,str) else digest['sha256'];assert H(P/name)==expected,name
inputs=read(P/'input-pins.json')['files']
for name,digest in inputs.items():assert H(ROOT/name)==digest,name
source=(P/'native_eabi_m0_log70.inc').read_text();start=source.index('#if defined(MK61_M0_RP2040_EABI) && MK61_M0_RP2040_EABI\nstatic constexpr int8_t ln_near_q77_delta');end=source.index('__attribute__((optimize("Os"),noinline)) static double ln_near_interval(',start)
new_block=source[start:end];rest=source[:start]+source[end:];dispatch='#if defined(MK61_M0_RP2040_EABI) && MK61_M0_RP2040_EABI\n    return ln_near_interval77(x,b);\n#else\n    return ln_near_interval(x,b);\n#endif'
assert rest.count(dispatch)==1 and rest.replace(dispatch,'    return ln_near_interval(x,b);')==(PAR/'native_eabi_m0_log70.inc').read_text()
for name in ['native_eabi_m0.cpp','native_eabi_m0_log70_center.inc','native_eabi_m0_log70_ratio.inc','native_eabi_m0_log_subnormal.inc','native_eabi_m0_log10.inc']:assert (P/name).read_bytes()==(PAR/name).read_bytes(),name
sys.path.insert(0,str(ROOT/'tests'));from check_stm32_vectors import ElfImage
candidate=ElfImage(P/'candidate.elf');parent=ElfImage(P/'control.elf')
def allocated(e):return {n:e.bytes_at(s) for n,s in e.named_sections.items() if s[2]&2 and s[1]!=8}
a,b=allocated(ElfImage(P/'candidate-full.o')),allocated(ElfImage(P/'control-full.o'));changed={k:(len(b.get(k,b'')),len(a.get(k,b''))) for k in a.keys()|b.keys() if a.get(k)!=b.get(k)}
assert changed=={'.rodata._ZL17ln_near_q77_delta':(0,256),'.text.ln_near_interval':(1160,0),'.text.ln_near_interval77':(0,1356)},changed
for name in ['generic_M0','M4_soft','M4_hard']:assert allocated(ElfImage(P/(name+'-candidate.o')))==allocated(ElfImage(P/(name+'-control.o')))
assert (P/'candidate-ratio.o').read_bytes()==(P/'control-ratio.o').read_bytes()
def symbytes(e,part,size):
 key=next(n for n in e.symbols if part in n and e.sizes.get(n)==size);addr=e.symbols[key];sec=next(s for s in e.named_sections.values() if s[3]<=addr<addr+size<=s[3]+s[5]);return e.bytes_at(sec)[addr-sec[3]:addr-sec[3]+size]
table=symbytes(candidate,'log_near_table',4096);assert table==symbytes(parent,'log_near_table',4096)
corrections=list(struct.unpack('<256b',symbytes(candidate,'ln_near_q77_delta',256)))
def nearest(q):
 n,d=q.numerator,q.denominator;v,t=divmod(n,d);return v+(2*t>d or (2*t==d and v&1))
def ln_abs_interval(c):
 y=abs((c-1)/(c+1));term=y;total=F(0)
 for k in range(20):total+=2*term/(2*k+1);term*=y*y
 tail=2*term/((41)*(1-y*y));return total,total+tail
for i in range(256):
 reciprocal,c70=struct.unpack_from('<QQ',table,16*i);den=8065+i;c=F(den,8192);lo,hi=ln_abs_interval(c)
 assert reciprocal==nearest(F(1<<75,den))
 assert nearest(lo*(1<<70))==nearest(hi*(1<<70))==c70
 c77=nearest(lo*(1<<77));assert c77==nearest(hi*(1<<77))==(c70<<7)+corrections[i]
 assert -64<=corrections[i]<=64 and 0<=((c70<<7)&((1<<64)-1))+corrections[i]<1<<64
# Derive the unchanged nine-product seed bound: omitted base2^16 digits
#00,01,10 total <2^49+2^32; half-up rounding adds at most1/2.
seed=F(1,2)+F((1<<49)+(1<<32),1<<54);old_error=seed+F(1,128);A=old_error*128
assert seed==F(17,32)+F(1,1<<22)
arg=F(1,2)+A*8320*F(3,4)/(1<<24)
for den in range(8065,8321):assert abs(F(4096-(den>>2))-F(1<<24,den))<F(3,4)
assert A*8320<1<<20 and A*8320*2080+(1<<23)<1<<31 and arg*8320<1<<13
S=1<<77;h=F(1,16000);assert h-F(1,16130)>arg/S
z=F(1)+F(1,8192)
# An independent coarse limb bound for both truncated cube cross terms;
# it is below1/512 without depending on the author's split of constants.
trunc_cube=(F(131072)+F(114689)+1)/(1<<27);assert trunc_cube<F(1,512)
cube=F(1,2)+F(1,512)+h*z
fourth=F(1,2)+(2*S*h*h*z+z*z)/S+(2*(S*h*h+z)/(1<<19)+1)/(1<<39)
fifth=F(1,2)+F(1,32)+h*fourth;tail=S*h**6/(6*(1-h));base=F(1,2)+arg*h/(1-h)+z/2+cube/3+fourth/4+fifth/5+tail
biases={5*(-4*r3+s*(6*r2+3*r4))-12*r5 for r2 in(-1,0) for r3 in(-1,0,1) for r4 in(-2,-1,0,1) for r5 in(-2,-1,0,1,2) for s in(-1,1)};assert max(map(abs,biases))==104
full=base+arg+F(104,60);assert base<F(3,2) and full<4
u=F(1<<38,S)+arg/S;linear=F(1,2)+S*u*u/(2*(1-u));assert linear<F(751,1000) and linear<base
assert S*h+arg<1<<64 and S*h*h+z<1<<50 and S*h**3+cube<9*(1<<32) and S*h**4+fourth<1<<22 and S*h**5+fifth<145
assert ((S*h)/(1<<32)).__ceil__()*((S*h*h+z)/(1<<18)).__ceil__()+2*((1<<16)-1)**2+(1<<26)<1<<64
# For each possible coefficient bias, every residual between its extrema is
#affine. Endpoint verification therefore covers the entire integer interval.
gates=0
for den in range(8065,8321):
 edge=(arg*den).__ceil__()-1
 for r0 in[-edge,0,edge]:
  for bias in biases:
   e=F(bias,60)-F(r0,den);assert e+base<4 and e-base>-4
   for d in [1,2,3]:
    if den*(60*d-bias)+60*r0>=90*den:assert e+base<d
    if den*(60*d+bias)-60*r0>=90*den:assert e-base>-d
    gates+=2
assert 4<256 and (F(1,16384)-F(1,16384)**2/2)*S-4>(1<<62)+4
# Bind full source+ASM to the entire ELF, not just selected symbol bodies.
build=read(P/'candidate-build.json');(O/'rebuild').mkdir(exist_ok=True)
replacements={str(P/n):str(O/'rebuild'/n) for n in ['candidate-full.o','candidate-ratio.o','candidate.elf']};commands=[]
for command in build['commands']:
 argv=[replacements.get(x,x) for x in command];proc=subprocess.run(argv,capture_output=True);commands.append(dict(argv=argv,exit=proc.returncode));assert proc.returncode==0,proc.stderr.decode()
for name in ['candidate-full.o','candidate-ratio.o','candidate.elf']:assert (O/'rebuild'/name).read_bytes()==(P/name).read_bytes(),name
out=dict(status='PASS_BOUNDED_SOURCE_DERIVED_Q77_MATH_AND_FULL_ELF_BINDING_WITH_PARENT_SCOPE_OPEN',source=pin(P/'native_eabi_m0_log70.inc'),ELF=pin(P/'candidate.elf'),sealed_files=len(files),input_pins=len(inputs),changed_allocated_sections=changed,only_near_source_delta_vs_private_parent=True,shared_tables_and_generic_M0_M4_controls_equal=True,own_whole_object_ASM_ELF_rebuild_exact=True,build_commands=commands,own_table_rows_exact_Fraction=256,source_bound_seed_error=str(seed),corrected_argument_error=str(arg),symmetric_base=str(base),full_error=str(full),linear_base=str(linear),coarse_cube_truncation_bound=str(trunc_cube),pack_gate_extreme_checks=gates,unchanged_seed_lemma='Nine retained16bit digit products; three omitted products <2^49+2^32, then half-up54bit rounding. Reciprocal RNE contributes<=1/128.',parent_main_raw_split_and_cold_entry_independently_accepted=False,public_ln_global_correctness_and_totality_not_conferred=True,hardware_accessed=False)
(O/'math-binding.json').write_text(json.dumps(out,indent=2)+'\n');print(json.dumps(dict(status=out['status'],source_files=len(inputs),table_rows=256,base=float(base),full=float(full),linear=float(linear),gate_checks=gates),indent=2))

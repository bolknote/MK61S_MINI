"""Exact rational adaptive exp error certificate and literal ARM unit."""
from pathlib import Path
from fractions import Fraction as F
import ast,copy,hashlib,json,re,shlex,struct,subprocess,sys
sys.dont_write_bytecode=True
W=Path(__file__).resolve().parent;ROOT=W.parents[1];P=ROOT/'.build/m0-asin-scaled-bound-v164-20261023'
sys.path.insert(0,str(ROOT/'tests'))
from check_stm32_vectors import ElfImage
sha=lambda p:hashlib.sha256(p.read_bytes()).hexdigest()
build=json.loads((W/'build.json').read_text());assert sha(W/'candidate/native_eabi_m0.cpp')==build['source_sha256']
tool=ROOT/'tools/certify_m0_exp_fast.py';fn=copy.deepcopy(next(n for n in ast.parse(tool.read_text()).body if isinstance(n,ast.FunctionDef) and n.name=='certificate'))
fn.body[-1].value=ast.Call(func=ast.Name(id='locals',ctx=ast.Load()),args=[],keywords=[])
env=dict(F=F,Path=Path,re=re,__file__=str(P/'source/tools/certify_m0_exp_fast.py'))
exec(compile(ast.fix_missing_locations(ast.Module(body=[fn],type_ignores=[])),str(tool),'exec'),env)
d=env['certificate']();delta=d['delta'];coefficient=F(275,64)
assert delta<coefficient
product=F(1,2)+F(1,1<<15)
maximum_delta=d['scale']*d['h']/(1-d['h'])+d['polynomial']
maximum_correction=maximum_delta/2+product
assert maximum_correction<23*(1<<48)
constant=product+d['real_h']/(2*(1-d['real_h']))+F(1,1<<33)/(1-d['real_h'])
assert constant<F(129,256)
qmax=(1<<63)+(1<<53)+1;maxhead=qmax>>48
assert (maxhead+24)*275+16383<1<<32
assert 3*256+128<1<<31
im=ElfImage(W/'candidate.elf')
def data(fragment,size):
 n=next(n for n in im.symbols if fragment in n and im.sizes.get(n)==size);a=im.symbols[n]
 s=next(s for s in im.named_sections.values() if s[3]<=a<s[3]+s[5])
 return im.bytes_at(s)[a-s[3]:a-s[3]+size]
table=data('exp_table',4096);refine=data('refine_exp_table',6144);rows=[]
for i,value in enumerate(struct.unpack('<512Q',table)):
 assert (2*value-1)**512<(1<<(63*512+i))<(2*value+1)**512
 low,mid,high=struct.unpack_from('<3I',refine,12*i);v94=(high<<64)|(mid<<32)|low
 assert (2*v94-1)**512<(1<<(95*512+i))<(2*v94+1)**512
 bias=v94-(value<<32)
 assert -(1<<31)<bias<1<<31
 assert low-(int(low>>31)<<32)==bias
 rows.append((value,bias))

jobs={};head_certificates=0
def add(q,bias):
 assert 0<=q<1<<64 and -(1<<31)<=bias<1<<31
 jobs.setdefault((q,bias&0xffffffff),None)
for head in range(1<<14,maxhead+1):
 top=head+24;bound=((top*275+16383)>>14)+129
 assert F(bound,256)>delta*F(top,65536)+constant
 assert F(bound-129,256)>=coefficient*F(top,65536)
 head_certificates+=1
 for distance in (2,3):
  for above in (False,True):
   cutoff=bound-distance*256 if above else distance*256-bound-1
   biases={-128,0,127,cutoff-1,cutoff,cutoff+1}
   tail=512+distance if above else 512-distance
   payload=((head*0x9e3779b9)&((1<<48)-1))&~1023
   q=(head<<48)|payload|tail
   for highbias in biases:
    if not -128<=highbias<=127:continue
    for lowbias in (0,(1<<24)-1):add(q,(highbias<<24)+lowbias)
for value,bias in rows:
 for offset in (-1,0,1):
  head=(value>>48)+offset
  if not 1<<14<=head<=maxhead:continue
  for distance in (2,3):
   for above in (False,True):add((head<<48)|(512+distance if above else 512-distance),bias)
raw=b''.join(struct.pack('<QQ',q,bias) for q,bias in jobs)
(W/'unit-inputs.bin').write_bytes(raw)
source=(W/'candidate/native_eabi_m0.cpp').read_text();start=source.index('          const uint32_t top=uint32_t(q>>48)+24U;');stop=source.index('          safe=margin>int32_t(bound);',start)+len('          safe=margin>int32_t(bound);');fragment=source[start:stop]
unit='''#include <stdint.h>
using U=uint64_t;
extern "C" U audit_exp_gate(U q,U arguments) {
 const int32_t delta32=int32_t(uint32_t(arguments));
 const unsigned tail=unsigned(q)&1023U;
 const unsigned distance=tail>512U?tail-512U:512U-tail;
 bool safe=false;
'''+fragment+'''
 return (U(bound)<<32)|unsigned(safe);
}
'''
(W/'unit.cpp').write_text(unit)
entry=next(e for e in json.loads((P/'build/compile_commands.json').read_text()) if e['file'].endswith('/code/native_eabi_m0.cpp'))
cmd=shlex.split(entry['command']);cc=Path(cmd[0]).parent
cmd[cmd.index(entry['file'])]=str(W/'unit.cpp');cmd[cmd.index('-o')+1]=str(W/'unit.o')
subprocess.run(cmd,cwd=W,check=True)
(W/'unit.ld').write_text('PHDRS { code PT_LOAD FLAGS(5); }\nSECTIONS { . = 0x10166000; .unit : { *(.text*) *(.rodata*) } :code /DISCARD/ : { *(.ARM.exidx*) *(.ARM.extab*) *(.comment) *(.ARM.attributes) *(.note*) } }\n')
link=[str(cc/'arm-none-eabi-ld'),'--gc-sections','-e','audit_exp_gate','-T',str(W/'unit.ld'),str(W/'unit.o'),'-o',str(W/'unit.elf')]
subprocess.run(link,cwd=W,check=True)
assert not subprocess.check_output([str(cc/'arm-none-eabi-nm'),'-u',str(W/'unit.elf')],text=True)
out=dict(status='AUTHOR_EXACT_RATIONAL_SOURCE_BOUND_ADAPTIVE_EXP_ENCLOSURE',source_sha256=build['source_sha256'],candidate_ELF_sha256=build['candidate_ELF_sha256'],
 original_reduction_and_polynomial_delta_bound=str(delta),original_delta_float=float(delta),
 adaptive_coefficient_upper_bound=str(coefficient),maximum_correction=str(maximum_correction),maximum_correction_strictly_below_23times2pow48=True,
 remaining_product_table_cross_bound=str(constant),remaining_bound_float=float(constant),remaining_strictly_below_129over256=True,
 every_Q62_Q94_table_row_RNE_and_bias_rechecked=True,table_rows=512,table_sha256=hashlib.sha256(table).hexdigest(),Q94_table_sha256=hashlib.sha256(refine).hexdigest(),
 q_head_range=[1<<14,maxhead],head_integer_bound_certificates=head_certificates,
 no_uint32_or_int32_overflow_or_undefined_shift=True,normal_error4_only=True,old_distance3_predicate_retained=True,
 source_literal_unit_fragment_sha256=hashlib.sha256(fragment.encode()).hexdigest(),unit_inputs=len(jobs),unit_inputs_sha256=sha(W/'unit-inputs.bin'),unit_ELF_sha256=sha(W/'unit.elf'),
 commands=[cmd,link],new_tables_or_RAM=False,hardware_accessed=False,independent_review_pending=True)
(W/'certificate.json').write_text(json.dumps(out,indent=2)+'\n')
print(json.dumps({k:v for k,v in out.items() if k!='commands'},indent=2))

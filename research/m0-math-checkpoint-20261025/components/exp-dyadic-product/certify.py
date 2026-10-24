"""Universal identity proof for the only changed numerical expression."""
from pathlib import Path
from fractions import Fraction as F
import ast, copy, hashlib, json, re, shlex, struct, subprocess, sys
sys.dont_write_bytecode=True
W=Path(__file__).resolve().parent;ROOT=W.parents[1]
P=ROOT/'.build/m0-asin-scaled-bound-v164-20261023'
D=ROOT/'.build/m0-exp-adaptive-enclosure-20261024'
sys.path.insert(0,str(ROOT/'tests'))
from check_stm32_vectors import ElfImage
sha=lambda p:hashlib.sha256(p.read_bytes()).hexdigest()
b=json.loads((W/'build.json').read_text())
old=(D/'candidate/native_eabi_m0.cpp').read_text()
new=(W/'candidate/native_eabi_m0.cpp').read_text()
original='  const U correction=mk61_m0_pow_exp_product_flash(q,below?U(0)-delta:delta);'
replacement='''  const U displacement=below?U(0)-delta:delta;
  // Row zero is exactly2^62. The rounded high product is a shift;
  // all three omitted partial products are identically zero.
  const U correction=index?mk61_m0_pow_exp_product_flash(q,displacement):
                           (displacement+2U)>>2;'''
assert old.count(original)==1 and new==old.replace(original,replacement)
assert sha(W/'candidate/native_eabi_m0.cpp')==b['source_sha256']
tool=ROOT/'tools/certify_m0_exp_fast.py'
fn=copy.deepcopy(next(n for n in ast.parse(tool.read_text()).body if isinstance(n,ast.FunctionDef) and n.name=='certificate'))
fn.body[-1].value=ast.Call(func=ast.Name(id='locals',ctx=ast.Load()),args=[],keywords=[])
env=dict(F=F,Path=Path,re=re,__file__=str(P/'source/tools/certify_m0_exp_fast.py'))
exec(compile(ast.fix_missing_locations(ast.Module(body=[fn],type_ignores=[])),str(tool),'exec'),env)
proof=env['certificate']()
maximum=proof['scale']*proof['h']/(1-proof['h'])+proof['polynomial']
assert maximum+2<1<<54
im=ElfImage(W/'candidate.elf')
name=next(n for n in im.symbols if 'exp_table' in n and im.sizes.get(n)==4096)
address=im.symbols[name]
section=next(s for s in im.named_sections.values() if s[3]<=address<s[3]+s[5])
table=im.bytes_at(section)[address-section[3]:address-section[3]+4096]
assert struct.unpack_from('<Q',table)[0]==1<<62
parent=json.loads((D/'certificate.json').read_text())
assert hashlib.sha256(table).hexdigest()==parent['table_sha256']
# A=2^62 has only limb a3=2^14. Every omitted term i+j<2 is zero.
# Therefore the old rounded retained product is
# floor((2^62*b+2^63)/2^64) = floor((b+2)/4), for all 0<=b<2^54.
# The addition cannot wrap. Neither the error radii nor admission gates change.
unit='''#include <stdint.h>
extern "C" __attribute__((optimize("Os"))) uint64_t audit_dyadic_product(uint64_t displacement) {
 return (displacement+2U)>>2;
}
'''
(W/'dyadic-unit.cpp').write_text(unit)
entry=next(e for e in json.loads((P/'build/compile_commands.json').read_text()) if e['file'].endswith('/code/native_eabi_m0.cpp'))
c=shlex.split(entry['command']);cc=Path(c[0]).parent
c[c.index(entry['file'])]=str(W/'dyadic-unit.cpp');c[c.index('-o')+1]=str(W/'dyadic-unit.o')
subprocess.run(c,cwd=W,check=True)
(W/'dyadic-unit.ld').write_text('PHDRS { code PT_LOAD FLAGS(5); }\nSECTIONS { . = 0x10166000; .unit : { *(.text*) *(.rodata*) } :code /DISCARD/ : { *(.ARM.exidx*) *(.ARM.extab*) *(.comment) *(.ARM.attributes) *(.note*) } }\n')
link=[str(cc/'arm-none-eabi-ld'),'--gc-sections','-e','audit_dyadic_product','-T',str(W/'dyadic-unit.ld'),str(W/'dyadic-unit.o'),'-o',str(W/'dyadic-unit.elf')]
subprocess.run(link,cwd=W,check=True)
assert not subprocess.check_output([str(cc/'arm-none-eabi-nm'),'-u',str(W/'dyadic-unit.elf')],text=True)
out=dict(status='SOURCE_PROOF_ALL_INDEX0_PRODUCTS_NUMERICALLY_IDENTICAL',
 source_sha256=b['source_sha256'],candidate_ELF_sha256=b['candidate_ELF_sha256'],
 only_CPP_change_is_exact_product_replacement=True,index0_table_value=1<<62,
 table_sha256=hashlib.sha256(table).hexdigest(),maximum_displacement_bound=str(maximum),
 displacement_plus2_strictly_below2pow54=True,all_omitted_terms_zero_for_index0=True,
 old_product_and_new_shift_equal_for_all_valid_displacements=True,
 all_previous_error_radii_admission_gates_refinement_and_IEEE_policy_unchanged=True,
 inherited_parent_numeric_proof_independent_review_pending=True,
 unit_ELF_sha256=sha(W/'dyadic-unit.elf'),commands=[c,link],hardware_accessed=False)
(W/'certificate.json').write_text(json.dumps(out,indent=2)+'\n')
print(json.dumps({k:v for k,v in out.items() if k!='commands'},indent=2))

"""Bind the main-ln one-sided ln2 error test to exact source and tables."""
from pathlib import Path
from fractions import Fraction as F
import ast
import hashlib
import json
import re

W=Path(__file__).resolve().parent
ROOT=W.parents[1]
BASE=ROOT/'.build/m0-ln-near-q77-linear-20261024'
P=ROOT/'.build/m0-asin-scaled-bound-v164-20261023/source/code'
sha=lambda p:hashlib.sha256(p.read_bytes()).hexdigest()
source=(W/'native_eabi_m0_log70.inc').read_text()
assert sha(W/'native_eabi_m0_log70.inc')=='661ae2b62f0f2e3b9da08b689de0a7876f83fa2f80f57380113b78cbbd74e79b'
expected=(BASE/'native_eabi_m0_log70.inc').read_text()
anchor='enum : uint32_t {ln_main_radius=8U,ln_near_radius=4U};'
assertion='''
static_assert(refine_log_two_high==((log70_two_high<<24)|uint32_t(log70_two_low>>40)) &&
    refine_log_two_low>(log70_two_low<<24),"Q70 ln2 must be a strict lower bound");'''
expected=expected.replace(anchor,anchor+assertion)
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
a=expected.index('  if(uint32_t(tail-(half-guard))<=2U*guard) {',expected.index('inline double ln_main_pack70'))
z=expected.index('\n  const uint32_t lo=',a)
oldbody=expected[a:z];body=oldbody[oldbody.index('\n')+1:oldbody.rfind('\n  }')]
newbody='''  if(uint32_t(tail-(half-guard))<=2U*guard) {
    // The generic polynomial bound is13.400121<14; the ln2 error
    // on exponent paths is nonpositive in the final magnitude.
    if(!exponent_error || tail<half+14U) {
'''+''.join('  '+line+'\n' for line in body.splitlines())+'''    }
  }'''
expected=expected[:a]+newbody+expected[z:]
assert expected==source

def constant(path,name):
    text=path.read_text()
    m=re.search(r'\b'+name+r'\s*=\s*(?:UINT64_C\((\d+)\)|(\d+)U)',text)
    assert m,name
    return int(m.group(1) or m.group(2))
table=P/'native_eabi_m0_log70_table.inc';refine=P/'native_eabi_m0_refine_table.inc'
L70=(constant(table,'log70_two_high')<<64)|constant(table,'log70_two_low')
L94=(constant(refine,'refine_log_two_high')<<64)|constant(refine,'refine_log_two_low')
assert L94-(L70<<24)==7924966
path=ROOT/'tools/generate_m0_log_table.py';text=path.read_text()
nodes=[n for n in ast.parse(text).body if isinstance(n,ast.FunctionDef) and n.name in ('nearest','logarithm')]
env={'Fraction':F};exec(compile(ast.Module(body=nodes,type_ignores=[]),str(path),'exec'),env)
assert env['logarithm'](F(2),70)==L70 and env['logarithm'](F(2),94)==L94
z=F(1,3);power=z;lower=F(0)
for i in range(100):lower+=2*power/(2*i+1);power*=z*z
upper=lower+2*power/(201*(1-z*z))
assert F(L70,1<<70)<lower<upper
error_low=F(L70)-upper*(1<<70);error_high=F(L70)-lower*(1<<70)
assert -F(1,2)<error_low<error_high<0
exact=F(json.loads((ROOT/'.build/m0-ln-enclosure-20261024/certificate.json').read_text())['main_bound'])
raw=F(json.loads((ROOT/'.build/m0-ln-main-raw-split-family-20261024/certificate.json').read_text())['generic_main_bound'])
assert exact<8 and raw<14
checks=0
for n in range(1,1024):
    extra=(n+1)//2
    for bound,radius,max_distance in ((exact,8,7+extra),(raw,14,15+extra)):
        # Final magnitude error is symmetric polynomial error plus the
        # same negative n*ln2-table error for either exponent sign.
        e_lo=-bound+n*error_low;e_hi=bound+n*error_high
        assert radius-e_hi>0
        assert max_distance-e_lo<2048
        checks+=2
out=dict(status='PASS_SOURCE_BOUND_MAIN_LN_LN2_DIRECTIONAL_UPPER_GATE',
    source_sha256=sha(W/'native_eabi_m0_log70.inc'),candidate_ELF_sha256=sha(W/'candidate.elf'),
    exact_parent_source_transformation_verified=True,L70=str(L70),L94=str(L94),Q94_minus_shifted_Q70=7924966,
    actual_ln2_Q70_error_approx=str(F(L70)-F(L94,1<<24)),ln2_Q70_is_strictly_below_exact_ln2=True,
    rational_100term_log2_lower_and_upper_checked=True,compile_time_sign_contract_present=True,
    exact_polynomial_bound=str(exact),exact_polynomial_bound_float=float(exact),raw_polynomial_bound=str(raw),raw_polynomial_bound_float=float(raw),
    exact_new_accept='original guard active && n>0 && tail>=half+8',raw_new_accept='original guard active && n>0 && tail>=half+14',
    magnitude_ln2_error='n*(L70-2^70*ln2)<0 for either exponent sign; the main product forms n*L70 exactly',
    n_domain=[1,1023],all1023_integer_exponents_checked=True,integer_endpoint_checks=checks,
    inherited_main_pack_shifts=[11,27],smallest_half_gap=1024,next_midpoint_offset_at_least=2048,
    upper_neighbor_not_skipped=True,new_tables_RAM_or_dependencies=False,
    other_source_paths_unchanged=True,source_only_new_runtime_changes_are_two_guard_predicates=True,
    helper_unit_required=True,hardware_accessed=False)
(W/'certificate.json').write_text(json.dumps(out,indent=2)+'\n');print(json.dumps(out,indent=2))

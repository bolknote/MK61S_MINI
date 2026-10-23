"""Exact-rational scaling of the existing certified small-angle enclosure."""
from fractions import Fraction as F
import hashlib,json,sys
from pathlib import Path
root=Path.cwd();work=Path(__file__).resolve().parent;parent=root/'.build/m0-sqrt-zero-tail-v163-20261023'
sys.path.insert(0,str(work/'proof'))
from certify_m0_asin_fast import certificate,verify_atan_table
def function(text,name):
    start=text.index(name);opening=text.index('{',start);depth=1;end=opening+1
    while depth:
        depth+=(text[end]=='{')-(text[end]=='}');end+=1
    return text[start:end]
old=certificate();relative=F(old['small_atan_error']);assert relative<24
asin=F(24,64)+F(1,2)+F(1,2)
acos_negative=asin+F(1,2)
assert asin==F(11,8)<2 and acos_negative==F(15,8)<2
per_exponent=[]
for exponent in range(-26,-12):
    bound=relative*F(2)**(exponent+7)+F(3,2)
    assert bound<2
    per_exponent.append(dict(exponent=exponent,error_q70=str(bound),radius=2))
source=work/'source/code/native_eabi_m0_asin.inc';text=source.read_text();prior=(parent/'source/code/native_eabi_m0_asin.inc').read_text()
for name in ('asin_root_normalized(','asin_root_estimate(','asin_root_shift(','asin_q70(',
             'asin_pack_q70(','asin_atan_small(','asin_geometry(','asin_geometry_refined(','asin_refine('):
    assert function(text,name)==function(prior,name),name
changed='''      angle=r96_sub(asin_half_pi(),asin_q70(small,exponent));
#if defined(MK61_M0_RP2040_EABI) && MK61_M0_RP2040_EABI
      // The relative error is <24 Q63 units. At exponent<=-13,
      // converting to Q70 and folding at most two half-pi constants
      // costs <24/64+1/2+1=1.875 units, so radius2 is sufficient.
      error=exponent<=-13?2U:128U;
#else
      error=128;
#endif'''
assert text.count(changed)==1
assert text.replace(changed,'      angle=r96_sub(asin_half_pi(),asin_q70(small,exponent));error=128;')==prior
table=verify_atan_table(work/'source/code/native_eabi_m0_refine_table.inc')
record=dict(status='PASS_EXACT_SCALED_ASIN_ACOS_ENDPOINT_BOUND',
    inherited_relative_small_atan_bound_q63=str(relative),inherited_relative_small_atan_bound_float=float(relative),
    conservative_asin_bound_q70=str(asin),conservative_negative_acos_bound_q70=str(acos_negative),
    returned_radius_q70=2,maximum_relative_exponent=-13,per_exponent=per_exponent,
    unchanged_approximation_functions=True,atan_half_pi_table=table,
    source_sha256=hashlib.sha256(source.read_bytes()).hexdigest(),
    producer_sha256=hashlib.sha256(Path(__file__).read_bytes()).hexdigest(),
    proof_scope='Existing relative angle error<24 Q63. The exact integer scale2^(exponent+7), one RNE quantization<=1/2 Q70 and at most two independently bounded half-pi quantization errors<=1/2 each give<15/8 Q70 for every affected result. Strict final rounding-cell guard remains. Other exponents and non-RP2040 paths retain128. No accuracy tolerance is relaxed.',
    new_tables=0,new_global_RAM=0,hardware_accessed=False,goal_complete=False)
(work/'certificate.json').write_text(json.dumps(record,indent=2)+'\n')
print('PASS:relative bound',float(relative),'<24 Q63;folded asin <=1.375/negative acos <=1.875 Q70;radius2;unchanged arithmetic/table.')

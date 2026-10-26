"""Prove the naked IEEE classifier partition and bind the unchanged bodies."""
from pathlib import Path
import ast
import hashlib
import json

W=Path(__file__).resolve().parent
ROOT=W.parents[1]
BASE=ROOT/'.build/m0-ln-main-raw-split-family-20261024'
sha=lambda p:hashlib.sha256(p.read_bytes()).hexdigest()
source=(W/'native_eabi_m0_log70.inc').read_text()
assert sha(W/'native_eabi_m0_log70.inc')=='52e3a6f0a32069120fe0ccd3ec6593872cb97bd9579bd1a2e9b8d654bd2efb1a'
tree=ast.parse((ROOT/'.build/m0-ln-cold-entry-20261024/prepare.py').read_text())
values={}
for n in tree.body:
    if isinstance(n,ast.Assign) and len(n.targets)==1 and isinstance(n.targets[0],ast.Name) and n.targets[0].id in ('start','replace'):
        values[n.targets[0].id]=ast.literal_eval(n.value)
parent=(BASE/'native_eabi_m0_log70.inc').read_text()
assert parent.count(values['start'])==1
assert parent.replace(values['start'],values['replace'])==source
for name in ('native_eabi_m0.cpp','native_eabi_m0_log70_center.inc','native_eabi_m0_log70_ratio.inc','native_eabi_m0_log10.inc','native_eabi_m0_log_subnormal.inc'):
    assert sha(W/name)==sha(BASE/name),name

# For the actual high-word shifts, field is sign:exponent in0..4095.
# ((field+1)>>11)==0 and field!=0 iff the number is positive normal.
checks=0
for field in range(4096):
    branch_normal=((field+1)>>11)==0 and field!=0
    assert branch_normal==(1<=field<=2046)
    for fraction_hi in (0,1,1<<19,(1<<20)-1):
        high=(field<<20)+fraction_hi
        assert high>>20==field
        for low in (0,1,0x80000000,0xffffffff):
            raw=(high<<32)+low
            early_zero=low==0 and ((high<<1)&0xffffffff)==0
            early_inf=low==0 and not early_zero and high==0x7ff00000
            assert early_zero==((raw&((1<<63)-1))==0)
            assert early_inf==(raw==0x7ff0000000000000)
            if early_zero:
                assert ((0xfff00000<<32)|low)==0xfff0000000000000
            checks+=1

unit=json.loads((W/'entry-unit-proof.json').read_text())
assert unit['source_sha256']==sha(W/'native_eabi_m0_log70.inc')
assert unit['actual_ARM_calls']==131072 and unit['all_forwarded_input_bits_preserved']
assert unit['SIO_accesses']==0
out=dict(status='PASS_EXACT_NAKED_LN_IEEE_CLASSIFIER_AND_UNCHANGED_NUMERICAL_SOURCE',
    source_sha256=sha(W/'native_eabi_m0_log70.inc'),candidate_ELF_sha256=sha(W/'candidate.elf'),
    parent_result_sha256=sha(BASE/'result.json'),source_change_only_exact_entry_replacement=True,
    previous_raw_near_polynomial_pack_tables_source_identical=True,
    sign_exponent_fields_exhausted=4096,bit_class_partition_checks=checks,
    fraction_low_partition='Classifier depends only on sign/exponent plus exact zero/positive-infinity full-bit tests; representatives cover zero/nonzero fraction and low classes.',
    zero_return_bits='FFF0000000000000',positive_infinity_return_bits='7FF0000000000000',
    other_cold_inputs='Tail forward original R0/R1 to unchanged mk61_m0_ln_special; raw NaN policy inherited.',
    positive_normals='Tail forward original R0/R1 to unchanged normal source body.',
    parent_rational_rounding_proof_inherited=True,parent_independent_review_not_claimed=True,
    new_tables_RAM_or_dependencies=False,hardware_accessed=False)
(W/'certificate.json').write_text(json.dumps(out,indent=2)+'\n')
print(json.dumps(out,indent=2))

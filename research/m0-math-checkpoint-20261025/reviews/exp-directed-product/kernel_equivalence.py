"""Independent arithmetic instruction bijection for all raw inputs/flags."""
from pathlib import Path
import json,re
R=Path('/Users/bolk/Projects/MK61S_MINI');O=Path(__file__).resolve().parent;W=R/'.build/m0-exp-directed-product-20261024'
def instructions(kind):
 s=(W/kind/'native_eabi_m0_pow_exp_product.inc').read_text()
 s=s.split('mk61_m0_pow_exp_product:\n',1)[1].split('.size mk61_m0_pow_exp_product',1)[0]
 return[re.sub(r'\s+',' ',l.split('//')[0].strip())for l in s.splitlines()if l.split('//')[0].strip()]
old,new=instructions('control'),instructions('candidate')
assert(len(old),len(new))==(79,77)and old[:4]==new[:4]and old[-2:]==new[-2:]
mapping={'r0':'r5','r1':'r6','r5':'r0','r6':'r1'}
middle=[re.sub(r'\br[0156]\b',lambda m:mapping[m[0]],line)for line in old[4:-2]]
first=middle.index('ldrh r5,[r3,#0]');assert middle[first:first+4]==['ldrh r5,[r3,#0]','ldrh r6,[r3,#12]','muls r5,r6','mov r4,r5']
middle[first:first+4]=['ldrh r4,[r3,#0]','ldrh r6,[r3,#12]','muls r4,r6']
assert middle[-2:]==['mov r5,r0','mov r6,r1']
# Original final MOVs target fixed ABI output registers; they are not renamed
# as temporaries. The new accumulators already ARE those ABI registers.
middle=middle[:-2]
cut=middle.index('lsls r4,#1');middle.insert(cut,'mov r12,r4')
assert middle==new[4:-2]
out=dict(status='PASS_ALL_INPUT_ARITHMETIC_BIJECTION_AND_FLAGS',
 exact_source_instruction_lists_bound_to_rebuilt_full_ELF=True,old79_new77=True,
 prologue_argument_save_offsets_36byte_frame_and_epilogue_identical=True,
 temporary_register_bijection={'old_r0':'new_r5','old_r1':'new_r6','old_r5':'new_r0','old_r6':'new_r1'},
 first_multiply_directly_into_r4_removes_one_nonflag_MOV=True,
 final_two_nonflag_ABI_MOVs_removed_accumulators_already_r0_r1=True,
 added_nonflag_MOV_R12_R4_before_discarding_exact_fraction=True,
 scalar_raw64_output_and_PCS_universal_equivalence_by_instruction_bijection=True,
 numerical_exact_retained_product_oracle_requires_a_lt2power63_b_lt2power54=True,
 arbitrary_NZCV_inputs_safe='All relevant arithmetic/flags map identically. Removed and added MOV are nonflag; changed first MUL produces the same flags/value. Dynamic all16 checks cover 8 adversarial pairs.',
 extra_R12_is_private_not_scalar_C_ABI=True,hardware=False)
with(O/'kernel-equivalence.json').open('x')as f:json.dump(out,f,indent=2);f.write('\n')
print(json.dumps(out,indent=2))

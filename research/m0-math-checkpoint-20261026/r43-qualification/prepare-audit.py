"""Adapt the all-row audit, explicitly preserving historical R41 adverse scope."""
from pathlib import Path
import sys
sys.dont_write_bytecode=True
W=Path(__file__).resolve().parent;ROOT=W.parents[1]
P=ROOT/'.build/m0-math-unified-pow-rsqrt-seedreuse-r42-qualification-20261026'
assert not(W/'audit.py').exists()
t=(P/'audit.py').read_text().replace('R42','R43').replace('R41','R42')
t=t.replace('m0-math-unified-pow-rsqrt-seedreuse-r42-20261026','m0-math-unified-pow-rsqrt-nativeq8-r43-20261026').replace('m0-math-unified-pow-rsqrt-negfirst-r41-qualification-20261026','m0-math-unified-pow-rsqrt-seedreuse-r42-qualification-20261026').replace('m0-math-unified-pow-rsqrt-negfirst-r41-20261026','m0-math-unified-pow-rsqrt-seedreuse-r42-20261026')
t=t.replace('b5e0bf1e6316a2bc0924127f0b9564c025cb042842f4d3527ce1eef8fd48a676','170cd77a62244459c526ea2817f964652f4355c31e7824defc7b0195a6a5b22b').replace('aa13981ded8055e02cd9c4fb5ee3106bc200e1210ce72bba1e5688aa32a55884','c9e7ebb1dcd34a4536e12fcb77af95ecbfc51f44176fe5b7e57e85b7cbe39515')
edits={
"unit=read(S/'product-unit-result.json')":"unit=read(S/'helper-unit-result.json')",
"assert proof['all8_product_CFGpaths_save_exactly1instruction']and proof['R6_old_suffix_dead_except_callee_restore']and unit['candidate_wrong']==unit['parent_instruction_increase_rows']==0":"assert proof['all_native_branch_paths_save1instruction']and proof['ordinary_entry_keeps_arbitrary_incoming_NZCV']and unit['candidate_wrong']==unit['all_native_fixture_parent_instruction_increase_rows']==0",
"assert unit['actual_qualified_primitive_ARM_calls']==92022 and unit['instruction_delta_histogram']=={'-1':46011}":"assert unit['actual_qualified_control_ARM_calls']==573536 and unit['generic_instruction_delta_histogram']=={'2':143384}and unit['native_fixture_instruction_delta_histogram']=={'-1':143384}",
"len(fullparent)==2312 and len(pl-cl)==15":"len(fullparent)==2303 and len(pl-cl)==10",
"len(priorloss)==2342":"len(priorloss)==2353",
"len(priorinputs)==145281":"len(priorinputs)==151409",
"len(priorloss-cl)==15 and len(pl-priorloss)==26 and len(cl-priorloss)==26":"len(priorloss-cl)==10 and len(pl-priorloss)==0 and len(cl-priorloss)==0",
"==2368 and len(cl)==diagnostic['candidate_losing_pairs']==2353":"==2353 and len(cl)==diagnostic['candidate_losing_pairs']==2343",
"control=unit['actual_qualified_primitive_ARM_calls']":"control=unit['actual_qualified_control_ARM_calls']",
"public+control==620386":"public+control==1101900",
"all_current_product_control_parent_increase_rows=0":"all_current_generic_helper_control_parent_increase_rows=143384,all_current_native_fixture_control_parent_increase_rows=0,all_generic_control_increases_retained=True",
"all8_product_CFG_paths_save1instruction=True":"all13_native_helper_CFG_paths_save1instruction=True,all13_generic_helper_CFG_paths_add2_retained=True",
"other18_M4default_CPP_objects_exact=True,bank_literal_bytes_identical=True":"other17_M4default_objects_exact=True,RPASM_allocatedbytes_exact_unique_relocation_changed=True,bank_changed13bytes_symbolically_mapped=True",
"inherited_R42_synthetic_helper_increase_rows3591_retained":"inherited_R41_synthetic_helper_increase_rows3591_retained",
"inherited_R42_helper_increases_not_R43_parent_increases_or_public_input_cases":"inherited_R41_helper_increases_not_R43_parent_increases_or_public_input_cases",
"Earlier3591synthetic helper increases retained in R42 packet, not pooled as fresh R43":"Earlier3591synthetic helper increases retained in R41 packet, not pooled as fresh R43; new143384generic helper increases retained separately, not public numeric-gold"
}
for a,b in edits.items():assert a in t,a;t=t.replace(a,b)
compile(t,str(W/'audit.py'),'exec');(W/'audit.py').write_text(t);print('R43 all-row audit prepared with explicit ordinary/native control scopes.')

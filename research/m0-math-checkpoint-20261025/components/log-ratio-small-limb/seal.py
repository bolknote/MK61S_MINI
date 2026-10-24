"""Freeze the source-bound exact small-low-limb quotient component."""
from pathlib import Path
from collections import Counter
import difflib
import hashlib
import json

W=Path(__file__).resolve().parent
ROOT=W.parents[1]
BASE=ROOT/'.build/m0-ln-endpoint-predicate-20261024'
assert not (W/'result.json').exists()
def sha(p):return hashlib.sha256(p.read_bytes()).hexdigest()
def read(n):return json.loads((W/n).read_text())
q,iso,body,cert,helper,shared,host=[read(n) for n in ('qualification.json','isolation.json','public-body-proof.json','certificate.json','helper-proof.json','shared-section-proof.json','seed-domain-proof.json')]
source,elf=sha(W/'native_eabi_m0_log70_center.inc'),sha(W/'candidate.elf')
assert source=='af83817a78b261621a638c5cc3436bfd63ef57371d999766dfad2a50733dcef7'
assert elf=='c0000b4a468cdb80228fab332978f276a21cf5e229fa1abe7622a287ef396297'
for d in (q,iso,body,cert,helper,shared,host):assert d['source_sha256']==source and d['candidate_ELF_sha256']==elf
assert q['cases']==len(q['rows'])==68876 and q['unique_inputs']==34438
assert q['actual_ARM_calls']==275504 and q['retained_parent_counts_checked']==66172
assert all(r['correct']['candidate'] and r['correct']['parent'] and r['outputs']['candidate']==r['outputs']['parent'] for r in q['rows'])
assert all(g['newly_slower_correct_Qfplib']==0 for g in q['groups'])
assert all(r['instructions']['candidate']==r['instructions']['parent'] for r in q['rows'] if r['SIO']=='READY')
assert helper['actual_ARM_calls']==790256 and helper['pairs']==197564 and helper['SIO_accesses']==0
assert helper['all_results_exact_integer_floor'] and not helper['firmware_or_ROM_mapped']
assert host['pairs']==67634176 and host['not_ARM_execution']
assert iso['allocated_object_bytes_delta']==212 and all(c['allocated_code_and_data_identical'] for c in iso['contexts'])
assert body['entire_ELF_byte_exact_without_exclusions']
assert q['candidate_stack_bytes']==q['parent_stack_bytes']==640
fixed=[r for r in q['rows'] if r['correct']['Qfplib'] and r['instructions']['parent']>r['instructions']['Qfplib']>=r['instructions']['candidate']]
assert len(fixed)==155 and all(r['SIO']=='DIRTY' for r in fixed)
old=json.loads((BASE/'remaining-slower.json').read_text())['rows']
old_set={(r['x'],r['SIO']) for r in old}
assert sum((r['x'],r['SIO']) in old_set for r in fixed)==28
losses,regress=q['remaining_slower_correct_Qfplib'],q['regressions_vs_parent']
assert len(losses)==113 and len({r['x'] for r in losses})==68
assert len({r['x'] for r in losses if (r['x'],r['SIO']) in old_set})==45
assert len(regress)==6779
delta=Counter(r['instructions']['candidate']-r['instructions']['parent'] for r in regress)
assert delta=={3:2682,4:4097}
change=Counter('faster' if r['instructions']['candidate']<r['instructions']['parent'] else 'equal' if r['instructions']['candidate']==r['instructions']['parent'] else 'slower' for r in q['rows'])
(W/'remaining-slower.json').write_text(json.dumps(dict(status='SIXTY_EIGHT_EXPANDED_LN_SPEED_INPUTS_OPEN',raw_inputs=68,state_rows=113,old73_remaining=45,new_control_remaining=23,rows=losses),indent=2)+'\n')
(W/'regressions.json').write_text(json.dumps(dict(status='ALL_PARENT_REGRESSIONS_RETAINED',state_rows=6779,instruction_delta_histogram=dict(delta),rows=regress),indent=2)+'\n')
(W/'small-low-limb-only.patch').write_text(''.join(difflib.unified_diff((BASE/'native_eabi_m0_log70_center.inc').read_text().splitlines(True),(W/'native_eabi_m0_log70_center.inc').read_text().splitlines(True),fromfile='parent/native_eabi_m0_log70_center.inc',tofile='candidate/native_eabi_m0_log70_center.inc')))
pins=dict(json.loads((BASE/'input-pins.json').read_text())['files'])
for n,h in pins.items():assert sha(ROOT/n)==h,n
for n in ('result.json','qualification.json','certificate.json','candidate.elf','candidate-full.o','helper-proof.json','isolation.json'):
    p=BASE/n;pins[str(p.relative_to(ROOT))]=sha(p)
p=ROOT/'.build/m0-ln-endpoint-predicate-independent-20261024/FINAL-REVIEW.json'
assert sha(p)=='dc26bd1132de4d1ce006ea40bf175e0add99616e3f345bf3fc1a22b847da5fb0'
assert json.loads(p.read_text())['blockers']==[]
pins[str(p.relative_to(ROOT))]=sha(p)
(W/'input-pins.json').write_text(json.dumps(dict(status='READ_ONLY_INPUTS_PINNED',files=pins),indent=2)+'\n')
r=dict(status='AUTHOR_PASS_EXACT_SMALL_LOW_LIMB_RATIO_WITH_68_EXPANDED_SPEED_INPUTS_OPEN',
    unique_inputs=34438,public_state_cases=68876,all_cases_profiled=True,qualified_public_ARM_calls=275504,
    qualified_bare_helper_ARM_calls=790256,total_qualified_ARM_calls=1065760,
    separate_host_exhaustive_integer_pairs=67634176,host_pairs_not_ARM_calls=True,
    candidate_wrong=0,retained_parent_counts_checked=66172,groups=q['groups'],old73_raw_deficits_fixed=28,
    old73_raw_deficits_remaining=45,expanded_parent_raw_losses=223,expanded_candidate_raw_losses=68,
    expanded_correct_Qfplib_raw_deficits_fixed=155,new_correct_Qfplib_deficits=0,remaining_state_rows=113,
    newly_exposed_parent_control_losses=150,new_control_losses_remaining=23,vs_parent=dict(change),
    regression_state_rows=6779,regression_instruction_histogram=dict(delta),all_READY_counts_equal=True,
    public_stack_bytes=640,parent_public_stack_same_corpus=640,direct_helper_stack_bytes=helper['observed_stack_bytes'],
    parent_helper_stack_bytes=68,allocated_object_code_bytes_delta=212,linked_component_bytes_delta=216,
    new_tables_global_RAM_or_libgcc=False,M4_generic_M0_allocated_controls_equal=True,whole_public_rebuild_byte_exact=True,
    historical_ln10_total_fixed=6,historical_ln10_remaining=4,source_sha256=source,candidate_ELF_sha256=elf,
    candidate_full_object_sha256=sha(W/'candidate-full.o'),parent_result_sha256=sha(BASE/'result.json'),
    independent_review='not_claimed',production_integration=False,hardware_accessed=False,
    physical_cycles_measured=False,goal_complete=False)
handoff=f'''# Exact small-low-limb log quotient

Private RP2040 child of the accepted endpoint predicate. For signed low
word ell-64..64, delta=F*2^32+ell, reuse the existing reciprocal and six
small products to get a nonnegative underestimate within5Q70 units.
Three remainder bits produce exact floor(H). The generic path now adds
a sign-extended correction, avoiding a wasted U64 sum before subtraction.
All other quotient/polynomial/table/rounding algorithms remain unchanged.

Host uint128 exhaustion covers all67,634,176valid pairs,1024den513F129ell,
with exact independent quotient/remainder and digest69f36adcd7428ad1.
These are not ARM calls. Fresh bare ARM covers197564pairs/790256calls,
all1024den/bothSIO/familyandguardedges:0wrong,0SIOaccesses,PCS/SP/bounded
writes pass. Only component+accepted184Bproduct capsule, nofirmware/ROM.
Fresh public34438unique/68876allprofiled states/275504ARM:0wrongMPFR4.2.2,
raw parent NaN policy/callerSIO/PCS/SP/bounds pass. All66172parentcounts
reproduce. Qualified ARM total1,065,760, not counting discarded trials.

All28former general DIRTY losses now beat correct Qfplib; on the sameold
corpus73raw→45. The broader guard/ordinary controls expose150preexisting
parent losses, giving expandedparent223raw→child68raw/113states:
155rawfixed,0newlyintroduced.23new-control losses remain alongside the
old45. All wrong-reference outputs/losses/regressions are preserved.
Examples DIRTY:718→647vsQfp716;719→644vs689;713→676vs683.
The one new guard-edge loss in an earlier full trial was addressed by
the signed-return optimization: former trial715 now712vsQfp713.

READY34438counts identical. DIRTY4796faster22863equal6779slower; each
regression is3or4instructions. ln2DIRTY613 versus parent610/Qfplib711
is explicitly a3instruction power-path regression. Publicstack640same;
helper76vs68. Code+212Bobject/+216Blinked, only slowhelper232→444B.
No newtables/RAM/libgcc/deps. Other shared bytes/functions and allocated
sections/tables, ratioASM and genericM0/M4controls match (not wholeM4FW).
WholeCPP/ASM/ELF rebuildbyteexact. Near source/object body/table bytes
match parent; linked addresses relocate, not claimed identical. No mathROM.

Source:{source}
ELF:{elf}
Object:{r['candidate_full_object_sha256']}

Hold packet unchanged. Independent review, canonical integration,
physical cycles and hardware acceptance are not claimed. Historical ln
remains6/10fixed4open. Other operations/general pow totality/the original
full math goal remain OPEN.
'''
(W/'HANDOFF.md').write_text(handoff)
r['files']={p.name:sha(p) for p in sorted(W.iterdir()) if p.is_file()}
(W/'result.json').write_text(json.dumps(r,indent=2)+'\n')
print(json.dumps({k:v for k,v in r.items() if k!='files'},indent=2))

"""Freeze the exact predicate child with every newly exposed loss retained."""
from pathlib import Path
from collections import Counter
import hashlib
import json
import sys

sys.dont_write_bytecode = True
W = Path(__file__).resolve().parent
ROOT = W.parents[1]
BASE = ROOT / '.build/m0-ln-near-directional-20261024'
sys.path.insert(0,str(ROOT / 'tests'))
from check_stm32_vectors import ElfImage
assert not (W / 'result.json').exists()
def sha(p):
    return hashlib.sha256(p.read_bytes()).hexdigest()
def read(n):
    return json.loads((W / n).read_text())
q,iso,body,cert,helper,shared = [read(n) for n in ['qualification.json','isolation.json','public-body-proof.json','certificate.json','helper-proof.json','shared-section-proof.json']]
source,elf = sha(W / 'native_eabi_m0_log70_center.inc'),sha(W / 'candidate.elf')
assert source == '79067df1532a771c3cef484271292d7a592f73e1a0e0d51af86b5359c3de33a7'
assert elf == '5187e1bbba29ec6b0d24cfc57aba9feb74598cc0b8df0df06fe6b13a53039e7e'
for d in (q,iso,body,cert,helper,shared):
    assert d['source_sha256'] == source and d['candidate_ELF_sha256'] == elf
assert q['cases'] == len(q['rows']) == 66172 and q['unique_inputs'] == 33086
assert q['actual_ARM_calls'] == 264688 and q['retained_parent_counts_checked'] == 65880
assert all(r['correct']['candidate'] and r['correct']['parent'] and
           r['outputs']['candidate'] == r['outputs']['parent'] for r in q['rows'])
assert helper['actual_ARM_calls'] == 229300 and helper['pairs'] == 57325
assert helper['SIO_accesses'] == 0 and helper['all_results_exact_integer_floor']
assert not helper['firmware_or_ROM_mapped']
assert iso['allocated_object_bytes_delta'] == 0 and all(c['allocated_code_and_data_identical'] for c in iso['contexts'])
assert body['entire_ELF_byte_exact_without_exclusions']
assert q['candidate_stack_bytes'] == q['parent_stack_bytes'] == 640
assert all(g['newly_slower_correct_Qfplib'] == 0 for g in q['groups'])
assert all(r['instructions']['candidate'] == r['instructions']['parent'] for r in q['rows'] if r['SIO'] == 'READY')
fixed = [r for r in q['rows'] if r['correct']['Qfplib'] and r['instructions']['parent'] > r['instructions']['Qfplib'] >= r['instructions']['candidate']]
assert len(fixed) == 5 and all(r['SIO'] == 'DIRTY' for r in fixed)
assert {r['x'] for r in fixed} == {'3FEF7FFFFFFFFFE6','3FEF7FFFFFFFFFE8','3FEF7FFFFFFFFFEA','3FEF7FFFFFFFFFD9','3FEF7FFFFFFFFFDB'}
losses,regress = q['remaining_slower_correct_Qfplib'],q['regressions_vs_parent']
assert len(losses) == 118 and len({r['x'] for r in losses}) == 73
assert len(regress) == 26 and all(r['instructions']['candidate']-r['instructions']['parent'] == 1 for r in regress)
previous=json.loads((BASE / 'qualification.json').read_text())
old_set={(r['x'],r['SIO']) for r in previous['remaining_slower_correct_Qfplib']}
assert len({r['x'] for r in losses if (r['x'],r['SIO']) in old_set}) == 46
assert sum(r['group']=='general_quotient_low_word_wrap_controls' for r in losses) == 27
change=Counter('faster' if r['instructions']['candidate']<r['instructions']['parent'] else
               'equal' if r['instructions']['candidate']==r['instructions']['parent'] else 'slower' for r in q['rows'])
(W / 'remaining-slower.json').write_text(json.dumps(dict(status='SEVENTY_THREE_EXPANDED_LN_SPEED_INPUTS_OPEN',raw_inputs=73,state_rows=118,old51_remaining=46,new_control_losses=27,rows=losses),indent=2)+'\n')
(W / 'regressions.json').write_text(json.dumps(dict(status='ALL_PARENT_REGRESSIONS_RETAINED',state_rows=26,instruction_delta=1,rows=regress),indent=2)+'\n')

def closure(e,part):
    names=[n for n in e.symbols if part in n and e.sizes.get(n,0)]
    assert len(names)==1,(part,names)
    n=names[0];a,size=e.symbols[n]&~1,e.sizes[n]
    s=next(s for s in e.named_sections.values() if s[3]<=a<s[3]+s[5])
    return a,e.bytes_at(s)[a-s[3]:a-s[3]+size]
old,new=ElfImage(W/'control.elf'),ElfImage(W/'candidate.elf')
for n in ('ln_near_interval','log_near_table'):
    assert closure(old,n)==closure(new,n),n
(W / 'inherited-near-proof.json').write_text(json.dumps(dict(
    status='IDENTICAL_LINKED_NEAR_CODE_AND_TABLE_INHERIT_PARENT_PROOF',
    linked_addresses_and_bytes_identical=True,source_header_byte_identical=True,
    parent_result_sha256=sha(BASE/'result.json'),parent_certificate_sha256=sha(BASE/'certificate.json'),
    parent_packer_proof_sha256=sha(BASE/'pack-unit-proof.json'),
    inherited_packer_ARM_calls=16896,fresh_packer_ARM_calls_claimed=0),indent=2)+'\n')
pins=dict(json.loads((BASE/'input-pins.json').read_text())['files'])
for n,h in pins.items():
    assert sha(ROOT/n)==h,n
for n in ('result.json','qualification.json','certificate.json','pack-unit-proof.json','candidate.elf','candidate-full.o'):
    p=BASE/n;pins[str(p.relative_to(ROOT))]=sha(p)
for n in ('seed-source-proof.json','seed-kernel.S'):
    p=ROOT/'.build/m0-log-ratio-dirty-20261024'/n;pins[str(p.relative_to(ROOT))]=sha(p)
(W/'input-pins.json').write_text(json.dumps(dict(status='READ_ONLY_INPUTS_PINNED',files=pins),indent=2)+'\n')
r=dict(status='AUTHOR_PASS_EXACT_ENDPOINT_PREDICATE_WITH_73_EXPANDED_SPEED_INPUTS_OPEN',
    unique_inputs=33086,public_state_cases=66172,all_cases_profiled=True,
    qualified_public_ARM_calls=264688,qualified_bare_helper_ARM_calls=229300,total_qualified_ARM_calls=493988,
    candidate_wrong=0,retained_parent_counts_checked=65880,groups=q['groups'],
    old51_raw_inputs_fixed=5,old51_raw_inputs_remaining=46,new_correct_Qfplib_deficits=0,
    additional_preexisting_general_control_losses=27,expanded_parent_raw_losses=78,
    expanded_candidate_raw_losses=73,remaining_state_rows=118,
    vs_parent=dict(change),regression_state_rows=26,regression_instruction_delta=1,
    public_stack_bytes=640,parent_public_stack_same_corpus=640,allocated_code_and_data_delta=0,
    new_tables_global_RAM_or_libgcc=False,all_READY_instruction_counts_identical=True,
    helper_observed_stack_bytes=68,M4_generic_M0_controls_equal=True,whole_public_rebuild_byte_exact=True,
    inherited_near_packer_ARM_calls_not_counted=16896,source_sha256=source,candidate_ELF_sha256=elf,
    candidate_full_object_sha256=sha(W/'candidate-full.o'),parent_result_sha256=sha(BASE/'result.json'),
    historical_ln10_total_fixed=6,historical_ln10_remaining=4,independent_review='not_claimed',
    production_integration=False,hardware_accessed=False,physical_cycles_measured=False,goal_complete=False)
handoff=f'''# Exact log quotient endpoint predicate

Private RP2040 child of the frozen near-ln directional component. Only
one endpoint condition changes to an equivalent high/low-word predicate.
All arithmetic/rounding/table/primitive algorithms remain unchanged.

Fresh33086 unique inputs/66172 fully profiled state cases,264688 public
ARM calls, zero own errors against fresh MPFR4.2.2. All65880 parent
instruction counts reproduce. PCS/SP/bounded writes/caller SIO/raw parent
NaN policy pass. Bare helpers add229300 calls for57325pairs across all1024
denominators, both SIO states, exact integer floor and no SIO accesses.
That test loads only the component plus its existing184-byte source-bound
product capsule; no firmware/ROM. Qualification total493988 ARM calls.

Five old DIRTY losses722->718 now beat correct Qfplib719. ln2 DIRTY
613->610 versusQfplib711; READY599 is unchanged. On the same old corpus
51raw losses become46. New low-word-wrap controls expose27 preexisting
losses, so the enlarged corpus has parent78raw versus child73raw/118state
losses. Zero newly introduced correct-Qfplib deficits. All controls,
incorrect reference answers, losses and regressions remain in reports.
Historical ln remains6/10 fixed,4open; no whole-ln or whole-math GO.

All33086READY counts are identical. DIRTY10197faster/22863equal/26slower;
each regression is one instruction. The extra controls include these
regressions and do not hide their still-correct answers. Allocated code/
data size0, stack640 unchanged on this same corpus, helper stack68.
Only232-byte helper body changes within shared3800B section; every other
function/literal/padding byte, all other sections/tables/deps and the ASM
object match. GenericM0/M4 controls match (not a whole-M4 image build).
Entire public CPP/ASM/ELF independently rebuilds byte-exactly. Linked
near body/table keep exact addresses/bytes, inheriting the parent's
16896 bare packer calls without counting them as fresh. No new mathROM.

Source:{source}
ELF:{elf}
Object:{r['candidate_full_object_sha256']}

Hold this packet unchanged. Independent review, canonical integration,
physical cycles and hardware acceptance are not claimed. Other needed
operations, general pow totality and the original full goal remain OPEN.
'''
(W/'HANDOFF.md').write_text(handoff)
r['files']={p.name:sha(p) for p in sorted(W.iterdir()) if p.is_file()}
(W/'result.json').write_text(json.dumps(r,indent=2)+'\n')
print(json.dumps({k:v for k,v in r.items() if k!='files'},indent=2))

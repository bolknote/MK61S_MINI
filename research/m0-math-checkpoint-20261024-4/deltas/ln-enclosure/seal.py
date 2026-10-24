"""Freeze the strict-radius/selector delta with all broadened losses retained."""
from pathlib import Path
from collections import Counter
import hashlib
import json
import sys

sys.dont_write_bytecode=True
W=Path(__file__).resolve().parent
ROOT=W.parents[1]
BASE=ROOT/'.build/m0-log-ratio-dirty-20261024'
sys.path.insert(0,str(ROOT/'tests'))
from check_stm32_vectors import ElfImage
assert not (W/'result.json').exists()


def sha(p):return hashlib.sha256(p.read_bytes()).hexdigest()
def read(name):return json.loads((W/name).read_text())


q,i,b,c=[read(n) for n in ('qualification.json','isolation.json','public-body-proof.json','certificate.json')]
source,elf=sha(W/'native_eabi_m0_log70.inc'),sha(W/'candidate.elf')
assert source=='44d1d70cd02a52e8ba4de34dd5168e23806b3df59f0a93d814a1fe061158aa76'
assert elf=='36d1662268eaa35b5bd688fb7c2ff16958c1bc46dd92166dab5722e96b6f62f6'
for d in (q,i,b):assert d['source_sha256']==source and d['candidate_ELF_sha256']==elf
assert c['source_sha256']==source
assert q['cases']==len(q['rows'])==39318 and q['unique_inputs']==19659
assert q['actual_ARM_calls']==157272 and q['retained_parent_counts_checked']==29814
assert all(r['correct']['candidate'] and r['correct']['parent'] for r in q['rows'])
assert i['allocated_object_bytes_delta']==0 and all(t['allocated_code_and_data_identical'] for t in i['contexts'])
assert b['entire_ELF_byte_exact_without_exclusions']
assert q['candidate_stack_bytes']==q['parent_stack_bytes']==568
losses=q['remaining_slower_correct_Qfplib']
assert len(losses)==65 and len({r['x'] for r in losses})==34
assert [g['candidate_slower_correct_Qfplib'] for g in q['groups']]==[31,34]
assert all(g['newly_slower_correct_Qfplib']==0 for g in q['groups'])
regress=q['regressions_vs_parent']
assert len(regress)==18992 and all(r['instructions']['candidate']-r['instructions']['parent']==1 for r in regress)
fixed=[r for r in q['rows'] if r['correct']['Qfplib'] and r['instructions']['parent']>r['instructions']['Qfplib']>=r['instructions']['candidate']]
assert len(fixed)==210 and len({r['x'] for r in fixed})==105
(W/'remaining-slower.json').write_text(json.dumps(dict(status='THIRTY_FOUR_RAW_LN_SPEED_INPUTS_OPEN',raw_inputs=34,state_rows=65,rows=losses),indent=2)+'\n')
(W/'regressions.json').write_text(json.dumps(dict(status='ALL_PARENT_REGRESSIONS_RETAINED',state_rows=len(regress),instruction_delta=1,rows=regress),indent=2)+'\n')
old,new=ElfImage(BASE/'candidate.elf'),ElfImage(W/'candidate.elf')


def closure(image,name):
    if name not in image.symbols:
        matches=[n for n in image.symbols if name in n and image.sizes.get(n,0)]
        assert len(matches)==1,(name,matches)
        name=matches[0]
    address,size=image.symbols[name]&~1,image.sizes[name]
    section=next(s for s in image.named_sections.values() if s[3]<=address<s[3]+s[5])
    return address,image.bytes_at(section)[address-section[3]:address-section[3]+size]


names=('mk61_m0_log_ratio70','mk61_m0_log_ratio70_slow','log10_table')
for name in names:assert closure(old,name)==closure(new,name),name
helper=read('control-build.json')
(W/'inherited-helper-proof.json').write_text(json.dumps(dict(status='IDENTICAL_PARENT_HELPER_CLOSURE_REUSED',symbols=list(names),addresses_and_bytes_identical=True,
    parent_helper_proof_sha256=sha(BASE/'helper-proof.json'),inherited_parent_ARM_calls=155608,fresh_helper_calls_claimed=0),indent=2)+'\n')
pins=json.loads((BASE/'input-pins.json').read_text())['files']
for name,digest in pins.items():assert sha(ROOT/name)==digest,name
for name in ('result.json','qualification.json','helper-proof.json','certificate.json','candidate.elf','candidate-full.o'):
    pins[str((BASE/name).relative_to(ROOT))]=sha(BASE/name)
for name in ('tools/generate_m0_log70_table.py','tools/generate_m0_log_table.py'):
    pins[name]=sha(ROOT/name)
(W/'input-pins.json').write_text(json.dumps(dict(status='READ_ONLY_INPUTS_PINNED',files=pins),indent=2)+'\n')
r=dict(status='AUTHOR_PASS_STRICT_LN_ENCLOSURES_WITH_34_EXPANDED_SPEED_INPUTS_OPEN',unique_inputs=19659,public_state_cases=39318,all_cases_profiled=True,
    fresh_public_ARM_calls=157272,candidate_wrong=0,retained_parent_counts_checked=29814,groups=q['groups'],
    old27_raw_deficits_resolved=14,expanded_correct_Qfplib_raw_deficits_fixed=105,new_correct_Qfplib_deficits=0,
    remaining_expanded_raw_inputs=34,remaining_speed_state_rows=65,historical_ln10_fixed=5,historical_ln10_remaining=5,
    vs_parent=dict(faster=18664,equal=1662,slower=18992),all_parent_regression_deltas=1,
    public_stack_bytes_observed=568,parent_public_stack_same_expanded_corpus=568,
    allocated_object_and_linked_bytes_delta=0,new_tables_global_RAM_or_libgcc=False,
    M4_generic_M0_allocated_controls_equal=True,whole_public_ELF_rebuild_byte_exact=True,inherited_helper_ARM_calls=155608,
    source_sha256=source,subnormal_source_sha256=sha(W/'native_eabi_m0_log_subnormal.inc'),candidate_ELF_sha256=elf,
    candidate_full_object_sha256=sha(W/'candidate-full.o'),parent_result_sha256=sha(BASE/'result.json'),
    independent_review='not_claimed',production_integration=False,hardware_accessed=False,physical_cycles_measured=False,goal_complete=False,
    files={p.name:sha(p) for p in sorted(W.iterdir()) if p.is_file()})
(W/'result.json').write_text(json.dumps(r,indent=2)+'\n')
print(json.dumps({k:v for k,v in r.items() if k!='files'},indent=2))

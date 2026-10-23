"""Keep every old range and deficit, bind the new image, run frozen public canaries."""
import hashlib
import json
from pathlib import Path
import struct
import sys

root=Path.cwd();work=Path(__file__).resolve().parent
parent=root/'.build/m0-pow-small-y-stable-v144-20261023'
sys.path.insert(0,str(root/'tests'))
from native_eabi_m0_arm_self_test import Machine,SP


def sha(p):
    return hashlib.sha256(Path(p).read_bytes()).hexdigest()


elf=work/'firmware/mk61s-picocalc-pico-h.elf'
matrix=json.loads((work/'instruction-matrix.json').read_text())
old_matrix=json.loads((parent/'instruction-matrix.json').read_text())
audit=json.loads((work/'result.json').read_text())
old_audit=json.loads((parent/'result.json').read_text())
tiny=json.loads((work/'tiny-profile.json').read_text())
old_tiny=json.loads((parent/'tiny-profile.json').read_text())
assert matrix['owned_elf_sha256']==audit['elf_sha256']==tiny['elf_sha256']==sha(elf)
assert tiny['cases_data']==old_tiny['cases_data']
changed=[];unchanged=[]
for a,b in zip(matrix['chunks'],old_matrix['chunks'],strict=True):
    assert a['operation']==b['operation']
    if a!=b:
        assert a['operation']=='exp'
        assert a['mean_instructions']['own']<b['mean_instructions']['own']
        changed.append(a['index'])
    else:
        unchanged.append(a['index'])
assert len(changed)==3 and len(unchanged)==116
audit_changes=[]
for a,b in zip(audit['groups'],old_audit['groups'],strict=True):
    assert (a['operation'],a['stream'])==(b['operation'],b['stream'])
    if a!=b:
        assert a['operation']=='exp'
        audit_changes.append(a['stream'])
        for x,y in zip(a['rows'],b['rows'],strict=True):
            assert {k:v for k,v in x.items() if k!='own_instructions'}=={k:v for k,v in y.items() if k!='own_instructions'}
            assert x['own_instructions']<=y['own_instructions']
    else:
        assert a['operation']!='exp'
assert len(audit_changes)==5
groups=[dict(operation=g['operation'],stream=g['stream'],cases=g['cases'],
             mean_instructions=g['mean_instructions'],owned_wrong_rounding=g['owned_wrong_rounding'],
             qfplib_wrong_results=g['qfplib_wrong_results'],origin='original117') for g in matrix['groups']]
groups += [dict(operation=g['operation'],stream=g['stream'],cases=g['cases'],
                mean_instructions=g['mean_instructions'],owned_wrong_rounding=g['own_wrong'],
                qfplib_wrong_results=g['qfplib_wrong'],both_correct_cases=g['both_correct_cases'],
                both_correct_mean_instructions=g['both_correct_mean_instructions'],
                both_correct_own_slower=g['both_correct_own_slower'],origin='independent53') for g in audit['groups']]
groups.append(dict(operation='pow',stream='tiny_exponents_normal_bases',cases=168,
                   mean_instructions=dict(own=tiny['own_mean_instructions'],qfplib=tiny['qfplib_mean_instructions']),
                   owned_wrong_rounding=0,qfplib_wrong_results=0,origin='tiny168'))
scores=[sum((g['mean_instructions']['own']<g['mean_instructions']['qfplib']) if op=='faster' else
            (g['mean_instructions']['own']==g['mean_instructions']['qfplib']) if op=='equal' else
            (g['mean_instructions']['own']>g['mean_instructions']['qfplib']) for g in groups)
        for op in ('faster','equal','slower')]
assert scores==[156,2,13] and len(groups)==171 and sum(g['cases'] for g in groups)==30304
report=dict(status='PASS_EXPANDED_COVERAGE_NOT_A_SPEED_PASS',owned_elf_sha256=sha(elf),
    groups=groups,group_count=171,cases=30304,instruction_groups_faster=scores[0],
    instruction_groups_equal=scores[1],instruction_groups_slower=scores[2],owned_wrong_rounding=0,
    original117_groups=dict(faster=115,equal=2,slower=0),
    changed_original_chunks=changed,unchanged_original_chunk_records=len(unchanged),
    original_changes_are_exp_only_and_faster=True,
    independent_changes_are_exp_only_and_every_case_no_slower=True,
    changed_independent_groups=audit_changes,unchanged_independent_group_records=48,
    tiny196_case_records_identical=True,
    raw_deficits=[g for g in groups if g['mean_instructions']['own']>g['mean_instructions']['qfplib']],
    both_correct_subset_mean_deficits=[g for g in groups if g.get('both_correct_cases',0) and g['both_correct_mean_instructions']['own']>g['both_correct_mean_instructions']['qfplib']],
    source_reports={n:sha(work/n) for n in ('instruction-matrix.json','result.json','tiny-profile.json')},
    producer_sha256=sha(__file__),
    scope='All171 previously selected groups are retained. Other116 original chunk records, all48 non-exp independent group records and196 tiny rows are exact V144 copies. Every changed independent exp vector has identical RNE output and no added instructions. Counts are executed ARM instructions with modeled SIO, not physical cycles or an all-input speed guarantee.',
    approved_hardware_package_changed=False,hardware_accessed=False,general_pow_totality_proved=False,goal_complete=False)
(work/'extended-instruction-matrix.json').write_text(json.dumps(report,indent=2)+'\n')

vectors=list(struct.iter_unpack('<3Q',(root/'.build/m0-v138-execution-20261023/inputs/119.bin').read_bytes()[32:]))
assert len(vectors)==30
machine=Machine(elf,True,stack_bytes=16384,instruction_budget=200000000,
                bootrom=root/'research/rp2040-memset-2026-10-21/capture/bootrom.bin')
digest=hashlib.sha256()
for x,y,expected in vectors:
    got=machine.call('_ZN12compact_math3powEdd',x,y)[0]
    assert got==expected
    digest.update(struct.pack('<4Q',x,y,expected,got))
(work/'public-canary.json').write_text(json.dumps(dict(status='PASS_FROZEN_PUBLIC_POW_CANARY_ON_V145',
    cases=30,wrong_rounding=0,result_sha256=digest.hexdigest(),elf_sha256=sha(elf),
    input_sha256=sha(root/'.build/m0-v138-execution-20261023/inputs/119.bin'),
    producer_sha256=sha(__file__),maximum_observed_stack_bytes=SP-machine.stack_lowest,
    scope='Actual public pow calls on the30 frozen negative-factor vectors. Original independent directed-MPFR expected bits. Emulator, not a hardware receipt.',
    hardware_accessed=False,production_promoted=False,goal_complete=False),indent=2)+'\n')
print('PASS: expanded171 groups156/2/13; every old group retained; only exp changed;30 frozen public canaries.')

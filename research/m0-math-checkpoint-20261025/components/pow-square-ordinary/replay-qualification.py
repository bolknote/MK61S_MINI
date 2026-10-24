"""Fresh candidate ARM+MPFR replay of the unchanged63795-input pow corpus.
Parent/control/Qfplib counts from the prior full four-machine run are pinned
and inherited, not counted as new executions. New four-machine probe is separate.
"""
from pathlib import Path
from collections import Counter
import hashlib,json,struct,sys
sys.dont_write_bytecode=True
W=Path(__file__).resolve().parent;ROOT=W.parents[1]
P=ROOT/'.build/m0-asin-scaled-bound-v164-20261023';B=ROOT/'.build/m0-exp-cached-product-20261024';T=ROOT/'.build/m0-pow-square-exact-20261024';Q=ROOT/'.build/m0-float-fma-qualification-20261023'
sys.path.insert(0,str(Q));sys.path.insert(0,str(Q/'support'))
from native_eabi_m0_arm_self_test import Machine,SP
from check_stm32_vectors import ElfImage
from m0_mpfr_oracle import Oracle
from oracles import equal
sha=lambda p:hashlib.sha256(p.read_bytes()).hexdigest()
b=json.loads((W/'build.json').read_text());old=json.loads((T/'qualification.json').read_text());tb=json.loads((T/'build.json').read_text())
assert sha(W/'candidate.elf')==b['images']['candidate']['ELF_sha256']
assert sha(T/'candidate.elf')==old['candidate_ELF_sha256']
assert b['square_source_sha256']==tb['square_source_sha256']
base=P/'firmware/mk61s-picocalc-pico-h.elf';rom=ROOT/'research/rp2040-memset-2026-10-21/capture/bootrom.bin'
m=Machine(base,True,bootrom=rom);ElfImage(B/'candidate.elf').load(m.uc);ElfImage(W/'candidate.elf').load(m.uc)
states={'READY':struct.pack('<7I',0,0,0,0,0,0,1),'DIRTY':struct.pack('<7I',17,3,17,3,5,2,3)}
oracle=Oracle();expected_by_pair={};rows=[];deltas=Counter();old_deltas=Counter()
for prior in old['rows']:
 if len(rows)%4096==0:print('progress',len(rows),'/',len(old['rows']),flush=True)
 x,y=int(prior['x'],16),int(prior['y'],16);key=(x,y)
 if key not in expected_by_pair:expected_by_pair[key]=oracle.reference('pow',x,y)
 expected=expected_by_pair[key]
 assert equal(int(prior['expected'],16),expected,64)
 state=states[prior['SIO']];m.uc.mem_write(0xd0000060,state)
 got,_,cost=m.call('_ZN12compact_math3powEdd',x,y,count=True)
 assert equal(got,expected,64),(hex(x),hex(y),prior['SIO'],hex(got),hex(expected))
 assert got==int(prior['outputs']['parent'],16)
 after=bytes(m.uc.mem_read(0xd0000060,28))
 if prior['SIO']=='DIRTY':assert after==state
 else:assert not(struct.unpack('<7I',after)[6]&2)
 if y&0xffffffff:
  assert cost==prior['instructions']['parent'],(prior['x'],prior['y'],prior['SIO'],'nonzero-low path changed',cost,prior['instructions']['parent'])
 row=dict(prior);row['outputs']=dict(prior['outputs'],previous_trial=prior['outputs']['candidate'],candidate=f'{got:016X}')
 row['instructions']=dict(prior['instructions'],previous_trial=prior['instructions']['candidate'],candidate=cost)
 row['correct']=dict(prior['correct'],candidate=True);rows.append(row)
 deltas[cost-prior['instructions']['parent']]+=1;old_deltas[cost-prior['instructions']['candidate']]+=1
loss=lambda r,label:r['correct']['Qfplib'] and r['instructions'][label]>r['instructions']['Qfplib']
oldrows=[r for r in rows if r['group']=='historical153'];remaining=[r for r in rows if loss(r,'candidate')];new=[r for r in remaining if not loss(r,'parent')]
assert len(expected_by_pair)==old['unique_inputs'] and len(rows)==old['public_state_cases']
out=dict(status='AUTHOR_PUBLIC_POW_EXACT_SQUARE_ORDINARY_FULL_PROFILE',
 candidate_source_sha256=b['images']['candidate']['source_sha256'],candidate_ELF_sha256=b['images']['candidate']['ELF_sha256'],
 square_source_sha256=b['square_source_sha256'],ordinary_source_sha256=b['ordinary_source_sha256'],source_alias_CPP_sha256=b['source_alias_CPP_sha256'],
 unique_inputs=len(expected_by_pair),public_state_cases=len(rows),actual_fresh_public_ARM_calls=len(rows),fresh_MPFR_calls=len(expected_by_pair),MPFR_version=oracle.version,
 inherited_parent_control_Qfplib_count_rows=len(rows),inherited_baseline_ARM_calls_added=0,pinned_four_machine_trial_qualification_sha256=sha(T/'qualification.json'),
 candidate_wrong=0,all_candidate_returned_bits_identical_parent=True,nonzero_low_exponent_words_counts_identical_parent=True,
 speed_comparison_uses_all_numerically_correct_reference_rows_without_domain_filter=True,
 original153_parent_remaining=len({(r['x'],r['y']) for r in oldrows if loss(r,'parent')}),
 original153_candidate_remaining=len({(r['x'],r['y']) for r in oldrows if loss(r,'candidate')}),
 all_parent_raw_losses=len({(r['x'],r['y']) for r in rows if loss(r,'parent')}),all_candidate_raw_losses=len({(r['x'],r['y']) for r in remaining}),
 new_candidate_raw_losses=len({(r['x'],r['y']) for r in new}),
 vs_parent=dict(faster=sum(v for k,v in deltas.items() if k<0),equal=deltas[0],slower=sum(v for k,v in deltas.items() if k>0)),
 parent_instruction_delta_counts=dict(sorted(deltas.items())),previous_trial_instruction_delta_counts=dict(sorted(old_deltas.items())),
 candidate_observed_stack_bytes=SP-m.stack_lowest,parent_observed_stack_bytes_inherited=old['observed_stacks']['parent'],
 PCS_SP_SIO_bounded_writes_every_call=True,all_cases_profiled=True,corpus_pins=old['corpus_pins'],
 hardware_accessed=False,whole_math_GO=False,independent_review_pending=True,
 rows=rows,remaining_slower_correct_Qfplib=remaining,new_slower_correct_Qfplib=new)
(W/'qualification.json').write_text(json.dumps(out,indent=2)+'\n')
print(json.dumps({k:v for k,v in out.items() if k not in ('rows','remaining_slower_correct_Qfplib','new_slower_correct_Qfplib','corpus_pins')},indent=2))
for r in new[:20]:print('NEW',r['x'],r['y'],r['SIO'],r['instructions'])

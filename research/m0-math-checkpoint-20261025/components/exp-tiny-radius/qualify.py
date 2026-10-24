"""Full old exp replay and every tiny midpoint's two exact transitions.

Candidate ARM is fresh for every input/state. Old parent/Qfp rows are
pinned inherited acquisitions, independently checked by the short probe.
For every new input both candidate and Qfp are freshly profiled. No
nominal-domain or incorrect-reference output is removed from raw records.
"""
from pathlib import Path
from collections import Counter
import gzip,hashlib,json,struct,sys
sys.dont_write_bytecode=True
W=Path(__file__).resolve().parent;ROOT=W.parents[1]
P=ROOT/'.build/m0-asin-scaled-bound-v164-20261023'
B=ROOT/'.build/m0-exp-cached-product-20261024'
Q=ROOT/'.build/m0-float-fma-qualification-20261023'
sys.path[:0]=[str(Q),str(Q/'support'),str(ROOT/'tests')]
from native_eabi_m0_arm_self_test import Machine,SP
from check_stm32_vectors import ElfImage
from m0_mpfr_oracle import Oracle
from oracles import equal
sha=lambda p:hashlib.sha256(p.read_bytes()).hexdigest()
build=json.loads((W/'build.json').read_text());assert sha(W/'candidate.elf')==build['candidate_ELF_sha256']
old=json.loads((B/'qualification.json').read_text())
assert old['unique_inputs']==48763 and old['public_state_cases']==97526
previous={(int(r['x'],16),r['SIO']):r for r in old['rows']}
probe=json.loads((W/'probe.json').read_text())
assert probe['candidate_ELF_sha256']==build['candidate_ELF_sha256'] and probe['new_raw_losses']==0
probe_rows={(int(r['x'],16),r['SIO']):r for r in probe['rows']}
jobs={}
for row in old['rows']:jobs.setdefault(int(row['x'],16),'old48763:'+row['group'])
tiny_data=(W/'tiny-inputs.bin').read_bytes();groups=json.loads((W/'tiny-input-groups.json').read_text())
for (x,),group in zip(struct.iter_unpack('<Q',tiny_data),groups):jobs.setdefault(x,group)
for row in probe['rows']:jobs.setdefault(int(row['x'],16),'probe:'+row['group'])
(W/'qualification-inputs.bin').write_bytes(b''.join(struct.pack('<Q',x) for x in jobs))
rom=ROOT/'research/rp2040-memset-2026-10-21/capture/bootrom.bin'
m=Machine(P/'firmware/mk61s-picocalc-pico-h.elf',True,bootrom=rom)
image=ElfImage(W/'candidate.elf');image.load(m.uc);m.elf.symbols['candidate_exp']=image.symbols['mk61_m0_exp']
ref=Machine(ROOT/'.build/m0-v138-execution-20261023/reference/reference.elf',True)
states={'READY':struct.pack('<7I',0,0,0,0,0,0,1),'DIRTY':struct.pack('<7I',17,3,17,3,5,2,3)}
oracle=Oracle();remaining=[];new=[];old_losses=set();old_parent_losses=set();all_losses=set()
parent_increases=[];old_deltas=Counter();tiny_costs=Counter();comparison=Counter();counts=Counter()
nan_shortcuts=0;raw_rows=0;tiny_losses=set();historical=set();fresh_qfp_calls=0
records=W/'qualification-records.jsonl.gz'
print('prepared',len(jobs),'inputs; old48763 unchanged; new',len(jobs)-48763,flush=True)
with gzip.open(records,'wt',encoding='utf-8',compresslevel=6) as raw:
 for index,(x,group) in enumerate(jobs.items()):
  if index%2048==0:print('qualification',index,'/',len(jobs),'losses',len(all_losses),flush=True)
  expected=oracle.reference('exp',x)
  magnitude=x&0x7fffffffffffffff
  nan_shortcuts+=magnitude>0x7ff0000000000000 and not bool(x&(1<<51))
  for state_name,state in states.items():
   prior=previous.get((x,state_name));smoke=probe_rows.get((x,state_name))
   if prior:assert equal(expected,int(prior['expected'],16),64)
   m.uc.mem_write(0xd0000060,state)
   got,_,cost=m.call('candidate_exp',x,count=True)
   assert equal(got,expected,64),(hex(x),hex(got),hex(expected))
   if prior:assert got==int(prior['outputs']['candidate'],16),(hex(x),'changed raw bits')
   after=bytes(m.uc.mem_read(0xd0000060,28))
   if state_name=='DIRTY':assert after==state
   else:assert not(struct.unpack('<7I',after)[6]&2)
   if prior:
    qgot=int(prior['outputs']['Qfplib'],16);qcost=prior['instructions']['Qfplib'];parent=prior['instructions']['candidate']
    old_deltas[cost-parent]+=1
   else:
    ref.uc.mem_write(0xd0000060,state)
    qgot,_,qcost=ref.call('qfp_dexp',x,count=True);fresh_qfp_calls+=1
    assert bytes(ref.uc.mem_read(0xd0000060,28))==state
    parent=smoke['instructions']['parent'] if smoke else None
   qcorrect=equal(qgot,expected,64)
   if prior:assert qcorrect==prior['correct']['Qfplib']
   if smoke:
    assert cost==smoke['instructions']['candidate'] and qcost==smoke['instructions']['Qfplib']
   row=dict(x=f'{x:016X}',group=group,SIO=state_name,expected=f'{expected:016X}',
            candidate=f'{got:016X}',candidate_instructions=cost,Qfplib=f'{qgot:016X}',
            Qfplib_instructions=qcost,Qfplib_correct=qcorrect,parent_instructions=parent,
            Qfplib_acquisition='inherited accepted cached-product corpus' if prior else 'fresh')
   raw.write(json.dumps(row,separators=(',',':'))+'\n');raw_rows+=1
   counts['candidate_ARM_calls']+=1
   if qcorrect:
    comparison['faster' if cost<qcost else 'equal' if cost==qcost else 'slower']+=1
    if cost>qcost:
     remaining.append(row);all_losses.add(x)
     if prior:old_losses.add(x)
     if parent is not None and parent<=qcost:new.append(row)
     if 0x3c90000000000000<magnitude<0x3d90000000000000:tiny_losses.add(x)
     if prior and prior['group']=='historical16':historical.add(x)
    if prior and parent>qcost:old_parent_losses.add(x)
   else:counts['wrong_Qfplib_rows_retained']+=1
   if parent is not None and cost>parent:parent_increases.append(row)
   if 0x3c90000000000000<magnitude<0x3d90000000000000:tiny_costs[cost]+=1
assert raw_rows==2*len(jobs)
report=dict(status='AUTHOR_QUALIFIED_EXACT_TINY_EXP_ALL_MIDPOINT_TRANSITIONS',
 source_sha256=build['source_sha256'],candidate_ELF_sha256=build['candidate_ELF_sha256'],
 unique_inputs=len(jobs),profiled_states=raw_rows,fresh_candidate_ARM_calls=counts['candidate_ARM_calls'],
 fresh_Qfplib_ARM_calls=fresh_qfp_calls,fresh_ARM_calls=counts['candidate_ARM_calls']+fresh_qfp_calls,
 old_parent_Qfplib_rows_pinned_not_new=97526,inherited_ARM_calls_added=0,
 oracle_evaluations=len(jobs),actual_directed_MPFR_input_conversions=len(jobs)-nan_shortcuts,
 NaN_shortcuts_without_MPFR=nan_shortcuts,MPFR_version=oracle.version,
 old48763_parent_raw_losses=len(old_parent_losses),old48763_candidate_raw_losses=len(old_losses),
 union_candidate_raw_losses=len(all_losses),new_known_parent_raw_losses=len({r['x'] for r in new}),
 all_new_tiny_midpoint_raw_losses=len(tiny_losses),old_historical16_remaining=len(historical),
 wrong=0,old_raw_return_bits_identical=True,correct_Qfplib_comparison=dict(comparison),
 wrong_Qfplib_state_rows_retained=counts['wrong_Qfplib_rows_retained'],
 old_parent_cost_deltas=dict(sorted(old_deltas.items())),parent_cost_increase_rows=len(parent_increases),
 tiny_instruction_counts=dict(sorted(tiny_costs.items())),candidate_stack_bytes=SP-m.stack_lowest,
 qualification_records_sha256=sha(records),qualification_records_state_rows=raw_rows,
 input_words_sha256=sha(W/'qualification-inputs.bin'),old_qualification_sha256=sha(B/'qualification.json'),
 all_inputs_fully_profiled=True,no_nominal_domain_filter=True,hardware_accessed=False,
 independent_review_pending=True,goal_complete=False,remaining=remaining,new=new)
(W/'qualification.json').write_text(json.dumps(report,indent=2)+'\n')
(W/'retained-parent-regressions.json').write_text(json.dumps(parent_increases,indent=2)+'\n')
print(json.dumps({k:v for k,v in report.items() if k not in ('remaining','new','old_parent_cost_deltas','tiny_instruction_counts')},indent=2))
assert not new and not tiny_losses

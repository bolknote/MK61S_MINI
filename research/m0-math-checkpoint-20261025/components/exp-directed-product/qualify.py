"""Preserve every prior456750 exp input; acquire new directed/broad midpoint controls."""
from pathlib import Path
from collections import Counter
import gzip,hashlib,json,struct,sys
sys.dont_write_bytecode=True
W=Path(__file__).resolve().parent;ROOT=W.parents[1]
P=ROOT/'.build/m0-asin-scaled-bound-v164-20261023';E=ROOT/'.build/m0-exp-dyadic-product-20261024';Q=ROOT/'.build/m0-float-fma-qualification-20261023'
sys.path[:0]=[str(Q),str(Q/'support'),str(ROOT/'tests')]
from native_eabi_m0_arm_self_test import Machine,SP
from check_stm32_vectors import ElfImage
from m0_mpfr_oracle import Oracle
from oracles import equal
sha=lambda p:hashlib.sha256(p.read_bytes()).hexdigest()
b=json.loads((W/'build.json').read_text());assert sha(W/'candidate.elf')==b['candidate_ELF_sha256']
oldmeta=json.loads((E/'qualification.json').read_text());oldrecords=E/'qualification-records.jsonl.gz'
assert sha(oldrecords)==oldmeta['qualification_records_sha256']
previous={};jobs={}
with gzip.open(oldrecords,'rt',encoding='utf-8') as f:
 for line in f:
  row=json.loads(line);x=int(row['x'],16);previous[x,row['SIO']]=row;jobs.setdefault(x,'old456750:'+row['group'])
assert len(jobs)==456750 and len(previous)==913500
proof=json.loads((W/'certificate.json').read_text());assert proof['source_sha256']==b['source_sha256']
assert proof['private_return_proof_sha256']==sha(W/'private-return-proof.json')
tiny_data=(W/'public-new-inputs.bin').read_bytes();groups=json.loads((W/'public-new-groups.json').read_text())
for (x,),group in zip(struct.iter_unpack('<Q',tiny_data),groups):jobs.setdefault(x,group)
probe=json.loads((W/'probe.json').read_text())
assert probe['candidate_ELF_sha256']==b['candidate_ELF_sha256'] and not probe['new_measured_parent_raw_losses']
smoke={(int(r['x'],16),r['SIO']):r for r in probe['rows']}
for row in probe['rows']:jobs.setdefault(int(row['x'],16),'probe:'+row['group'])
(W/'qualification-inputs.bin').write_bytes(b''.join(struct.pack('<Q',x) for x in jobs))
rom=ROOT/'research/rp2040-memset-2026-10-21/capture/bootrom.bin'
m=Machine(P/'firmware/mk61s-picocalc-pico-h.elf',True,bootrom=rom)
im=ElfImage(W/'candidate.elf');im.load(m.uc);m.elf.symbols['candidate_exp']=im.symbols['mk61_m0_exp']
ref=Machine(ROOT/'.build/m0-v138-execution-20261023/reference/reference.elf',True)
states={'READY':struct.pack('<7I',0,0,0,0,0,0,1),'DIRTY':struct.pack('<7I',17,3,17,3,5,2,3)}
oracle=Oracle();remaining=[];new=[];regressions=[];old_losses=set();parent_losses=set();old48763_losses=set();all_losses=set();tiny_losses=set();historical=set()
comparison=Counter();deltas=Counter();tinycosts=Counter();calls=qcalls=nan_shortcuts=wrong_ref=0
records=W/'qualification-records.jsonl.gz'
print('prepared',len(jobs),'inputs;456750previous unchanged;new',len(jobs)-456750,flush=True)
with gzip.open(records,'wt',encoding='utf-8',compresslevel=6) as raw:
 for index,(x,group) in enumerate(jobs.items()):
  if index%4096==0:print('qualification',index,'/',len(jobs),'losses',len(all_losses),flush=True)
  expected=oracle.reference('exp',x);magnitude=x&0x7fffffffffffffff
  nan_shortcuts+=magnitude>0x7ff0000000000000 and not bool(x&(1<<51))
  for state_name,state in states.items():
   prior=previous.get((x,state_name));probed=smoke.get((x,state_name))
   m.uc.mem_write(0xd0000060,state)
   got,_,cost=m.call('candidate_exp',x,count=True);calls+=1
   assert equal(got,expected,64),(hex(x),hex(got),hex(expected))
   after=bytes(m.uc.mem_read(0xd0000060,28))
   if state_name=='DIRTY':assert after==state
   else:assert not(struct.unpack('<7I',after)[6]&2)
   if prior:
    assert equal(expected,int(prior['expected'],16),64) and got==int(prior['candidate'],16)
    qgot=int(prior['Qfplib'],16);qcost=prior['Qfplib_instructions'];parent=prior['candidate_instructions']
    deltas[cost-parent]+=1
   else:
    ref.uc.mem_write(0xd0000060,state);qgot,_,qcost=ref.call('qfp_dexp',x,count=True);qcalls+=1
    assert bytes(ref.uc.mem_read(0xd0000060,28))==state
    parent=probed['instructions'].get('parent') if probed else None
   qcorrect=equal(qgot,expected,64)
   if prior:assert qcorrect==prior['Qfplib_correct']
   if probed:assert cost==probed['instructions']['candidate'] and qcost==probed['instructions']['Qfplib']
   row=dict(x=f'{x:016X}',group=group,SIO=state_name,expected=f'{expected:016X}',candidate=f'{got:016X}',candidate_instructions=cost,Qfplib=f'{qgot:016X}',Qfplib_instructions=qcost,Qfplib_correct=qcorrect,parent_instructions=parent,Qfplib_acquisition='inherited dyadic-exp corpus' if prior else 'fresh')
   raw.write(json.dumps(row,separators=(',',':'))+'\n')
   if parent is not None and cost>parent:regressions.append(row)
   if qcorrect:
    comparison['faster' if cost<qcost else 'equal' if cost==qcost else 'slower']+=1
    if prior and parent>qcost:parent_losses.add(x)
    if cost>qcost:
     remaining.append(row);all_losses.add(x)
     if prior:old_losses.add(x)
     if prior and 'old48763:' in prior['group']:old48763_losses.add(x)
     if parent is not None and parent<=qcost:new.append(row)
     if 0x3c90000000000000<magnitude<0x3df0000000000000:tiny_losses.add(x)
     if prior and prior['group'].endswith(':historical16'):historical.add(x)
   else:wrong_ref+=1
   if 0x3c90000000000000<magnitude<0x3df0000000000000:tinycosts[cost]+=1
report=dict(status='AUTHOR_QUALIFIED_DIRECTED_EXP_AND_77_INSTRUCTION_FRACTION_PRODUCT',
 source_sha256=b['source_sha256'],candidate_ELF_sha256=b['candidate_ELF_sha256'],unique_inputs=len(jobs),profiled_states=2*len(jobs),
 fresh_candidate_ARM_calls=calls,fresh_Qfplib_ARM_calls=qcalls,fresh_ARM_calls=calls+qcalls,
 inherited_parent_Qfplib_rows913500_not_new=True,inherited_ARM_calls_added=0,
 oracle_evaluations=len(jobs),actual_directed_MPFR_input_conversions=len(jobs)-nan_shortcuts,NaN_shortcuts_without_MPFR=nan_shortcuts,MPFR_version=oracle.version,
 old456750_parent_raw_losses=len(parent_losses),old456750_candidate_raw_losses=len(old_losses),
 old48763_candidate_raw_losses=len(old48763_losses),union_candidate_raw_losses=len(all_losses),
 new_known_parent_raw_losses=len({r['x'] for r in new}),tiny_correct_reference_raw_losses=len(tiny_losses),
 historical_exp16_remaining=len(historical),wrong=0,old456750_raw_return_bits_identical=True,
 correct_Qfplib_comparison=dict(comparison),wrong_Qfplib_state_rows_retained=wrong_ref,
 old_parent_cost_deltas=dict(sorted(deltas.items())),known_parent_cost_increase_rows=len(regressions),
 tiny_instruction_counts=dict(sorted(tinycosts.items())),candidate_stack_bytes=SP-m.stack_lowest,
 qualification_records_sha256=sha(records),qualification_records_state_rows=2*len(jobs),
 input_words_sha256=sha(W/'qualification-inputs.bin'),old_qualification_records_sha256=sha(oldrecords),
 all_inputs_fully_profiled=True,no_nominal_domain_filter=True,hardware_accessed=False,
 independent_review_pending=True,goal_complete=False,remaining=remaining,new=new)
(W/'qualification.json').write_text(json.dumps(report,indent=2)+'\n')
(W/'retained-parent-regressions.json').write_text(json.dumps(regressions,indent=2)+'\n')
print(json.dumps({k:v for k,v in report.items() if k not in ('remaining','new','old_parent_cost_deltas','tiny_instruction_counts')},indent=2))
assert not new and not tiny_losses

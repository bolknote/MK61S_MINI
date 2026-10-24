"""Recount saved raw records only. No ARM execution or MPFR evaluation."""
import gzip,hashlib,json,struct
from collections import Counter
from pathlib import Path
R=Path('/Users/bolk/Projects/MK61S_MINI');O=Path(__file__).resolve().parent;W=R/'.build/m0-exp-near-one-20261024';P=R/'.build/m0-exp-directed-product-20261024'
def ref(p):p=Path(p);data=p.read_bytes();return dict(path=str(p),bytes=len(data),sha256=hashlib.sha256(data).hexdigest())
def equivalent(a,b):return a==b or ((int(a,16)&0x7fffffffffffffff)>0x7ff0000000000000 and (int(b,16)&0x7fffffffffffffff)>0x7ff0000000000000)
result=json.loads((W/'result.json').read_text());meta=json.loads((W/'qualification.json').read_text())
raw=W/'qualification-records.jsonl.gz';oldraw=P/'qualification-records.jsonl.gz'
assert ref(raw)['sha256']==meta['qualification_records_sha256']
words=(W/'qualification-inputs.bin').read_bytes();oldwords=(P/'qualification-inputs.bin').read_bytes()
assert len(words)==490031*8 and len(oldwords)==467366*8 and words[:len(oldwords)]==oldwords
inputs=[f'{v[0]:016X}'for v in struct.iter_unpack('<Q',words)]
assert len(set(inputs))==490031
audit=json.loads((W/'remaining-parent-audit.json').read_text());audit_rows={(r['x'],r['SIO']):r for r in audit['rows']}
assert len(audit_rows)==36
comparison=Counter();deltas=Counter();increase_scopes=Counter();wrong_qfp=0
old_parent_losses=set();old_new_losses=set();all_losses=set();increases=[];oldbits=0;remaining=0;old_cases=0
original={r['x']for r in json.loads((W/'original-exp16.json').read_text())['rows']};original_rows=0
with gzip.open(raw,'rt')as current,gzip.open(oldraw,'rt')as old:
 previous=iter(old)
 for i,line in enumerate(current):
  row=json.loads(line);x=row['x'];state=row['SIO'];cost=row['candidate_instructions'];qcost=row['Qfplib_instructions'];qcorrect=row['Qfplib_correct']
  assert x==inputs[i//2]and state==('READY'if i%2==0 else 'DIRTY')
  assert equivalent(row['candidate'],row['expected'])
  assert qcorrect==equivalent(row['Qfplib'],row['expected'])
  parent=row['parent_instructions']
  if i<934732:
   before=json.loads(next(previous));assert (x,state)==(before['x'],before['SIO'])
   assert row['candidate']==before['candidate']and row['expected']==before['expected'];oldbits+=1
   for key in ['Qfplib','Qfplib_instructions','Qfplib_correct']:assert row[key]==before[key]
   assert parent==before['candidate_instructions'];old_cases+=1
   if qcorrect and parent>qcost:old_parent_losses.add(x)
  if qcorrect:
   comparison['faster'if cost<qcost else 'slower'if cost>qcost else 'equal']+=1
   if cost>qcost:
    remaining+=1;all_losses.add(x)
    if i<934732:old_new_losses.add(x)
    bound=parent
    if bound is None:
     a=audit_rows[x,state]
     for key in ['candidate','candidate_instructions','expected','Qfplib','Qfplib_instructions']:assert a[key]==row[key]
     bound=a['parent_instructions']
    assert bound>qcost,('new loss',x,state)
  else:wrong_qfp+=1
  if parent is not None and cost>parent:
   delta=cost-parent;deltas[delta]+=1;increases.append((x,state,delta))
   scope='wrong_Qfplib'if not qcorrect else 'already_losing_correct_Qfplib'if parent>qcost else 'still_no_slower_correct_Qfplib'
   increase_scopes[scope]+=1
  if x in original:
   assert qcorrect and cost<qcost;original_rows+=1
  if i%300000==0:print('saved-records',i,flush=True)
 assert i+1==980062 and next(previous,None)is None
assert old_cases==oldbits==934732 and len(old_parent_losses)==1896 and len(old_new_losses)==196
assert old_new_losses<=old_parent_losses and len(old_parent_losses-old_new_losses)==1700
assert len(all_losses)==214 and len(all_losses-old_new_losses)==18 and remaining==428
assert original_rows==32 and len(original)==16
assert dict(comparison)==result['correct_Qfplib_state_comparison']and wrong_qfp==407820
assert len(increases)==5712 and {str(k):v for k,v in deltas.items()}==result['retained_positive_instruction_deltas']
assert dict(increase_scopes)==result['retained_cost_increase_scopes']
saved_increase=json.loads((W/'retained-parent-regressions.json').read_text())
assert sorted(increases)==sorted((r['x'],r['SIO'],r['candidate_instructions']-r['parent_instructions'])for r in saved_increase)
out=dict(status='PASS_SAVED_RAW_ACCOUNTING_NO_REEXECUTION',raw=ref(raw),parent_raw=ref(oldraw),
 input_words=ref(W/'qualification-inputs.bin'),parent_input_words=ref(P/'qualification-inputs.bin'),
 all980062_rows_exactly_one_per_input_and_SIO=True,old934732_results_reference_costs_and_raw_bits_bound=True,
 same467366_loss_counts=[1896,196],same_inputs_fixed=1700,union490031_losses=214,old_remaining=196,new_preexisting_remaining=18,
 all428_remaining_states_parent_bound=True,new_loss_states=0,correct_Qfplib_comparison=dict(comparison),
 wrong_Qfplib_state_rows_retained=wrong_qfp,cost_increase_state_rows=len(increases),positive_deltas=dict(deltas),cost_increase_scopes=dict(increase_scopes),
 original16_rows_strict=32,reviewed_whole507_preserved=dict(no_slower=422,strict=413,equal=9),
 author423_separate_union_not_promoted=True,ARM_calls=0,MPFR_evaluations=0,other_operation_qualifications_added=False)
with (O/'accounting.json').open('x')as f:json.dump(out,f,indent=2);f.write('\n')
print(json.dumps(ref(O/'accounting.json'),indent=2))

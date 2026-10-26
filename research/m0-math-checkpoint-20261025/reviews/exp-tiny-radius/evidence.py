"""Independently reconcile streamed sealed measurements; no broad ARM replay."""
from pathlib import Path
from collections import Counter
import gzip,hashlib,json,struct,sys
sys.dont_write_bytecode=True
from model import LOW,HIGH,midpoint_model,public_tiny_cost
O=Path(__file__).resolve().parent;R=O.parents[1];P=R/'.build/m0-exp-tiny-radius-20261024';B=R/'.build/m0-exp-cached-product-20261024'
def read(p):return json.loads(Path(p).read_text())
def sha(p):return hashlib.sha256(Path(p).read_bytes()).hexdigest()
def equal(x,y):return bool(x&0x7fffffffffffffff>0x7ff0000000000000 and x&(1<<51)) if y&0x7fffffffffffffff>0x7ff0000000000000 else x==y
def key(r):return (int(r['x'],16),r['SIO'])
q=read(P/'qualification.json');old=read(B/'qualification.json');probe=read(P/'probe.json');audit=read(P/'remaining-parent-audit.json')
previous={key(r):r for r in old['rows']};smoke={key(r):r for r in probe['rows']};audited={key(r):r for r in audit['rows']};reported={key(r):r for r in q['remaining']}
assert len(previous)==97526 and len(reported)==1338 and len(audited)==960
assert audit['fresh_parent_ARM_calls']==960 and audit['fresh_MPFR_calls']==0
assert q['candidate_ELF_sha256']==probe['candidate_ELF_sha256']==audit['candidate_ELF_sha256']==sha(P/'candidate.elf')
input_states={};expected_bits={};group_for={};comparison=Counter();costs=Counter();regressions=[];old_deltas=Counter();reg_delta=Counter();losses={};old_losses=set();old_parent_losses=set();old_count=0;fresh_Q=0;wrong_Q=0;tiny_correct=0;all_rows=0;probe_reused=0;parent_audit_used=0
records=P/'qualification-records.jsonl.gz';assert sha(records)==q['qualification_records_sha256']
with gzip.open(records,'rt',encoding='utf-8') as data:
 for line in data:
  row=json.loads(line);x,state=key(row);assert state in ('READY','DIRTY')
  bit=1 if state=='READY' else 2;assert not(input_states.get(x,0)&bit);input_states[x]=input_states.get(x,0)|bit
  expected=int(row['expected'],16);got=int(row['candidate'],16);qgot=int(row['Qfplib'],16)
  assert equal(got,expected) and equal(qgot,expected)==row['Qfplib_correct']
  if x in expected_bits:assert expected_bits[x]==got
  else:expected_bits[x]=got;group_for[x]=row['group']
  k=(x,state);before=previous.get(k);sample=smoke.get(k);cost=row['candidate_instructions'];qp=row['Qfplib_instructions'];parent=row['parent_instructions']
  if before:
   old_count+=1
   assert row['Qfplib_acquisition']=='inherited accepted cached-product corpus'
   assert got==int(before['outputs']['candidate'],16) and equal(expected,int(before['expected'],16))
   assert qgot==int(before['outputs']['Qfplib'],16) and qp==before['instructions']['Qfplib'] and row['Qfplib_correct']==before['correct']['Qfplib']
   assert parent==before['instructions']['candidate']
   old_deltas[cost-parent]+=1
   if before['correct']['Qfplib'] and parent>qp:old_parent_losses.add(x)
  else:
   fresh_Q+=1;assert row['Qfplib_acquisition']=='fresh'
   if sample:
    assert parent==sample['instructions']['parent'] and cost==sample['instructions']['candidate'] and qp==sample['instructions']['Qfplib']
    assert got==int(sample['outputs']['candidate'],16)==int(sample['outputs']['parent'],16)
   else:assert parent is None
  mag=x&0x7fffffffffffffff
  if LOW<mag<HIGH:
   assert got==midpoint_model(x) and cost==public_tiny_cost(x)
   costs[cost]+=1
   if row['Qfplib_correct']:assert cost<qp;tiny_correct+=1
  if parent is not None and cost>parent:
   assert cost<qp;regressions.append(row);reg_delta[cost-parent]+=1
  if row['Qfplib_correct']:
   comparison['faster' if cost<qp else 'equal' if cost==qp else 'slower']+=1
   if cost>qp:
    assert k in reported and reported[k]==row
    if before:old_losses.add(x)
    if parent is None:
     assert k in audited
     parent=audited[k]['parent_instructions'];assert audited[k]==dict(row,parent_instructions=parent);parent_audit_used+=1
    elif not before:probe_reused+=1
    assert parent>qp
    losses.setdefault(x,[]).append(row)
  else:wrong_Q+=1
  all_rows+=1
assert len(input_states)==163675 and all(v==3 for v in input_states.values()) and all_rows==327350
inputs={x[0] for x in struct.iter_unpack('<Q',(P/'qualification-inputs.bin').read_bytes())};assert inputs==set(input_states)
assert old_count==97526 and fresh_Q==229824 and parent_audit_used==960 and probe_reused==70
assert len(old_parent_losses)==395 and len(old_losses)==154 and old_losses<=old_parent_losses
fixed=old_parent_losses-old_losses;assert len(fixed)==241
assert len(losses)==669 and set(losses)=={k[0] for k in reported}
old_inputs={k[0] for k in previous};extra=set(losses)-old_inputs
assert len(extra)==515
dense={x for x in extra if group_for[x]=='dense_domain_edges'};ordinary=extra-dense
assert len(dense)==514 and ordinary=={0xc08357d5691b8c00}
assert all(HIGH<=(x&0x7fffffffffffffff)<=HIGH+256 for x in dense)
assert comparison==Counter(faster=210984,slower=1338) and wrong_Q==115028
assert len(regressions)==13234 and regressions==read(P/'retained-parent-regressions.json')
assert costs==Counter({int(k):v for k,v in q['tiny_instruction_counts'].items()})
assert old_deltas==Counter({int(k):v for k,v in q['old_parent_cost_deltas'].items()})
# Verify every valid pair of integer transition neighbors from the universal
# cell construction occurs in the actual acquisition, not only a model file.
prepared={x[0] for x in struct.iter_unpack('<Q',(P/'tiny-inputs.bin').read_bytes())}
transition_locations=0;excluded=Counter()
for e in range(-54,-38):
 for neg in (0,1):
  s=-e-neg;step=1<<(s-1);qshift=55-e-2*s
  first=((1<<52)+step-1)//step;first+=int(first%2==0)
  last=(1<<53)//step;last-=int(last%2==0)
  for odd in range(first,last+1,2):
   midpoint=odd*step;floor=(odd*odd)>>qshift
   for d in (floor,floor+1):
    m=midpoint+(d if neg else -d)
    if not 1<<52<=m<1<<53:excluded['outside_this_binade']+=1;continue
    x=(neg<<63)|((e+1023)<<52)|(m-(1<<52))
    if not LOW<(x&0x7fffffffffffffff)<HIGH:excluded['caller_domain_endpoint']+=1;continue
    assert x in prepared and x in inputs and expected_bits[x]==midpoint_model(x)
    transition_locations+=1
assert transition_locations==98303 and excluded==Counter(outside_this_binade=2,caller_domain_endpoint=1)
for x in [LOW,LOW-1,LOW+1,(970<<52)-1,970<<52,HIGH-1,HIGH,HIGH+1]:
 for s in (0,1<<63):assert x|s in inputs
nan_shortcuts=sum(x&0x7fffffffffffffff>0x7ff0000000000000 and not(x&(1<<51)) for x in inputs)
assert nan_shortcuts==2
assert q['fresh_candidate_ARM_calls']==all_rows and q['fresh_Qfplib_ARM_calls']==fresh_Q
assert all_rows+fresh_Q+audit['fresh_parent_ARM_calls']==558134
assert q['actual_directed_MPFR_input_conversions']==len(inputs)-nan_shortcuts==163673
assert q['oracle_evaluations']==len(inputs) and probe['fresh_ARM_calls']==10446
historical={x for x in losses if group_for[x]=='old48763:historical16'}
assert historical=={0x4085f424184f6dc5,0xc041265824e2113c}
historical_counts={f'{x:016X}':[{k:r[k] for k in ['SIO','candidate_instructions','Qfplib_instructions','parent_instructions']} for r in losses[x]] for x in sorted(historical)}
d=dict(status='PASS_INDEPENDENT_SEALED_EXP_TINY_EVIDENCE_ACCOUNTING_AND_LOSS_AUDIT',streamed_state_rows=all_rows,unique_inputs=len(inputs),author_fresh_candidate_ARM=327350,author_fresh_Qfplib_ARM=229824,author_fresh_parent_remaining_audit_ARM=960,author_total_qualified_fresh_ARM=558134,author_oracle_evaluations=163675,author_actual_directed_MPFR_input_conversions=163673,author_sNaN_shortcuts_without_MPFR=2,old97526_state_rows_parent_and_Qfplib_inherited_not_fresh=True,old48763_bits_identical_every_state=True,known_remaining_parent_costs_from_excluded_probe_state_rows=70,remaining_fresh_parent_audit_rows=960,final_smoke10446_excluded=True,rejected_inline_trial_not_a_parent_or_qualified_run=True,same_old48763_losses_before395_after154_fixed241=True,expanded163675_losses=669,expanded_loss_partition=dict(old154=True,new_dense_boundary514=True,new_ordinary_preexisting1='C08357D5691B8C00'),all_remaining669_preexisting_parent_losses=True,new_raw_speed_losses=0,correct_Qfplib_comparison=dict(comparison),wrong_Qfplib_states_retained=wrong_Q,tiny_correct_Qfplib_state_rows_all_faster=tiny_correct,all_tiny_costs_match_independent_model=dict(sorted(costs.items())),known_parent_cost_increases=13234,known_parent_cost_increase_histogram=dict(sorted(reg_delta.items())),all_known_increases_still_faster_Qfplib=True,valid_transition_neighbor_locations_in_fresh_ARM_and_MPFR_corpus=98303,three_excluded_cell_locations=dict(excluded),adjacent_binade_and_caller_endpoints_separately_acquired=True,all49153_midpoint_cells_independently_bound_to_acquisition=True,original_exp16_remaining2=historical_counts,old_candidate_observed_stack736=old['candidate_stack_bytes'],new_author_observed_stack376=q['candidate_stack_bytes'],observed_stack_not_universal_bound=True,author442299_model_controls_inherited_not_counted_own=True,own_fresh_ARM_or_MPFR_in_this_file=0,records_sha256=sha(records),original507_unchanged418=True)
(O/'evidence.json').write_text(json.dumps(d,indent=2)+'\n');print(json.dumps(d,indent=2))

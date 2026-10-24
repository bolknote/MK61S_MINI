"""Independent streamed reconciliation of sealed raw evidence, no ARM replay."""
from pathlib import Path
from collections import Counter
import gzip,hashlib,json,struct,sys
sys.dont_write_bytecode=True
from model import LOW,HIGH,exact_model,word_model
O=Path(__file__).resolve().parent;R=O.parents[1];P=R/'.build/m0-exp-tiny-log-midpoint-20261024';B=R/'.build/m0-exp-tiny-radius-20261024'
def read(p):return json.loads(Path(p).read_text())
def sha(p):return hashlib.sha256(Path(p).read_bytes()).hexdigest()
def equal(x,y):return bool(x&0x7fffffffffffffff>0x7ff0000000000000 and x&(1<<51)) if y&0x7fffffffffffffff>0x7ff0000000000000 else x==y
def key(r):return (int(r['x'],16),r['SIO'])
def stream_array(path):
 decoder=json.JSONDecoder();buf='';pos=0;ended=False
 with Path(path).open() as f:
  buf=f.read(65536);assert buf.lstrip().startswith('[');pos=buf.index('[')+1
  while True:
   while True:
    while pos<len(buf) and (buf[pos].isspace() or buf[pos]==','):pos+=1
    if pos<len(buf):break
    buf=buf[pos:]+f.read(65536);pos=0;assert buf
   if buf[pos]==']':assert not(buf[pos+1:]+f.read()).strip();return
   while True:
    try:row,end=decoder.raw_decode(buf,pos);break
    except json.JSONDecodeError:
     chunk=f.read(65536);assert chunk;buf=buf[pos:]+chunk;pos=0
   yield row;pos=end
q=read(P/'qualification.json');result=read(P/'result.json');oldmeta=read(B/'qualification.json');probe=read(P/'probe.json');audit=read(P/'remaining-parent-audit.json')
previous={}
with gzip.open(B/'qualification-records.jsonl.gz','rt') as f:
 for line in f:
  r=json.loads(line);previous[key(r)]=(int(r['candidate'],16),int(r['expected'],16),int(r['Qfplib'],16),r['candidate_instructions'],r['Qfplib_instructions'],r['Qfplib_correct'],r['group'])
assert len(previous)==327350
smoke={key(r):r for r in probe['rows']};audited={key(r):r for r in audit['rows']};reported={key(r):r for r in q['remaining']};regrows=iter(stream_array(P/'retained-parent-regressions.json'))
assert len(reported)==1342 and len(audited)==1028 and audit['fresh_parent_ARM_calls']==1028 and audit['fresh_MPFR_calls']==0
assert q['candidate_ELF_sha256']==probe['candidate_ELF_sha256']==audit['candidate_ELF_sha256']==sha(P/'candidate.elf')
input_states={};expected_bits={};group_for={};comparison=Counter();costs=Counter();reg_delta=Counter();old_deltas=Counter();losses={};old_losses=set();old_parent_losses=set();older_losses=set();fresh_Q=wrong_Q=tiny_correct=all_rows=old_count=reg_count=probe_reused=parent_audit_used=0
critical={int(r['x'],16):r for r in read(O/'own-vectors.json') if r['critical']};critical_seen=Counter()
assert len(critical)==308
records=P/'qualification-records.jsonl.gz';assert sha(records)==q['qualification_records_sha256']
with gzip.open(records,'rt',encoding='utf-8') as data:
 for line in data:
  row=json.loads(line);x,state=key(row);assert state in ('READY','DIRTY');k=(x,state)
  bit=1 if state=='READY' else 2;assert not(input_states.get(x,0)&bit);input_states[x]=input_states.get(x,0)|bit
  expected=int(row['expected'],16);got=int(row['candidate'],16);qgot=int(row['Qfplib'],16);assert equal(got,expected) and equal(qgot,expected)==row['Qfplib_correct']
  first=x not in expected_bits
  if first:expected_bits[x]=got;group_for[x]=row['group']
  else:assert expected_bits[x]==got
  before=previous.get(k);sample=smoke.get(k);cost=row['candidate_instructions'];qp=row['Qfplib_instructions'];parent=row['parent_instructions']
  if before:
   old_count+=1;assert row['Qfplib_acquisition']=='inherited tiny-radius corpus'
   bgot,bexpected,bqgot,bcost,bqp,bcorrect,bgroup=before
   assert got==bgot and equal(expected,bexpected) and qgot==bqgot and qp==bqp and row['Qfplib_correct']==bcorrect and parent==bcost
   old_deltas[cost-parent]+=1
   if bcorrect and parent>qp:old_parent_losses.add(x)
  else:
   fresh_Q+=1;assert row['Qfplib_acquisition']=='fresh'
   if sample:
    assert parent==sample['instructions'].get('parent') and cost==sample['instructions']['candidate'] and qp==sample['instructions']['Qfplib']
    assert got==int(sample['outputs']['candidate'],16) and ('parent' not in sample['outputs'] or got==int(sample['outputs']['parent'],16))
   else:assert parent is None
  mag=x&0x7fffffffffffffff
  if LOW<mag<HIGH:
   if first:assert got==exact_model(x)==word_model(x)
   assert cost<=206;costs[cost]+=1
   if row['Qfplib_correct']:assert cost<qp;tiny_correct+=1
  if x in critical:
   assert got==int(critical[x]['expected'],16);critical_seen[x]+=1
  if parent is not None and cost>parent:
   assert cost<qp and next(regrows)==row;reg_count+=1;reg_delta[cost-parent]+=1
  if row['Qfplib_correct']:
   comparison['faster' if cost<qp else 'equal' if cost==qp else 'slower']+=1
   if cost>qp:
    assert k in reported and reported[k]==row
    if before:
     old_losses.add(x)
     if before[6].startswith('old48763:'):older_losses.add(x)
    if parent is None:
     assert k in audited;parent=audited[k]['parent_instructions'];assert audited[k]==dict(row,parent_instructions=parent);parent_audit_used+=1
    elif not before:probe_reused+=1
    assert parent>qp;losses.setdefault(x,[]).append(row)
  else:wrong_Q+=1
  all_rows+=1
assert next(regrows,None) is None
assert len(input_states)==428231 and all(v==3 for v in input_states.values()) and all_rows==856462
inputs={x[0] for x in struct.iter_unpack('<Q',(P/'qualification-inputs.bin').read_bytes())};assert inputs==set(input_states)
assert old_count==327350 and fresh_Q==529112 and parent_audit_used==1028 and probe_reused==4
assert len(old_parent_losses)==669 and len(old_losses)==155 and old_losses<=old_parent_losses and len(old_parent_losses-old_losses)==514
assert len(older_losses)==154
assert len(losses)==671 and set(losses)=={k[0] for k in reported}
old_inputs={k[0] for k in previous};extra=set(losses)-old_inputs;assert len(extra)==516
dense={x for x in extra if group_for[x]=='dense_extended_domain_edges'};ordinary=extra-dense
assert len(dense)==514 and len(ordinary)==2 and all(group_for[x]=='probe:new_ordinary' for x in ordinary)
assert all(HIGH<=(x&0x7fffffffffffffff)<=HIGH+256 for x in dense)
assert comparison==Counter(faster=469786,slower=1342) and wrong_Q==385334
assert reg_count==239986 and all(delta>0 for delta in reg_delta)
assert costs==Counter({int(k):v for k,v in q['tiny_instruction_counts'].items()})
assert old_deltas==Counter({int(k):v for k,v in q['old_parent_cost_deltas'].items()})
assert len(critical_seen)==308 and set(critical_seen.values())=={2}
assert sum(r['critical']['quadratic_diff'] for r in critical.values())==154
assert read(P/'correction-cell-arm-binding.json')['existing_actual_ARM_state_rows']==sum(critical_seen.values())==616
nan_shortcuts=sum(x&0x7fffffffffffffff>0x7ff0000000000000 and not(x&(1<<51)) for x in inputs);assert nan_shortcuts==2
assert q['fresh_candidate_ARM_calls']==all_rows and q['fresh_Qfplib_ARM_calls']==fresh_Q
assert q['fresh_ARM_calls']==all_rows+fresh_Q==1385574
assert result['total_qualified_fresh_ARM_calls']==all_rows+fresh_Q+audit['fresh_parent_ARM_calls']==1386602
assert q['actual_directed_MPFR_input_conversions']==len(inputs)-nan_shortcuts==428229 and q['oracle_evaluations']==len(inputs)
assert probe['fresh_ARM_calls']==sum(len(r['instructions']) for r in probe['rows'])==24898
assert read(P/'trial-r1/probe.json')['fresh_ARM_calls']==24854 and read(P/'hard-refine-profile.json')['fresh_diagnostic_ARM_calls']==2
historical={x for x in losses if group_for[x]=='old163675:old48763:historical16'};assert historical=={0x4085f424184f6dc5,0xc041265824e2113c}
historical_counts={f'{x:016X}':[{k:r[k] for k in ['SIO','candidate_instructions','Qfplib_instructions','parent_instructions']} for r in losses[x]] for x in sorted(historical)}
for x in [LOW,LOW-1,LOW+1,HIGH-1,HIGH,HIGH+1]:
 for s in (0,1<<63):assert x|s in inputs
d=dict(status='PASS_INDEPENDENT_LOG_MIDPOINT_SEALED_EVIDENCE_AND_LOSS_ACCOUNTING',streamed_state_rows=all_rows,unique_inputs=len(inputs),author_fresh_candidate_ARM=856462,author_fresh_Qfplib_ARM=529112,author_fresh_parent_remaining_audit_ARM=1028,author_total_qualified_fresh_ARM=1386602,author_oracle_evaluations=428231,author_actual_directed_MPFR_input_conversions=428229,author_sNaN_shortcuts_without_MPFR=2,old327350_state_parent_and_Qfplib_measurements_inherited_not_fresh=True,all_old163675_raw_bits_identical_every_state=True,remaining_known_parent_state_rows314=dict(from_old_corpus310=True,from_excluded_final_probe4=True),remaining_fresh_parent_audit_rows1028=True,excluded_final_probe_ARM=24898,excluded_superseded_trial_ARM=24854,excluded_diagnostic_ARM=2,same_old163675_losses_before669_after155_fixed514=True,same_older48763_losses_remain154=True,expanded428231_losses=671,expanded_loss_partition=dict(old155=True,new_dense_boundary514=True,new_ordinary_preexisting2=[f'{x:016X}' for x in sorted(ordinary)]),all_remaining671_preexisting_parent_losses=True,new_raw_speed_losses=0,correct_Qfplib_comparison=dict(comparison),wrong_Qfplib_states_retained=wrong_Q,tiny_correct_Qfplib_state_rows_all_faster=tiny_correct,all_tiny_rows_match_independent_exact_word_model=True,tiny_observed_instruction_histogram=dict(sorted(costs.items())),known_parent_cost_increases=reg_count,known_parent_cost_increase_histogram=dict(sorted(reg_delta.items())),all_known_increases_still_faster_Qfplib=True,all154_cubic_changed_cells_bound308actual_inputs616states=True,quadratic_only_wrong_inputs154=True,original_exp16_remaining2=historical_counts,old_author_observed_stack376=oldmeta['candidate_stack_bytes'],new_author_observed_stack376=q['candidate_stack_bytes'],observed_stack_not_universal_bound=True,own_fresh_ARM_or_MPFR_in_this_file=0,records_sha256=sha(records),original507_unchanged418=True)
(O/'evidence.json').write_text(json.dumps(d,indent=2)+'\n');print(json.dumps(d,indent=2))

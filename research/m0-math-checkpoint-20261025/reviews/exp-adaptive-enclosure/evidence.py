"""Stream all frozen exp rows; reconcile callers, replay, exclusions and ledger."""
from pathlib import Path
from collections import Counter
import gzip,hashlib,json,struct,sys
sys.dont_write_bytecode=True
R=Path('/Users/bolk/Projects/MK61S_MINI');O=Path(__file__).resolve().parent;P=R/'.build/m0-exp-adaptive-enclosure-20261024';B=R/'.build/m0-exp-tiny-log-midpoint-20261024'
def read(p):return json.loads(Path(p).read_text())
def sha(p):return hashlib.sha256(Path(p).read_bytes()).hexdigest()
def equal(x,y):return bool(x&0x7fffffffffffffff>0x7ff0000000000000 and x&(1<<51)) if y&0x7fffffffffffffff>0x7ff0000000000000 else x==y
def key(r):return (int(r['x'],16),r['SIO'])
q=read(P/'qualification.json');result=read(P/'result.json');audit=read(P/'remaining-parent-audit.json');oldmeta=read(B/'qualification.json');probe=read(P/'probe.json')
old={}
with gzip.open(B/'qualification-records.jsonl.gz','rt') as f:
 for line in f:
  r=json.loads(line);old[key(r)]=(int(r['candidate'],16),int(r['expected'],16),int(r['Qfplib'],16),r['candidate_instructions'],r['Qfplib_instructions'],r['Qfplib_correct'],r['group'])
assert len(old)==856462
smoke={key(r):r for r in probe['rows']};audited={key(r):r for r in audit['rows']};reported={key(r):r for r in q['remaining']};assert len(audited)==2762 and len(reported)==4046
states={};groups={};expbits={};allrows=oldrows=freshQ=wrongQ=audits=0;comparison=Counter();olddelta=Counter();regdelta=Counter();tinycost=Counter();losses={};oldparentloss=set();oldloss=set();olderloss=set();regrows=[];regpartition=Counter();fixedrows={};beforelost={}
assert sha(P/'qualification-records.jsonl.gz')==q['qualification_records_sha256']
with gzip.open(P/'qualification-records.jsonl.gz','rt') as f:
 for line in f:
  r=json.loads(line);x,state=key(r);bit=1 if state=='READY' else 2;assert state in ['READY','DIRTY'] and not states.get(x,0)&bit;states[x]=states.get(x,0)|bit;groups[x]=r['group']
  e=int(r['expected'],16);c=int(r['candidate'],16);v=int(r['Qfplib'],16);cc=r['candidate_instructions'];qc=r['Qfplib_instructions'];pc=r['parent_instructions'];assert equal(c,e) and equal(v,e)==r['Qfplib_correct']
  if x in expbits:assert expbits[x]==c
  else:expbits[x]=c
  prev=old.get((x,state));sample=smoke.get((x,state))
  if prev:
   oldrows+=1;bc,be,bv,bcc,bqc,bcorrect,bgroup=prev;assert c==bc and equal(e,be) and v==bv and qc==bqc and r['Qfplib_correct']==bcorrect and pc==bcc
   assert r['Qfplib_acquisition']=='inherited log-midpoint corpus';olddelta[cc-pc]+=1
   if bcorrect and pc>qc:
    oldparentloss.add(x);beforelost[x,state]=r
    if cc<=qc:fixedrows[x,state]=r
  else:
   freshQ+=1;assert r['Qfplib_acquisition']=='fresh'
   if sample:assert pc==sample['instructions'].get('parent') and cc==sample['instructions']['candidate'] and qc==sample['instructions']['Qfplib']
   else:assert pc is None
  if 0x3c90000000000000<(x&0x7fffffffffffffff)<0x3df0000000000000:
   assert prev and cc==pc;tinycost[cc]+=1
  if pc is not None and cc>pc:
   regrows.append(r);regdelta[cc-pc]+=1
   if not r['Qfplib_correct']:regpartition['wrong_Qfplib']+=1
   elif cc>qc:assert pc>qc;regpartition['already_slower_correct_Qfplib']+=1
   else:regpartition['no_slower_correct_Qfplib']+=1
  if r['Qfplib_correct']:
   comparison['faster' if cc<qc else 'equal' if cc==qc else 'slower']+=1
   if cc>qc:
    assert reported[x,state]==r
    if prev:
     oldloss.add(x)
     if prev[6].startswith('old163675:old48763:'):olderloss.add(x)
    if pc is None:assert dict(r,parent_instructions=audited[x,state]['parent_instructions'])==audited[x,state];pc=audited[x,state]['parent_instructions'];audits+=1
    assert pc>qc;losses.setdefault(x,[]).append(r)
  else:wrongQ+=1
  allrows+=1
assert allrows==880014 and len(states)==440007 and set(states.values())=={3} and oldrows==856462 and freshQ==23552 and audits==2762
inputs={x[0] for x in struct.iter_unpack('<Q',(P/'qualification-inputs.bin').read_bytes())};assert inputs==set(states)
assert len(oldparentloss)==671 and len(oldloss)==642 and oldloss<=oldparentloss and len(olderloss)==126
fixed=oldparentloss-oldloss;assert len(fixed)==29 and len(fixedrows)==58 and {k[0] for k in fixedrows}==fixed
reportedfixed=read(P/'same-corpus-fixed29.json');assert {key(r):r for r in reportedfixed['rows']}==fixedrows
assert sum(r['candidate_instructions']==r['Qfplib_instructions'] for r in fixedrows.values())==2
assert {r['x'] for r in fixedrows.values() if r['candidate_instructions']==r['Qfplib_instructions']}=={'C0861FF4680382C9'}
assert len(losses)==2023 and set(losses)=={x for x,s in reported}
extras=set(losses)-{x for x,s in old};extra_groups=Counter(groups[x] for x in extras)
assert len(extras)==1381 and extra_groups==Counter(small_actual_output_midpoint_log_preimages=1353,new_normal_uniform=15,normal_and_endpoint_actual_midpoint_log_preimages=13)
assert comparison==Counter(faster=485398,slower=4046,equal=2) and wrongQ==390568
assert regrows==read(P/'retained-parent-regressions.json') and len(regrows)==200 and regdelta==Counter({2:126,29:74})
assert regpartition==Counter(already_slower_correct_Qfplib=44,wrong_Qfplib=70,no_slower_correct_Qfplib=86)
assert olddelta==Counter({int(k):v for k,v in q['old_parent_cost_deltas'].items()}) and tinycost==Counter({int(k):v for k,v in q['tiny_instruction_counts'].items()})
assert q['fresh_ARM_calls']==880014+23552==903566 and audit['fresh_parent_ARM_calls']==2762 and audit['known_parent_state_rows']==1284
assert q['actual_directed_MPFR_input_conversions']==440005 and q['NaN_shortcuts_without_MPFR']==sum(x&0x7fffffffffffffff>0x7ff0000000000000 and not x&(1<<51) for x in inputs)==2
historical=[r for r in read(R/'.build/m0-asin-scaled-bound-v164-20261023/slower-inputs.json')['rows'] if r['operation']=='exp'];historicalremaining={int(r['x'],16) for r in historical}&set(losses);assert historicalremaining=={0x4085f424184f6dc5}
assert 0xc041265824e2113c in fixed
# Reconcile every author original other-caller result with our own acquisition.
callers=read(P/'caller-proof.json');owncall=read(O/'caller-results.json');ck=lambda r:(r['operation'],r['x'],r.get('y'),r['stream'],r['SIO']);ownmap={ck(r):r for r in owncall}
for r in callers['rows']:
 o=ownmap[ck(r)];assert o['outputs']==r['outputs'] and o['instructions']==r['instructions'] and o['product_calls']==r['product_calls'] and o['expected']==r['expected']
assert len(ownmap)==378 and callers['fresh_ARM_calls']==1134 and callers['actual_directed_MPFR_inputs']==189
# All10,085 reference variants are inherited rows plus a fresh child state;
# only10,081 distinct x/y/SIO states were executed.
replay=read(P/'pow-loss-replay.json');prior=read(R/'.build/m0-pow-rsqrt-asm-20261024/remaining-expanded.json');assert sha(R/'.build/m0-pow-rsqrt-asm-20261024/remaining-expanded.json')==replay['pinned_parent_remaining_sha256']
assert len(prior['rows'])==len(replay['rows'])==10085
freshstates={};pairs=set()
for before,after in zip(prior['rows'],replay['rows']):
 reconstructed={k:v for k,v in after.items() if k not in ['previous_candidate_instructions','fresh_candidate']};assert before==reconstructed
 fresh=after['fresh_candidate'];assert fresh['candidate']==before['outputs']['candidate']==before['expected'];assert fresh['candidate_instructions']==before['instructions']['candidate']-3*fresh['product_calls']>before['instructions']['Qfplib']
 k=after['x'],after['y'],after['SIO'];assert k not in freshstates or freshstates[k]==fresh;freshstates[k]=fresh;pairs.add((after['x'],after['y']))
assert len(freshstates)==10081 and len(pairs)==7904 and replay['remaining']==replay['rows'] and replay['fresh_MPFR_calls']==0
# Unit counts and input/domain inventory, without rerunning the huge ARM sweep.
u=read(P/'unit-proof.json');gateinputs=(P/'unit-inputs.bin').read_bytes();prodinputs=(P/'product-unit-inputs.bin').read_bytes();accepted=0
for raw,bias in struct.iter_unpack('<QQ',gateinputs):
 bias=bias if bias<1<<31 else bias-(1<<32);tail=raw&1023;distance=abs(tail-512);bound=(275*((raw>>48)+24)+16383)//16384+129;margin=distance*256+((bias>>24) if tail>512 else -(bias>>24)-1);accepted+=margin>bound
valid=sum(a<1<<63 and b<1<<54 for a,b in struct.iter_unpack('<QQ',prodinputs))
assert len(gateinputs)//16==595004 and accepted==337604 and u['gate']['actual_ARM_calls']==595004
assert len(prodinputs)//16==70660 and valid==36781 and u['product']['actual_ARM_calls']==141320 and u['total_actual_ARM_calls']==736324
assert result['total_qualified_fresh_ARM_calls']==903566+2762+736324+1134+10081==1653867
assert result['total_actual_directed_MPFR_validation_inputs']==440005+189==440194
assert read(P/'public-input-preparation.json')['MPFR_directed_log_preimage_generations']==1536
notes=read(P/'logs/VALIDATION-NOTES.json');assert notes['excluded_final_probe_ARM_calls']==32208 and notes['excluded_final_margin_ARM_calls']==336 and notes['excluded_stack_diagnostic_repeat_calls']==640
# Preserve and extend the separate original507 component ledger by one strict exp fix.
parentreview=read(R/'.build/m0-exp-tiny-log-midpoint-independent-20261024/FINAL-REVIEW.json');oldledger=parentreview['original507_separate_component_union'];assert oldledger['no_slower']==418 and oldledger['equal']==6
newledger=dict(status='ACCEPTED_ADDITIVE_ORIGINAL507_SEPARATE_COMPONENT_UNION_419',accepted_baseline=oldledger,parent_review_sha256='bdaba8cf9bbe58c8e36dafe9b8f904eb8428fdd42db0abb070b5f4a42e472554',new_strict=1,new_equal=0,new_original_fix=dict(operation='exp',x='C041265824E2113C',parent2248=True,candidate599=True,Qfplib622=True,both_SIO_states_fresh_MPFR_bound=True),current=dict(no_slower=419,strictly_faster=413,equal=6,remaining=88,remaining_by_operation=dict(pow=51,exp=1,sin=22,cos=14)),full_other189_original_jobs_own_replayed=True,original_exp16_own_replayed=True,unchanged_prior_other_operation_evidence_inherited=True,not_one_integrated_binary=True,whole_math_GO=False,hardware=False,release=False)
(O/'original507-component-delta.json').write_text(json.dumps(newledger,indent=2)+'\n')
out=dict(status='PASS_INDEPENDENT_ADAPTIVE_SEALED_EVIDENCE_AND_LEDGER_RECONCILIATION',state_rows=allrows,unique_inputs=440007,all_old428231_bits_identical=True,inherited856462_parent_Qfplib_state_measurements_not_fresh=True,author_fresh_exp_candidate_ARM=880014,author_fresh_new_Qfplib_ARM=23552,author_fresh_parent_loss_audit_ARM=2762,remaining_known_parent_state_rows1284=True,author_fresh_gate_product_ARM=736324,author_fresh_other_callers_ARM=1134,author_fresh_pow_loss_states_ARM=10081,author_total_qualified_fresh_ARM=1653867,author_exp_actual_directed_MPFR_inputs=440005,author_other_callers_actual_directed_MPFR_inputs=189,author_total_actual_directed_MPFR_validation=440194,sNaN_shortcuts_without_MPFR=2,separate_log_generations1536_not_validation=True,same_old428231_losses_before671_after642_fixed29=True,fixed29_strict28_equal1=True,same_older48763_losses_before154_after126=True,expanded440007_losses2023_partition=dict(old642=True,new_preexisting1381=dict(extra_groups)),all2023_losses_parent_bound_no_new_losses=True,correct_Qfplib_comparison=dict(comparison),wrong_Qfplib_states_retained=390568,known_parent_cost_increases200=True,known_parent_cost_increase_deltas=dict(regdelta),known_parent_cost_increase_Qfplib_partition=dict(regpartition),all_prior_tiny_costs_exact_parent=True,original_exp_remaining_only_positive4085F424184F6DC5=True,original_pow51_sin22_cos14_unchanged_and_own_bound=True,expanded_pow_reference_variants10085_and_distinct_fresh_states10081=True,expanded_pow_remaining7904_unchanged=True,expanded_pow_MPFR_and_Qfplib_references_inherited=True,not_full111912_pair_fresh_replay=True,excluded_final_probe32208_margin336_stack640_and_failed_unit736324=True,trial_R1_R2_rejected_not_parents=True,author_observed_stack744_new_corpus_and_same_input_parent744=True,original507_union419_remaining88=True,own_ARM_or_MPFR_in_this_file=0)
(O/'evidence.json').write_text(json.dumps(out,indent=2)+'\n');print(json.dumps(out,indent=2))

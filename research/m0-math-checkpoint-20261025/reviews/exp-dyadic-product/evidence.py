"""Independent streamed frozen evidence accounting and original/expanded ledgers."""
from pathlib import Path
from collections import Counter
import copy,gzip,hashlib,json,struct,sys
sys.dont_write_bytecode=True
R=Path('/Users/bolk/Projects/MK61S_MINI');O=Path(__file__).resolve().parent;P=R/'.build/m0-exp-dyadic-product-20261024';B=R/'.build/m0-exp-adaptive-enclosure-20261024';E=R/'.build/m0-exp-adaptive-enclosure-independent-20261024'
def read(p):return json.loads(Path(p).read_text())
def sha(p):return hashlib.sha256(Path(p).read_bytes()).hexdigest()
def equal(x,y):return bool(x&0x7fffffffffffffff>0x7ff0000000000000 and x&(1<<51)) if y&0x7fffffffffffffff>0x7ff0000000000000 else x==y
def key(r):return (int(r['x'],16),r['SIO'])
q=read(P/'qualification.json');result=read(P/'result.json');audit=read(P/'remaining-parent-audit.json');probe=read(P/'probe.json');beforemeta=read(B/'qualification.json');old={}
with gzip.open(B/'qualification-records.jsonl.gz','rt') as f:
 for line in f:
  r=json.loads(line);old[key(r)]=(int(r['candidate'],16),int(r['expected'],16),int(r['Qfplib'],16),r['candidate_instructions'],r['Qfplib_instructions'],r['Qfplib_correct'],r['group'])
assert len(old)==880014
smoke={key(r):r for r in probe['rows']};audited={key(r):r for r in audit['rows']};reported={key(r):r for r in q['remaining']};assert len(audited)==130 and len(reported)==3082
states={};bitsmap={};groups={};rows=oldrows=freshQ=wrongQ=audits=0;comparison=Counter();olddelta=Counter();regdelta=Counter();tinycost=Counter();losses={};oldparentloss=set();oldloss=set();olderloss=set();fixedrows={};regrows=[];regpart=Counter()
assert sha(P/'qualification-records.jsonl.gz')==q['qualification_records_sha256']
with gzip.open(P/'qualification-records.jsonl.gz','rt') as f:
 for line in f:
  r=json.loads(line);x,state=key(r);b=1 if state=='READY' else 2;assert state in ['READY','DIRTY'] and not states.get(x,0)&b;states[x]=states.get(x,0)|b;groups[x]=r['group'];e=int(r['expected'],16);c=int(r['candidate'],16);v=int(r['Qfplib'],16);cc=r['candidate_instructions'];qc=r['Qfplib_instructions'];pc=r['parent_instructions'];assert equal(c,e) and equal(v,e)==r['Qfplib_correct']
  if x in bitsmap:assert bitsmap[x]==c
  else:bitsmap[x]=c
  prev=old.get((x,state));sample=smoke.get((x,state))
  if prev:
   oldrows+=1;bc,be,bv,bcc,bqc,bcorrect,bgroup=prev;assert c==bc and equal(e,be) and v==bv and qc==bqc and r['Qfplib_correct']==bcorrect and pc==bcc
   assert r['Qfplib_acquisition']=='inherited adaptive-exp corpus';olddelta[cc-pc]+=1
   if bcorrect and pc>qc:
    oldparentloss.add(x)
    if cc<=qc:fixedrows[x,state]=r
  else:
   freshQ+=1;assert r['Qfplib_acquisition']=='fresh'
   if sample:assert pc==sample['instructions'].get('parent') and cc==sample['instructions']['candidate'] and qc==sample['instructions']['Qfplib']
   else:assert pc is None
  if 0x3c90000000000000<(x&0x7fffffffffffffff)<0x3df0000000000000:assert prev and cc==pc;tinycost[cc]+=1
  if pc is not None and cc>pc:
   regrows.append(r);regdelta[cc-pc]+=1
   if not r['Qfplib_correct']:regpart['wrong_Qfplib']+=1
   elif cc>qc:assert pc>qc;regpart['already_losing_correct_Qfplib']+=1
   else:regpart['still_no_slower_correct_Qfplib']+=1
  if r['Qfplib_correct']:
   comparison['faster' if cc<qc else 'equal' if cc==qc else 'slower']+=1
   if cc>qc:
    assert reported[x,state]==r
    if prev:
     oldloss.add(x)
     if prev[6].startswith('old428231:old163675:old48763:'):olderloss.add(x)
    if pc is None:assert dict(r,parent_instructions=audited[x,state]['parent_instructions'])==audited[x,state];pc=audited[x,state]['parent_instructions'];audits+=1
    assert pc>qc;losses.setdefault(x,[]).append(r)
  else:wrongQ+=1
  rows+=1
assert rows==913500 and len(states)==456750 and set(states.values())=={3} and oldrows==880014 and freshQ==33486 and audits==130
inputs={x[0] for x in struct.iter_unpack('<Q',(P/'qualification-inputs.bin').read_bytes())};assert inputs==set(states)
assert len(oldparentloss)==2023 and len(oldloss)==1476 and oldloss<=oldparentloss and len(olderloss)==96
fixed=oldparentloss-oldloss;assert len(fixed)==547 and len(fixedrows)==1094 and {k[0] for k in fixedrows}==fixed
assert {key(r):r for r in read(P/'same-corpus-fixed547.json')['rows']}==fixedrows
assert sum(r['candidate_instructions']==r['Qfplib_instructions'] for r in fixedrows.values())==10
extras=set(losses)-{x for x,s in old};extragroups=Counter(groups[x] for x in extras)
assert len(losses)==1541 and len(extras)==65 and extragroups==Counter(dyadic_power_and_adjacent_output_midpoint_log_preimages=40,dyadic_cell_interior_controls=13,new_ordinary_uniform=12)
assert comparison==Counter(faster=517720,slower=3082,equal=10) and wrongQ==392688
assert regrows==read(P/'retained-parent-regressions.json') and len(regrows)==13222 and regdelta==Counter({2:13222})
assert regpart==Counter(already_losing_correct_Qfplib=200,wrong_Qfplib=11950,still_no_slower_correct_Qfplib=1072)
assert olddelta==Counter({int(k):v for k,v in q['old_parent_cost_deltas'].items()}) and tinycost==Counter({int(k):v for k,v in q['tiny_instruction_counts'].items()})
assert q['fresh_ARM_calls']==913500+33486==946986 and audit['fresh_parent_ARM_calls']==130 and audit['known_parent_state_rows']==2952
assert q['actual_directed_MPFR_input_conversions']==456748 and q['NaN_shortcuts_without_MPFR']==sum(x&0x7fffffffffffffff>0x7ff0000000000000 and not x&(1<<51) for x in inputs)==2
# All producer other-caller rows independently match our fresh public run.
authorcalls=read(P/'caller-proof.json');owncalls=read(O/'caller-results.json');ck=lambda r:(r['operation'],r['x'],r.get('y'),r['stream'],r['SIO']);ownmap={ck(r):r for r in owncalls}
for r in authorcalls['rows']:
 o=ownmap[ck(r)];assert o['outputs']==r['outputs'] and o['instructions']==r['instructions'] and o['product_calls']==r['product_calls'] and o['expected']==r['expected']
assert len(ownmap)==378 and authorcalls['fresh_ARM_calls']==1134 and authorcalls['actual_directed_MPFR_inputs']==189
# Preserve immutable old references while accounting for two generations of
# fresh-candidate fields. The producer copied/updated records in memory only.
replay=read(P/'pow-loss-replay.json');prior=read(B/'pow-loss-replay.json');assert sha(B/'pow-loss-replay.json')==replay['pinned_parent_remaining_sha256'];assert len(prior['rows'])==len(replay['rows'])==10085
freshstates={};oldpairs=set();remaining=[]
for before,after in zip(prior['rows'],replay['rows']):
 expected=copy.deepcopy(before);expected['instructions']['candidate']=before['fresh_candidate']['candidate_instructions'];expected['outputs']['candidate']=before['fresh_candidate']['candidate'];expected['previous_candidate_instructions']=before['fresh_candidate']['candidate_instructions'];expected['fresh_candidate']=after['fresh_candidate'];assert expected==after
 fresh=after['fresh_candidate'];assert fresh['candidate']==before['fresh_candidate']['candidate']==before['expected'];assert fresh['candidate_instructions']==before['fresh_candidate']['candidate_instructions']-2*fresh['product_calls']
 k=after['x'],after['y'],after['SIO'];assert k not in freshstates or freshstates[k]==fresh;freshstates[k]=fresh;oldpairs.add((after['x'],after['y']))
 if fresh['candidate_instructions']>after['instructions']['Qfplib']:remaining.append(after)
assert len(freshstates)==10081 and len(oldpairs)==7904 and remaining==replay['remaining'] and replay['fresh_MPFR_calls']==0
remainingpairs={(r['x'],r['y']) for r in remaining};fixedpow=oldpairs-remainingpairs;assert len(remainingpairs)==7901 and len(fixedpow)==3
ownnew=read(O/'new-original-pow-ties.json');assert fixedpow=={(r['x'],r['y']) for r in ownnew}=={tuple(v) for v in replay['fixed_pair_values']}
# Unit evidence inventory does not relabel broad producer sweeps as ours.
u=read(P/'unit-proof.json');dy=read(P/'dyadic-unit-proof.json');prodinputs=(P/'product-unit-inputs.bin').read_bytes();dinputs=(P/'dyadic-unit-inputs.bin').read_bytes();valid=sum(a<1<<63 and b<1<<54 for a,b in struct.iter_unpack('<QQ',prodinputs))
assert len(prodinputs)//16==70660 and valid==36781 and u['total_actual_ARM_calls']==141320
assert len(dinputs)//8==70094 and dy['actual_ARM_calls']==70094 and all(v<1<<54 and (((1<<62)*v+(1<<63))>>64)==(v+2)>>2 for v, in struct.iter_unpack('<Q',dinputs))
assert result['total_qualified_fresh_ARM_calls']==946986+130+141320+70094+1134+10081==1169745
assert result['total_actual_directed_MPFR_validation_inputs']==456748+189==456937 and read(P/'public-input-preparation.json')['MPFR_directed_log_preimage_generations']==8404
assert probe['fresh_ARM_calls']==40494 and read(P/'margin-probe.json')['fresh_ARM_calls']==336
# Late parent acceptance is additive, never rewriting the pending-at-seal fact.
parent=read(E/'FINAL-REVIEW.json');assert parent['status']=='GO_PRIVATE_RP_ADAPTIVE_EXP_ENCLOSURE_AND_SHARED_PRODUCT_COMPONENT_ONLY' and result['source_parent_independent_review_pending'] and read(P/'certificate.json')['inherited_parent_numeric_proof_independent_review_pending']
parentledger=parent['original507_separate_component_union'];assert parentledger['no_slower']==419 and parentledger['strictly_faster']==413 and parentledger['equal']==6
original=read(R/'.build/m0-asin-scaled-bound-v164-20261023/slower-inputs.json')['rows'];expkeys={r['x'] for r in original if r['operation']=='exp'};pub=[r for r in read(O/'public-results.json') if r['SIO']=='READY' and r['x'] in expkeys];assert len(pub)==16
for label in ['candidate','accepted_parent']:assert sum(r['Qfplib_correct'] and r['instructions'][label]<r['instructions']['Qfplib'] for r in pub)==15 and sum(r['instructions'][label]>r['instructions']['Qfplib'] for r in pub)==1
ready=[r for r in owncalls if r['SIO']=='READY'];assert len(ready)==189
assert sum(r['instructions']['parent']<r['instructions']['Qfplib'] for r in ready)==sum(r['instructions']['candidate']<r['instructions']['Qfplib'] for r in ready)==102
assert sum(r['instructions']['parent']==r['instructions']['Qfplib'] for r in ready)==0 and sum(r['instructions']['candidate']==r['instructions']['Qfplib'] for r in ready)==3
ledger=dict(status='ACCEPTED_ADDITIVE_ORIGINAL507_SEPARATE_COMPONENT_UNION_422',accepted_parent_ledger=parentledger['ledger'],new_strict=0,new_equal=3,new_pow_ties=ownnew,current=dict(no_slower=422,strictly_faster=413,equal=9,remaining=85,remaining_by_operation=dict(pow=48,exp=1,sin=22,cos=14)),all189_original_other_jobs_and16_exp_own_fresh=True,unaffected_other302_components_inherited_strict296_equal6=True,positive_hard_exp_regression2264to2266_retained=True,parent_pending_at_seal_preserved=True,parent_GO_added_in_separate_receipt=True,not_one_integrated_binary=True,whole_math_hardware_release_GO=False)
(O/'original507-component-delta.json').write_text(json.dumps(ledger,indent=2)+'\n')
out=dict(status='PASS_INDEPENDENT_DYADIC_SEALED_COUNTS_RESIDUALS_AND_LEDGER',unique_exp_inputs=456750,state_rows=913500,old440007_raw_bits_exact=True,old880014_parent_Qfplib_state_measurements_inherited_not_fresh=True,author_fresh_candidate_exp_ARM=913500,author_fresh_new_Qfplib_ARM=33486,author_fresh_parent_remaining_audit_ARM=130,author_fresh_product_ARM=141320,author_fresh_literal_dyadic_ARM=70094,author_fresh_other_callers_ARM=1134,author_fresh_pow_loss_states_ARM=10081,author_total_qualified_fresh_ARM=1169745,author_actual_MPFR_validation_exp456748_other189_total456937=True,sNaN_shortcuts2=True,separate8404_log_generations_not_validation=True,excluded_probe40494_margin336_initial_failed_product141320_not_qualified=True,same_old440007_exp_losses2023_to1476_fixed547=True,fixed547_strict542_equal5=True,same_older48763_exp126_to96=True,expanded456750_exp_losses1541_partition=dict(old1476=True,new_preexisting65=dict(extragroups)),all1541_losses_parent_bound_no_new_measured_losses=True,known_remaining_parent_states2952_fresh130=True,correct_Qfplib_comparison=dict(comparison),wrong_Qfplib_states392688_retained=True,known_parent_cost_increase_states13222_delta2=True,known_increase_Qfplib_partition=dict(regpart),positive_original_exp2264to2266_Q649_retained=True,negative_original_exp599to596_Q622=True,original_other189_author_rows_exact_own_acquisition=True,expanded_pow_variants10085_fresh_states10081=True,expanded_pow7904_to7901_fixed3_equal_original_pairs=True,pow_references_inherited_no_new_MPFR_or_full111912_pair_run=True,all_prior_tiny_costs_exact_parent=True,original507_accepted422_strict413_equal9_residual85=True,parent_pending_at_seal_preserved_lateGO_additive=True,own_ARM_MPFR_in_this_file=0)
(O/'evidence.json').write_text(json.dumps(out,indent=2)+'\n');print(json.dumps(out,indent=2))

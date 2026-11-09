"""Keep stable transport epochs separate and exclude interrupted job588 timing."""
import argparse,json,sys
from pathlib import Path
H=Path(__file__).resolve().parent
ROOT=H.parents[1];D=ROOT/'.build/m0-libc-batch-20261107-v1'
sys.path[:0]=[str(H),str(ROOT/'tests'),str(ROOT)]
import strata_data as b
from selection import choose,compare_matched
pin,save=b.pin,b.save

def closed_failed_process(p):
 assert p['EXIT']==1 and p['reaped'] and p['group_gone'] and p['parent_fds_before']==p['parent_fds_after']

def load_before():
 A=D/'amendment-v5';t=json.loads((A/'template-001/PLAN.json').read_text());apps=json.loads((A/'apps-001/BUILD.json').read_text());root=A/'run-001/campaign';campaign=json.loads((root/'CAMPAIGN.json').read_text())
 assert campaign['status']=='HOLD_FIRST_FAULT' and campaign['next_job']==576 and campaign['lease']['released'] and campaign['lease']['fd_closed'] and campaign['lease']['same_inode'];closed_failed_process(json.loads((A/'run-001/outer-process/PROCESS.json').read_text()))
 q=json.loads((root/'runs/000/QUALIFICATION.json').read_text());rows=[{} for _ in range(4)];jobs=[];refs=[pin(root/'CAMPAIGN.json')]
 def append(job,raw,inp,dec):
  parsed=b.wire.parse_report(raw.read_bytes(),inp.read_bytes(),t,apps['products'][3],dec.read_bytes());assert parsed['header'][24:30]==q['routes']['shared-flash']['context'];assert job==528+len(jobs) and parsed['request']['batch']==job%168;jobs.append(job)
  for row in parsed['rows']:assert row['index'] not in rows[3];rows[3][row['index']]=row
  refs.extend([pin(raw),pin(inp),pin(dec)])
 for step in campaign['phase_receipts']:
  assert pin(step['receipt']['path'])==step['receipt'] and pin(step['process']['path'])==step['process'];r=json.loads(Path(step['receipt']['path']).read_text());assert r['status']=='PASS';b.process(json.loads(Path(step['process']['path']).read_text()))
  if step['scope']!='timing':continue
  f=Path(step['receipt']['path']).parent
  for job in r['completed_jobs']:
   stem='job-%03d'%job;append(job,f/(stem+'.bin'),f/(stem+'-input.bin'),f/(stem+'.decoded'))
 audit_path=A/'TRANSPORT-HOLD-004-AUDIT-001.json';audit=json.loads(audit_path.read_text());assert audit['complete_exported_jobs']==list(range(576,588));assert audit['Root_independent_acceptance_pending'] # original stays pending; separate Root acceptance below
 acceptance=D/'amendment-v6/ROOT-ACCEPTED-RECOVERY588-001.json';accepted=json.loads(acceptance.read_text());assert accepted['job588_semantics_accepted_no_replay'] and accepted['job588_timing_excluded_from_controlled_selection'];refs.extend([pin(audit_path),pin(acceptance)])
 for j in audit['raws']:
  for k in ['raw','input','decoded']:assert pin(j[k]['path'])==j[k]
  append(j['job'],Path(j['raw']['path']),Path(j['input']['path']),Path(j['decoded']['path']))
 assert jobs==list(range(528,588));intervals=sum(7*sum(any(x) for x in row['raw']) for row in rows[3].values());assert intervals==793800
 return dict(template=t,rows=rows,jobs=60,intervals=intervals,contexts=q['routes'],raw_pins=refs)

def load_v6():
 A=D/'amendment-v6';audit_path=A/'PHYSICAL-INPUT-HOLD-004-AUDIT-001.json';audit=json.loads(audit_path.read_text());acceptance=D/'amendment-v10/ROOT-ACCEPTED-RECOVERY639-001.json';accepted=json.loads(acceptance.read_text());assert accepted['v6_CLOSED_independently_accepted'] and accepted['job639_semantics_accepted_no_replay'] and accepted['job639_timing_excluded']
 t=json.loads((A/'template-001/PLAN.json').read_text());apps=json.loads((A/'apps-001/BUILD.json').read_text());q=json.loads((A/'run-002/campaign/runs/000/QUALIFICATION.json').read_text());rows=[{} for _ in range(4)];refs=[pin(audit_path),pin(acceptance)];isolated=None;intervals=0
 assert audit['complete_exported_jobs']==list(range(589,640)) and audit['completed_controlled_jobs']==list(range(589,639))
 for record in audit['raws']:
  for k in ('raw','input','decoded'):assert pin(record[k]['path'])==record[k]
  parsed=b.wire.parse_report(Path(record['raw']['path']).read_bytes(),Path(record['input']['path']).read_bytes(),t,apps['products'][3],Path(record['decoded']['path']).read_bytes());assert parsed['header'][24:30]==q['routes']['shared-flash']['context'] and parsed['request']['batch']==record['job']%168
  if record['job']==639:isolated=dict(parsed=parsed,record=record);continue
  for row in parsed['rows']:assert row['index'] not in rows[3];rows[3][row['index']]=row;intervals+=7*sum(any(x) for x in row['raw'])
  refs.extend(record[k] for k in ('raw','input','decoded'))
 assert isolated is not None and len(rows[3])==50*210
 return dict(template=t,rows=rows,jobs=50,intervals=intervals,contexts=q['routes'],raw_pins=refs),isolated

def main(current,campaign,out):
 out.mkdir(parents=True,exist_ok=False);old=D/'amendment-v2';f0=b.load(old,old/'run-001/campaign/CAMPAIGN.json',166,528,'ROOT_COOPERATIVE_PAUSE_CLOSED');before=load_before();middle,interaction=load_v6();after=b.load(current,campaign,640,672,'PASS_REMAINING_32_AWAITING_INDEPENDENT_ROOT_CLOSED');t=f0['template']
 assert after['intervals']==400176 and after['jobs']==32
 for s in [before,middle,after]:assert t['cases']==s['template']['cases'] and t['leaves']==s['template']['leaves'] and t['logical_map']==s['template']['logical_map']
 recovery=json.loads((D/'diag588/READBACK-588-HOST-001.json').read_text());assert recovery['rows']==210 and recovery['raw_intervals']==13230
 for k in ['raw','input','decoded','APP','receipt','process','lease']:assert pin(recovery[k]['path'])==recovery[k]
 isolated=b.wire.parse_report(Path(recovery['raw']['path']).read_bytes(),Path(recovery['input']['path']).read_bytes(),before['template'],json.loads((D/'amendment-v3/apps-001/BUILD.json').read_text())['products'][3],Path(recovery['decoded']['path']).read_bytes());assert {r['index'] for r in isolated['rows']}==set(range(17640,17850))
 all_indexes=set(f0['rows'][3])|set(before['rows'][3])|{r['index'] for r in isolated['rows']}|set(middle['rows'][3])|{r['index'] for r in interaction['parsed']['rows']}|set(after['rows'][3]);assert all_indexes==set(range(t['case_count']))
 segments={'F0':f0,'AE2-before-disconnect':before,'AE2-after-reconnect':middle,'AE2-after-user-input':after};decisions={};maps=[]
 for name in b.FUNCTIONS:
  flash=b.scores(t,f0['rows'][1],name,7,'Flash');ram=b.scores(t,f0['rows'][2],name,7,'SRAM');sdk_rank=b.scores(t,f0['rows'][2],name,9,'SRAM');native=choose(flash);sdk=choose(sdk_rank);validations=[]
  for label,st in segments.items():
   observed={i:r for i,r in st['rows'][3].items() if r['function']==name}
   if not observed:continue
   matched={i:f0['rows'][1][i] for i in observed};ranking=b.scores(st['template'],observed,name,7,'Flash');reference=b.scores(t,matched,name,7,'Flash');profile=native['picked']['profile'];v=next(x for x in ranking if x['profile']==profile);r=next(x for x in reference if x['profile']==profile);comparison=compare_matched(r,v);noise=comparison['combined_uncertainty_ratio'];drift=comparison['ratio_drift']
   # A short-only slice can have an expected regression. Reject newly worse
   # effects, not already disclosed regressions in the complete primary map.
   valid=drift<=noise
   if not valid:native['verdict']='KEEP_CURRENT_UNRESOLVED_NEW_STRATUM_REGRESSION'
   validations.append(dict(stratum=label,physical_cases=len(observed),is_full_function=len(observed)==t['cases_by_function'][name],selected=v,matched_primary_reference=r,ratio_drift=drift,combined_uncertainty_ratio=noise,no_resolved_extra_regression=valid,all_candidate_ranking=ranking))
  x=native['picked'];y=next(v for v in ram if v['profile']==x['profile']);delta=x['checked_us']-y['checked_us'];bound=x['quantization_us']+y['quantization_us']+x['spread_us']+y['spread_us']
  if delta>bound:native['picked']=y
  native['placement_reason']='Matched F0 candidate SRAM improvement must exceed combined quantization/spread; otherwise keep Flash'
  decisions[name]=dict(native=native['picked'],native_verdict=native['verdict'],native_tie_policy=native,native_ranking=flash+ram,SDK=sdk['picked'],SDK_verdict=sdk['verdict'],SDK_tie_policy=sdk,SDK_ranking=sdk_rank,matched_subset_validation_by_stratum=validations,native_placement_comparison=dict(SRAM_improvement_us=delta,uncertainty_bound_us=bound))
  for label,st,route,baseline in [('F0-native-flash',f0,1,7),('F0-native-SRAM',f0,2,7),('F0-SDK',f0,2,9),('F0-shared-flash',f0,3,7),('AE2-before-disconnect',before,3,7),('AE2-after-reconnect',middle,3,7),('AE2-after-user-input',after,3,7)]:
   if not any(r['function']==name for r in st['rows'][route].values()):continue
   for target in range(6):
    p=out/(name+'-'+label+'-'+b.LABELS[target]+'-regressions.json');save(p,b.regressions(st['template'],st['rows'][route],name,target,baseline));maps.append(pin(p))
  print(name,native['verdict'],native['picked']['target'],native['picked']['placement'],round(native['picked']['gain_percent'],2),'SDK',sdk['verdict'],sdk['picked']['target'],round(sdk['picked']['gain_percent'],2),flush=True)
 prefix=json.loads((old/'PREFIX-001.json').read_text());total=prefix['raw_intervals']+f0['intervals']+before['intervals']+middle['intervals']+after['intervals']+recovery['raw_intervals']+interaction['record']['raw_intervals'];assert total==8897560
 result=dict(status='STRATIFIED_COMPLETE_MEASUREMENTS_AWAITING_INTEGRATION_AND_ROOT_CLOSED',physical_timing=True,hardware_jobs=672,rows=140448,raw_intervals=total,job588_semantics_pass_timing_excluded=True,job588=pin(D/'diag588/READBACK-588-HOST-001.json'),controlled_AE2_jobs=142,job639_semantics_pass_timing_excluded=True,job639=interaction['record'],decisions=decisions,primary_workload=t['workload'],historical_CDB_prefix=pin(old/'PREFIX-001.json'),strata={label:dict(jobs=s['jobs'],raw_intervals=s['intervals'],contexts=s['contexts'],raw_input_decoded_pins=s['raw_pins']) for label,s in segments.items()},regression_maps=maps,no_absolute_times_or_power_IRQ_cache_contexts_pooled=True,production_selection='Complete F0 native Flash/SRAM and independent SDK matrices. Each other controlled segment is validated only against its matching F0 input subset. Expected short-input regressions are retained; no resolved new segment regression is accepted.',unresolved_ties='Larger observed quantization/spread envelope, then weighted short inputs, then code size; not a statistical confidence interval',source=pin(__file__),base_source=pin(H/'strata_data.py'),selection_source=pin(H/'selection.py'))
 save(out/'RESULT.json',result)
if __name__=='__main__':
 p=argparse.ArgumentParser();p.add_argument('--evidence-root',type=Path,default=D);p.add_argument('--current',type=Path,required=True);p.add_argument('--campaign',type=Path,required=True);p.add_argument('--output',type=Path,required=True);a=p.parse_args();D=a.evidence_root.resolve();b.D=D;main(a.current,a.campaign,a.output)

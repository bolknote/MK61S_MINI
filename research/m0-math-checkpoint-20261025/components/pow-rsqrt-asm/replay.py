"""Fresh full public candidate+MPFR replay; pinned prior counts are inherited."""
import json,struct,sys
from collections import Counter
sys.dont_write_bytecode=True
from common import *
old_path=S/'qualification.json'
assert sha(old_path)=='30935cb919226d29571e6cb7d7441aab292f242def9aecc9b0b1a002aec348dc'
old=json.loads(old_path.read_text())
assert old['candidate_ELF_sha256']==build['parent_ELF_sha256']
m=machine('candidate');captured=hook_point(m);oracle=Oracle();expected_by_pair={};rows=[];deltas=Counter();points=0
for prior in old['rows']:
 if len(rows)%4096==0:print('progress',len(rows),'/',len(old['rows']),flush=True)
 x,y=int(prior['x'],16),int(prior['y'],16);key=(x,y)
 if key not in expected_by_pair:expected_by_pair[key]=oracle.reference('pow',x,y)
 expected=expected_by_pair[key]
 assert equal(int(prior['expected'],16),expected,64)
 state=states[prior['SIO']];m.uc.mem_write(0xd0000060,state);captured.clear()
 got,_,cost=m.call('_ZN12compact_math3powEdd',x,y,count=True)
 assert equal(got,expected,64),(hex(x),hex(y),prior['SIO'],hex(got),hex(expected))
 assert got==int(prior['outputs']['candidate'],16)
 normal=0<(x>>52)<2047 and y==bits(-.5)
 if normal:
  p=point(x);assert captured==[p['q']];points+=1
  assert bytes(m.uc.mem_read(0xd0000060,28))==state
 else:
  assert not captured
  assert cost==prior['instructions']['candidate'],(prior['x'],prior['y'],prior['SIO'],'unchanged dispatch count changed',cost,prior['instructions']['candidate'])
 after=bytes(m.uc.mem_read(0xd0000060,28))
 if prior['SIO']=='DIRTY':assert after==state
 else:assert not(struct.unpack('<7I',after)[6]&2)
 row=dict(prior);row['outputs']=dict(prior['outputs'],parent=prior['outputs']['candidate'],candidate=f'{got:016X}')
 row['instructions']=dict(prior['instructions'],parent=prior['instructions']['candidate'],candidate=cost)
 row['correct']=dict(prior['correct'],parent=prior['correct']['candidate'],candidate=True);rows.append(row)
 deltas[cost-prior['instructions']['candidate']]+=1
loss=lambda r,label:r['correct']['Qfplib'] and r['instructions'][label]>r['instructions']['Qfplib']
oldrows=[r for r in rows if r['group']=='historical153'];remaining=[r for r in rows if loss(r,'candidate')];new=[r for r in remaining if not loss(r,'parent')]
assert len(expected_by_pair)==old['unique_inputs'] and len(rows)==old['public_state_cases']
out={'status':'AUTHOR_FULL_PUBLIC_POW_RSQRT_CANDIDATE_REPLAY','candidate_ELF_sha256':sha(W/'candidate.elf'),'rsqrt_source_sha256':sha(W/'rsqrt.S'),'certificate_sha256':sha(W/'certificate.json'),'unique_inputs':len(expected_by_pair),'public_state_cases':len(rows),'fresh_public_ARM_calls':len(rows),'fresh_MPFR_calls':len(expected_by_pair),'MPFR_version':oracle.version,'inherited_parent_control_Qfplib_count_rows':len(rows),'inherited_baseline_calls_added':0,'parent_qualification_sha256':sha(old_path),'candidate_wrong':0,'all_candidate_returned_bits_identical_parent':True,'unchanged_dispatch_counts_identical_parent':True,'normal_points_checked_live':points,'correct_reference_no_domain_filter':True,'original153_parent_remaining':len({(r['x'],r['y']) for r in oldrows if loss(r,'parent')}),'original153_candidate_remaining':len({(r['x'],r['y']) for r in oldrows if loss(r,'candidate')}),'all_parent_raw_losses':len({(r['x'],r['y']) for r in rows if loss(r,'parent')}),'all_candidate_raw_losses':len({(r['x'],r['y']) for r in remaining}),'new_candidate_raw_losses':len({(r['x'],r['y']) for r in new}),'vs_parent':{'faster':sum(v for k,v in deltas.items() if k<0),'equal':deltas[0],'slower':sum(v for k,v in deltas.items() if k>0)},'parent_delta_counts':dict(sorted(deltas.items())),'observed_stack_bytes':SP-m.stack_lowest,'PCS_SP_SIO_boundedwrites_every_call':True,'all_cases_profiled':True,'corpus_pins':old['corpus_pins'],'hardware_accessed':False,'rows':rows,'remaining':remaining,'new':new}
(W/'qualification.json').write_text(json.dumps(out,indent=2)+'\n')
print(json.dumps({k:v for k,v in out.items() if k not in ('rows','remaining','new','corpus_pins')},indent=2))
for r in new[:20]:print('NEW',r['x'],r['y'],r['SIO'],r['instructions'])

"""Fresh focused four-machine public replay with live integer-point checks."""
import json,sys
from collections import Counter
sys.dont_write_bytecode=True
from common import *
machines={n:machine(n) for n in ('parent','control','candidate','Qfplib')}
captured=hook_point(machines['candidate']);jobs={}
def add(x,y,group,reference='qfp_composed_pow_exact'):
 jobs.setdefault((x,y),{'group':group,'reference':reference})
for r in json.loads((P/'slower-inputs.json').read_text())['rows']:
 if r['operation']!='pow':continue
 reference='qfp_composed_pow_exact' if r['stream']=='composed_exact_exponents' else 'qfp_composed_pow_integer' if r['stream'].startswith('composed_negative_') else 'qfp_composed_pow'
 add(int(r['x'],16),int(r['y'],16),'historical153',reference)
edges=[0,1,2,1<<51,(1<<52)-1,1<<52,bits(.5),bits(1.),bits(2.),0x7fefffffffffffff,0x7ff0000000000000,0x7ff0000000000001,0x7ff7ffffffffffff,0x7ff8000000000001,0x7fffffffffffffff]
for x in edges:
 for sign in (0,1<<63):
  for y in (0,1<<63,bits(1.),bits(-1.),bits(2.),bits(.5),bits(-.5)):
   add(x|sign,y,'IEEE_dispatch_controls','qfp_composed_pow_integer' if y in (0,1<<63) else 'qfp_composed_pow_exact')
rows=[];oracle=Oracle()
for index,((x,y),job) in enumerate(jobs.items()):
 if index%64==0:print('progress',index,'/',len(jobs),flush=True)
 expected=oracle.reference('pow',x,y)
 for state_name,state in states.items():
  outputs={};counts={};correct={}
  for label,m in machines.items():
   m.uc.mem_write(0xd0000060,state);captured.clear()
   got,_,cost=m.call(job['reference'] if label=='Qfplib' else '_ZN12compact_math3powEdd',x,y,count=True)
   if label=='candidate':
    normal=0<(x>>52)<2047 and y==bits(-.5)
    assert captured==([point(x)['q']] if normal else []),(hex(x),hex(y),captured,point(x) if normal else None)
    if normal:assert bytes(m.uc.mem_read(0xd0000060,28))==state
   outputs[label]=f'{got:016X}';counts[label]=cost;correct[label]=equal(got,expected,64)
   if label!='Qfplib':assert correct[label],(label,hex(x),hex(y),hex(got),hex(expected))
   if state_name=='DIRTY':assert bytes(m.uc.mem_read(0xd0000060,28))==state
  assert outputs['candidate']==outputs['control']==outputs['parent']
  assert counts['control']==counts['parent']
  rows.append({'x':f'{x:016X}','y':f'{y:016X}','SIO':state_name,'expected':f'{expected:016X}',**job,'outputs':outputs,'instructions':counts,'correct':correct})
loss=lambda r,label:r['correct']['Qfplib'] and r['instructions'][label]>r['instructions']['Qfplib']
old=[r for r in rows if r['group']=='historical153']
new=[r for r in rows if loss(r,'candidate') and not loss(r,'parent')]
remaining=[r for r in rows if loss(r,'candidate')]
out={'status':'PASS_FOCUSED_PUBLIC_PROBE','build_sha256':sha(W/'build.json'),'unique_inputs':len(jobs),'fresh_ARM_calls':4*len(rows),'fresh_MPFR_references':len(jobs),'MPFR_version':oracle.version,'wrong':0,'point_matches_old_integer_pipeline':True,'old153_parent_remaining':len({(r['x'],r['y']) for r in old if loss(r,'parent')}),'old153_candidate_remaining':len({(r['x'],r['y']) for r in old if loss(r,'candidate')}),'new_raw_losses':len({(r['x'],r['y']) for r in new}),'delta_counts':dict(Counter(r['instructions']['candidate']-r['instructions']['parent'] for r in rows)),'stacks':{n:SP-m.stack_lowest for n,m in machines.items() if n!='Qfplib'},'rows':rows,'remaining':remaining,'new':new,'hardware_accessed':False}
(W/'probe.json').write_text(json.dumps(out,indent=2)+'\n')
print(json.dumps({k:v for k,v in out.items() if k not in ('rows','remaining','new')},indent=2))
for r in old:
 if r['y']=='BFE0000000000000':print('RSQRT',r['x'],r['SIO'],r['instructions'],flush=True)

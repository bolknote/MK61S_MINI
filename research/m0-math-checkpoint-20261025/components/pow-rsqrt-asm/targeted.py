"""Fresh parent/candidate/Qfplib all-cell and rounding-tail reciprocal-root tests."""
import json,random,struct,sys
from collections import Counter
sys.dont_write_bytecode=True
from common import *
from unicorn import UC_HOOK_MEM_READ,UC_HOOK_MEM_WRITE
rng=random.Random(0x1252A7);jobs={};targets={0,1,496,497,511,512,513,514,515,527,528,1023};missing=[];search_count=0
def add(x,group):jobs.setdefault(x,group)
for p in (0,1):
 for index in range(256):
  head=((1023+p)<<52)|(index<<44)
  lows={0,1,2,(1<<43)-1,1<<43,(1<<43)+1,(1<<44)-2,(1<<44)-1,1<<42,3<<42,0xffff,0x10000,0xffffffff,0x100000000}
  lows.update(rng.getrandbits(44) for _ in range(64))
  for low in lows:add(head|low,'all512_cells_coordinate_corners_and_random')
  needed=set(targets)
  for attempt in range(16384):
   low=rng.getrandbits(44);x=head|low;v=point(x);tail=v['q']&1023;search_count+=1
   if tail in needed:
    add(x,'all512_cells_rounding_tail_targets');needed.remove(tail)
    if not needed:break
  if needed:missing.append({'parity':p,'index':index,'missing_tails':sorted(needed)})
for exponent in range(1,2047):
 for fraction in (0,(1<<52)-1,rng.getrandbits(52)):
  add((exponent<<52)|fraction,'all2046_exponents_scaling')
add(0x5B27CF4AC334ECB8,'old_hard_rounding_input')
assert not missing,missing
print('prepared',len(jobs),'public inputs; host-search points',search_count,flush=True)
machines={n:machine(n) for n in ('parent','candidate','Qfplib')};captured=hook_point(machines['candidate'])
accesses=[];machines['candidate'].uc.hook_add(UC_HOOK_MEM_READ|UC_HOOK_MEM_WRITE,lambda uc,access,address,size,value,user:accesses.append((access,address,size)),begin=0xd0000000,end=0xd0000fff)
oracle=Oracle();rows=[];tail_counts=Counter();deltas=Counter();y=bits(-.5);all_integer_bounds=True
for index,(x,group) in enumerate(jobs.items()):
 if index%4096==0:print('public progress',index,'/',len(jobs),flush=True)
 expected=oracle.reference('pow',x,y);v=point(x);q=v['q'];a=((x&((1<<52)-1))|(1<<52))<<(10+v['parity'])
 assert a*(q-16)**2<(1<<188)<a*(q+16)**2
 tail_counts[q&1023]+=1
 for state_name,state in states.items():
  outputs={};counts={};correct={}
  for label,m in machines.items():
   captured.clear();m.uc.mem_write(0xd0000060,state)
   got,_,cost=m.call('qfp_composed_pow_exact' if label=='Qfplib' else '_ZN12compact_math3powEdd',x,y,count=True)
   outputs[label]=f'{got:016X}';counts[label]=cost;correct[label]=equal(got,expected,64)
   if label!='Qfplib':assert correct[label],(label,hex(x),hex(got),hex(expected))
   if label=='candidate':assert captured==[q] and bytes(m.uc.mem_read(0xd0000060,28))==state
   elif state_name=='DIRTY':assert bytes(m.uc.mem_read(0xd0000060,28))==state
  assert outputs['parent']==outputs['candidate']
  deltas[counts['candidate']-counts['parent']]+=1
  rows.append({'x':f'{x:016X}','y':f'{y:016X}','group':group,'SIO':state_name,'expected':f'{expected:016X}','outputs':outputs,'instructions':counts,'correct':correct})
 assert not accesses
loss=lambda r,label:r['correct']['Qfplib'] and r['instructions'][label]>r['instructions']['Qfplib']
remaining=[r for r in rows if loss(r,'candidate')];new=[r for r in remaining if not loss(r,'parent')]
out={'status':'AUTHOR_TARGETED_RSQRT_ALL_CELLS_AND_ROUNDING_BOUNDARIES','build_sha256':sha(W/'build.json'),'candidate_ELF_sha256':sha(W/'candidate.elf'),'rsqrt_source_sha256':sha(W/'rsqrt.S'),'unique_inputs':len(jobs),'profiled_states':len(rows),'fresh_ARM_calls':3*len(rows),'fresh_MPFR_references':len(jobs),'MPFR_version':oracle.version,'wrong':0,'all_returned_bits_equal_parent':True,'all512_cells_have_every_target_tail':sorted(targets),'host_search_points_not_ARM_calls':search_count,'all2046_exponents':True,'live_integer_q_matches_old_pipeline':True,'exact_squared_true_q_inside_open_q_plusminus16':True,'all1024_tails_seen':len(tail_counts)==1024,'tail_histogram':dict(sorted(tail_counts.items())),'all_parent_raw_losses':len({r['x'] for r in rows if loss(r,'parent')}),'all_candidate_raw_losses':len({r['x'] for r in remaining}),'new_raw_losses':len({r['x'] for r in new}),'vs_parent':{'faster':sum(v for k,v in deltas.items() if k<0),'equal':deltas[0],'slower':sum(v for k,v in deltas.items() if k>0)},'delta_counts':dict(sorted(deltas.items())),'stacks':{n:SP-m.stack_lowest for n,m in machines.items() if n!='Qfplib'},'candidate_SIO_reads_or_writes':len(accesses),'PCS_SP_boundedwrites_each_call':True,'correct_reference_no_domain_filter':True,'hardware_accessed':False,'rows':rows,'remaining':remaining,'new':new}
(W/'targeted.json').write_text(json.dumps(out,indent=2)+'\n')
print(json.dumps({k:v for k,v in out.items() if k not in ('rows','remaining','new','tail_histogram','delta_counts')},indent=2))

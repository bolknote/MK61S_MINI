"""Fresh MPFR and all three Qfplib compositions on independent pow controls."""
from collections import Counter
import json,math,random,time,sys
sys.dont_write_bytecode=True
from harness import *

jobs={}
def add(x,y,group):jobs.setdefault((x,y),group)
for row in json.loads((W/'probe.json').read_text())['rows']:
    add(int(row['x'],16),int(row['y'],16),'repeat_pilot_excluded_from_pilot_counts')
special=[0,1<<63,1,(1<<63)|1,0x000fffffffffffff,0x0010000000000000,
         bits(0.5),bits(-0.5),bits(1.),bits(-1.),bits(2.),bits(-2.),
         0x7fefffffffffffff,0xffefffffffffffff,0x7ff0000000000000,0xfff0000000000000,
         0x7ff0000000000001,0xfff0000000000001,0x7ff8123456789abc,0xfff8123456789abc]
for x in special:
    for y in special:add(x,y,'IEEE_cartesian')
for x in [0.75,1.5,3.0,1.0+2.0**-52,1.0-2.0**-53]:
    denominator=512.0*math.log2(x)
    for exponent in [-1076,-1023,-1022,-1,0,1,1023,1024]:
        for index in [-1,0,1,255,511,512]:
            for offset in [-0.5,-2.0**-20,0.,2.0**-20,0.5]:
                add(bits(x),bits((512*exponent+index+offset)/denominator),'table_index_and_output_endpoint')
for index in range(512):
    for sign in [-1,1]:
        add(bits(1.5),bits(sign*(index+0.125)/(512*math.log2(1.5))),'all512_table_centers')
rng=random.Random(0x614257025)
for i in range(2048):
    exponent=rng.choice([1,2,12,512,1022,1023,1024,1536,2045,2046])
    x=(exponent<<52)|rng.getrandbits(52)
    if i%7==0:x|=1<<63
    y=bits((-1 if i&1 else 1)*2.0**-rng.choice([8,9,10,11,16,32,53]))
    if i%3==0:y=(y&0xfff0000000000000)|rng.getrandbits(52)
    add(x,y,'full_mantissa_all_exponent_bands')
for x in range(1,33):
    for y in [0.5,-0.5,2.,-2.,1./3.]:add(x,bits(y),'subnormal_bases')

machines={n:machine(n) for n in ('parent','control','candidate','Qfplib')}
calls=hook_products(machines['candidate'],'candidate')
roots,_=table();root_set=set(roots);seen=set()
oracle=Oracle();rows=[];start=time.monotonic();shortcuts=0
references=['qfp_composed_pow','qfp_composed_pow_exact','qfp_composed_pow_integer']
for i,((x,y),group) in enumerate(jobs.items()):
    if i%64==0:print('new-control',i,'/',len(jobs),'elapsed',round(time.monotonic()-start,1),flush=True)
    expected=oracle.reference('pow',x,y)
    shortcuts+=any((v&0x7fffffffffffffff)>0x7ff0000000000000 and not v&(1<<51) for v in [x,y])
    for state_name,state in states.items():
        outputs,counts,correct={},{},{}
        calls.clear()
        for label in ['parent','control','candidate',*references]:
            m=machines[label if label in machines else 'Qfplib'];m.uc.mem_write(0xd0000060,state)
            got,_,cost=m.call(label if label in references else '_ZN12compact_math3powEdd',x,y,count=True)
            outputs[label]=f'{got:016X}';counts[label]=cost;correct[label]=equal(got,expected,64)
            if label not in references:assert correct[label],(i,label,hex(x),hex(y),hex(got),hex(expected))
            state_after(m,state)
        assert outputs['parent']==outputs['control']==outputs['candidate']
        assert counts['parent']==counts['control'],(i,x,y,counts)
        tables=[c for c in calls if c['kind']=='table']
        for c in tables:
            assert int(c['a'],16) in root_set
            seen.add(int(c['a'],16))
        d=sum(int(c['a'],16)==1<<62 for c in tables);g=len(tables)-d
        assert counts['candidate']-counts['control']==2*g-67*d,(i,x,y,counts,calls)
        rows.append(dict(x=f'{x:016X}',y=f'{y:016X}',group=group,SIO=state_name,expected=f'{expected:016X}',
            outputs=outputs,instructions=counts,correct=correct,products=list(calls)))
loss=lambda r,label:any(r['correct'][q] and r['instructions'][label]>r['instructions'][q] for q in references)
remaining=[r for r in rows if loss(r,'candidate')]
new=[r for r in remaining if not loss(r,'parent')]
out=dict(status='FRESH_INDEPENDENT_POW_CONTROLS_ALL_REFERENCE_OUTPUTS_RETAINED',
    candidate_ELF_sha256=sha(W/'candidate.elf'),unique_pairs=len(jobs),public_state_rows=len(rows),
    fresh_public_ARM_calls=6*len(rows),fresh_candidate_calls=len(rows),fresh_parent_calls=len(rows),
    fresh_control_calls=len(rows),fresh_Qfplib_calls=3*len(rows),oracle_evaluations=len(jobs),
    actual_directed_MPFR_inputs=len(jobs)-shortcuts,sNaN_policy_shortcuts=shortcuts,MPFR_version=oracle.version,
    input_generation='binary64 host log2 only selects inputs; independent directed MPFR validates actual raw pairs',
    all512_roots_seen_in_public_calls=len(seen),no_nominal_reference_domain_filter=True,candidate_wrong=0,
    parent_layout_control_all_raw_bits_and_costs_identical=True,
    wrong_Qfplib_state_outputs_retained=sum(not r['correct'][q] for r in rows for q in references),
    parent_raw_loss_pairs=len({(r['x'],r['y']) for r in rows if loss(r,'parent')}),
    candidate_raw_loss_pairs=len({(r['x'],r['y']) for r in remaining}),new_raw_loss_pairs=len({(r['x'],r['y']) for r in new}),
    parent_cost_delta_histogram=dict(sorted(Counter(r['instructions']['candidate']-r['instructions']['parent'] for r in rows).items())),
    observed_stacks={n:SP-m.stack_lowest for n,m in machines.items() if n!='Qfplib'},
    elapsed_seconds=time.monotonic()-start,rows=rows,remaining=remaining,new=new,hardware_accessed=False)
(W/'new-qualification.json').write_text(json.dumps(out,indent=2)+'\n')
print(json.dumps({k:v for k,v in out.items() if k not in ('rows','remaining','new')},indent=2))

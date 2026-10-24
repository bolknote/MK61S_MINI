"""Bounded fresh ln MPFR/ARM boundary tests and sealed performance accounting."""
from pathlib import Path
from collections import Counter
from fractions import Fraction as F
import hashlib,json,struct,sys
sys.dont_write_bytecode=True
OUT=Path(__file__).resolve().parent;ROOT=OUT.parents[1]
W=ROOT/'.build/m0-ln-enclosure-20261024';P=ROOT/'.build/m0-log-ratio-dirty-20261024'
V=ROOT/'.build/m0-asin-scaled-bound-v164-20261023'
SUP=ROOT/'.build/m0-float-fma-qualification-20261023/support'
sys.path[:0]=[str(SUP),str(SUP.parent),str(ROOT/'tests')]
from native_eabi_m0_arm_self_test import Machine,SP
from check_stm32_vectors import ElfImage
from m0_mpfr_oracle import Oracle,bits
from oracles import equal
from unicorn import UC_HOOK_CODE
def sha(p):return hashlib.sha256(Path(p).read_bytes()).hexdigest()
def get(p):return json.loads(Path(p).read_text())
def put(n,o):
    with (OUT/n).open('x') as f:json.dump(o,f,indent=2);f.write('\n')
assert sha(OUT/'candidate.elf')=='36d1662268eaa35b5bd688fb7c2ff16958c1bc46dd92166dab5722e96b6f62f6'
ROM=ROOT/'research/rp2040-memset-2026-10-21/capture/bootrom.bin'
ELF=V/'firmware/mk61s-picocalc-pico-h.elf'
REF=ROOT/'.build/m0-v138-execution-20261023/reference/reference.elf'
machines={'Qfplib':Machine(REF,True)}
for label,path in (('parent',W/'control.elf'),('candidate',OUT/'candidate.elf')):
    m=Machine(ELF,True,bootrom=ROM);image=ElfImage(path);image.load(m.uc)
    m.elf.symbols[label+'_ln']=image.symbols['mk61_m0_ln'];m.trace=[]
    for name in ('ln_near_interval','ln_near_one','ln_refine','mk61_m0_cr_ln','mk61_m0_ln_special','mk61_m0_log_ratio70'):
        address=image.symbols[name]&~1
        def hit(uc,address,size,user,m=m):m.trace.append(user)
        m.uc.hook_add(UC_HOOK_CODE,hit,name,begin=address,end=address)
    machines[label]=m
states={'READY':struct.pack('<7I',0,0,0,0,0,0,1),'DIRTY':struct.pack('<7I',17,3,17,3,5,2,3)}
oracle=Oracle()
historical={int(r['x'],16) for r in get(V/'slower-inputs.json')['rows'] if r['operation']=='ln'}
jobs={r:'historical' for r in historical}
def add(raw,group):
    if 0<=raw<(1<<64):jobs.setdefault(raw,group)
for raw in (0,1<<63,1,(1<<52)-1,1<<52,(1<<52)+1,0x7fefffffffffffff,
    0x7ff0000000000000,0xfff0000000000000,0x7ff0000000000001,0xfff8000000001234,bits(-2.0),bits(0.5),bits(1.0),bits(2.0)):
    add(raw,'IEEE_and_normal_control')
for raw in (0x3fef800000000000,0x3fef808000000000,0x3ff0400000000000):
    for d in (-2,-1,0,1,2):add(raw+d,'dispatcher_boundary')
for n in (1,2,64,127,128):
    for sign in (-1,1):
        for numerator,denominator in ((n,8192),(2*n+1,16384)):
            center=bits(1+sign*numerator/denominator)
            for d in (-1,0,1):add(center+d,'near_center_or_half_cell')
# Generate input neighbors of exp(exact dyadics), exercising logarithm
# output binade edges rather than only input exponent boundaries.
for exponent in (-15,-14,-13,-7,0,9):
    for sign in (-1,1):
        target=bits(sign*2.0**exponent)
        center=oracle.reference('exp',target)
        for d in (-1,0,1):add(center+d,'log_output_dyadic_boundary')
for bit in (0,1,20,50,51):
    for d in (-1,0,1):add((1<<bit)+d,'subnormal_normalization_boundary')
for raw in (0x3fef7fffffffffe6,0x3fef7fffffffffe8,0x3fef7fffffffffea):add(raw,'retained_extra_DIRTY_loss')
auth=get(W/'qualification.json');saved={(r['x'],r['SIO']):r for r in auth['rows']}
rows=[];calls=0;matching=0
for raw,group in sorted(jobs.items()):
    expected=oracle.reference('ln',raw)
    for state_name,state in states.items():
        outputs={};costs={};correct={};trace={}
        for label,m in machines.items():
            m.uc.mem_write(0xd0000060,state)
            if label!='Qfplib':m.trace=[]
            symbol='qfp_dln' if label=='Qfplib' else label+'_ln'
            got,_,cost=m.call(symbol,raw,count=True);calls+=1
            outputs[label]=f'{got:016X}';costs[label]=cost;correct[label]=equal(got,expected,64)
            if label!='Qfplib':assert correct[label],(label,hex(raw),hex(got),hex(expected));trace[label]=list(m.trace)
            after=bytes(m.uc.mem_read(0xd0000060,28))
            if state_name=='DIRTY':assert after==state
            else:assert not struct.unpack('<7I',after)[6]&2
        assert outputs['candidate']==outputs['parent']
        assert costs['candidate']<=costs['parent']+1
        old=saved.get((f'{raw:016X}',state_name))
        if old:
            matching+=1
            for label in machines:
                assert outputs[label]==old['outputs'][label] and costs[label]==old['instructions'][label]
        rows.append(dict(x=f'{raw:016X}',group=group,SIO=state_name,expected=f'{expected:016X}',outputs=outputs,instructions=costs,correct=correct,trace=trace,author_record_matched=old is not None))
boundary=[r for r in rows if r['x']=='3FEF808000000000']
assert len(boundary)==2
for row in boundary:
    assert 'ln_near_interval' in row['trace']['parent'] and 'ln_refine' in row['trace']['parent']
    assert 'ln_near_interval' not in row['trace']['candidate'] and 'mk61_m0_log_ratio70' in row['trace']['candidate']
inside=[r for r in rows if r['x']=='3FEF808000000001']
assert len(inside)==2 and all('ln_near_interval' in r['trace']['candidate'] for r in inside)
put('SELECTED-PUBLIC-ARM.json',dict(status='PASS_FRESH_MPFR_RNE_DYADIC_N128_SUBNORMAL_ARM',
 unique_inputs=len(jobs),state_rows=len(rows),actual_ARM_calls=calls,MPFR_version=oracle.version,rows=rows,
 candidate_wrong=0,raw_parent_candidate_NaN_policy_equal=True,matched_author_state_records=matching,
 n128_actual_entry_trace_boundary=boundary,n127_next_float_actual_near_trace=inside,
 candidate_stack_bytes_observed=SP-machines['candidate'].stack_lowest,parent_stack_bytes_observed=SP-machines['parent'].stack_lowest,
 PCS_SP_return_bounded_writes_checked_every_call=True,DIRTY_all28_SIO_bytes_preserved=True,READY_no_DIRTY_left=True,
 author_full_corpus_not_repeated=True,hardware_accessed=False,
 resident_ELF_sha256=sha(ELF),Qfplib_ELF_sha256=sha(REF),ROM_sha256=sha(ROM)))

# Recompute author totals, retain all losses/regressions, and bind inherited
# parent records. This reads evidence; no39318-state replay is executed.
rr=auth['rows'];prior=get(P/'qualification.json')['rows'];prior_map={(r['x'],r['SIO']):r for r in prior}
assert len(rr)==39318 and len({r['x'] for r in rr})==19659
assert all(r['correct']['candidate'] and r['outputs']['candidate']==r['outputs']['parent'] for r in rr)
retained=0
for row in rr:
    old=prior_map.get((row['x'],row['SIO']))
    if old:
        retained+=1
        assert row['instructions']['parent']==old['instructions']['candidate']
        assert row['outputs']['parent']==old['outputs']['candidate']
assert retained==29814
groups=[]
for state in states:
    selected=[r for r in rr if r['SIO']==state]
    change=Counter('faster' if r['instructions']['candidate']<r['instructions']['parent'] else 'equal' if r['instructions']['candidate']==r['instructions']['parent'] else 'slower' for r in selected)
    parent_losses={r['x'] for r in selected if r['correct']['Qfplib'] and r['instructions']['parent']>r['instructions']['Qfplib']}
    child_losses={r['x'] for r in selected if r['correct']['Qfplib'] and r['instructions']['candidate']>r['instructions']['Qfplib']}
    assert child_losses<=parent_losses
    groups.append(dict(SIO=state,vs_parent=dict(change),parent_correct_Qfp_losses=len(parent_losses),child_correct_Qfp_losses=len(child_losses),fixed=len(parent_losses-child_losses),Qfplib_wrong=sum(not r['correct']['Qfplib'] for r in selected)))
remaining=[r for r in rr if r['correct']['Qfplib'] and r['instructions']['candidate']>r['instructions']['Qfplib']]
regressions=[r for r in rr if r['instructions']['candidate']>r['instructions']['parent']]
assert remaining==get(W/'remaining-slower.json')['rows'] and len(remaining)==65 and len({r['x'] for r in remaining})==34
assert regressions==get(W/'regressions.json')['rows'] and len(regressions)==18992
assert all(r['instructions']['candidate']-r['instructions']['parent']==1 for r in regressions)
oldloss={r['x'] for r in get(P/'remaining-slower.json')['rows']};newloss={r['x'] for r in remaining}
assert len(oldloss-newloss)==14
historical_left=historical&{int(r['x'],16) for r in remaining}
assert len(historical_left)==5
put('AUTHOR-ACCOUNTING.json',dict(status='PASS_HONEST_EXPANDED_AUTHOR_AND_RETAINED_PARENT_ACCOUNTING',
 public_unique_inputs=19659,state_rows=39318,parent_state_counts_retained=retained,groups=groups,
 remaining_raw_inputs=34,remaining_state_rows=65,new_correct_Qfp_deficits=0,
 prior27_raw_inputs_fixed=14,historical10_fixed=5,historical10_remaining=5,
 parent_regression_states=18992,every_regression_plus_one_instruction=True,
 faster_states=18664,equal_states=1662,author_parent_and_candidate_stack_bytes=568,
 inherited_bare_helper_ARM_calls=155608,inherited_helper_calls_not_recounted_fresh=True,
 no_physical_cycle_or_exhaustive_binary64_claim=True))
print(json.dumps(dict(status='PASS_BOUNDARY_ARM_AND_AUTHOR_ACCOUNTING',unique_inputs=len(jobs),ARM_calls=calls,MPFR=oracle.version,own_stack=SP-machines['candidate'].stack_lowest)))

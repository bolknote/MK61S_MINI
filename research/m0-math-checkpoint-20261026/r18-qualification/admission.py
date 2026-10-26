"""New router-family admission: all1024 cells, all10 admitted exponents.

Boundary and full-mantissa controls compare candidate, current R15, and
fresh Qfplib in READY/DIRTY. No nominal Qfplib domain filter.
"""
from pathlib import Path
from collections import Counter
import gzip,hashlib,importlib.util,json,random,struct,sys,time
sys.dont_write_bytecode=True
W=Path(__file__).resolve().parent;ROOT=W.parents[1]
S=ROOT/'.build/m0-math-unified-ln-small-partials-r18-20261025';P=ROOT/'.build/m0-math-unified-ln-ln2-r15-20261025'
sha=lambda p:hashlib.sha256(p.read_bytes()).hexdigest()
assert sha(S/'FROZEN.json')=='eb8d9ec8d61ad1eded286d52046d7b1d54053712d4fca4c88b288d7ddf7c5479'
assert sha(P/'FROZEN.json')=='2d48d6bac94d6635ca15acf686565ffc77840fa9e585403affea4e1b1b701058'
assert not(W/'admission-result.json').exists()
sys.path[:0]=[str(ROOT/'.build/m0-float-fma-qualification-20261023'),str(ROOT/'.build/m0-float-fma-qualification-20261023/support')]
from m0_mpfr_oracle import Oracle
from oracles import equal
from native_eabi_m0_arm_self_test import Machine,SP
def machine(name,directory):
    spec=importlib.util.spec_from_file_location(name,directory/'harness.py')
    module=importlib.util.module_from_spec(spec);spec.loader.exec_module(module)
    return module.machine()
machines={'candidate':machine('admission_R18',S),'parent':machine('admission_R15',P),
          'Qfplib':Machine(ROOT/'.build/m0-v138-execution-20261023/reference/reference.elf',True)}
own='_ZN12compact_math2lnEd';ref='qfp_dln';oracle=Oracle()
assert machines['candidate'].elf.symbols[own]==machines['candidate'].elf.symbols['mk61_m0_ln']
exponents=[e for e in range(1,2047)if not(e&(e+1))]
assert exponents==[1,3,7,15,31,63,127,255,511,1023]
rng=random.Random(0x1a14ad01);jobs=[]
for e in exponents:
    for cell in range(1024):
        offsets=[0,1,(1<<41)-1,1<<41,(1<<41)+1,(1<<42)-65,(1<<42)-64,(1<<42)-1,rng.randrange(1<<42)]
        assert len(set(offsets))==9
        for kind,offset in enumerate(offsets):jobs.append(dict(index=len(jobs),exponent=e,cell=cell,offset_kind=kind,x=f'{(e<<52)|(cell<<42)|offset:016X}'))
assert len(jobs)==92160
with gzip.GzipFile(filename=str(W/'admission-inputs.jsonl.gz'),mode='wb',mtime=0)as stream:
    for job in jobs:stream.write((json.dumps(job,separators=(',',':'))+'\n').encode())
states={'READY':struct.pack('<7I',0,0,0,0,0,0,1),'DIRTY':struct.pack('<7I',17,3,17,3,5,2,3)}
calls=Counter();classifications=Counter();comparisons=Counter();delta=Counter();wrongrefs=0;increases=0
remaining=[];new=[];old_loss_pairs=set();current_loss_pairs=set();fixed=set();started=time.monotonic()
with gzip.GzipFile(filename=str(W/'admission-records.jsonl.gz'),mode='wb',mtime=0)as stream:
    for job in jobs:
        if job['index']%4096==0:print('admission',job['index'],'/',len(jobs),'elapsed',round(time.monotonic()-started,1),'losses',len(current_loss_pairs),'new',len({r['x']for r in new}),flush=True)
        x=int(job['x'],16);gold=oracle.reference('ln',x);relations=[]
        for label,state in states.items():
            output={};costs={};correct={}
            for name,m in machines.items():
                m.uc.mem_write(0xd0000060,state)
                got,_,cost=m.call(ref if name=='Qfplib'else own,x,count=True);calls[name]+=1
                output[name]=f'{got:016X}';costs[name]=cost;correct[name]=equal(got,gold,64)
                if name!='Qfplib':assert correct[name],(name,job,label,hex(got),hex(gold))
                if label=='DIRTY':assert bytes(m.uc.mem_read(0xd0000060,28))==state
                else:assert not struct.unpack('<7I',m.uc.mem_read(0xd0000060,28))[6]&2
            d=costs['candidate']-costs['parent'];delta[d]+=1;increases+=d>0
            row=dict(**job,SIO=label,expected=f'{gold:016X}',outputs=output,instructions=costs,correct=correct)
            stream.write((json.dumps(row,separators=(',',':'))+'\n').encode())
            if correct['Qfplib']:
                relation='strict'if costs['candidate']<costs['Qfplib']else'equal'if costs['candidate']==costs['Qfplib']else'slower'
                relations.append(relation);comparisons[relation]+=1
                was=costs['parent']>costs['Qfplib'];now=relation=='slower'
                if was:old_loss_pairs.add(job['x'])
                if now:
                    current_loss_pairs.add(job['x']);remaining.append(row)
                    if not was:new.append(row)
                if was and not now:fixed.add(job['x'])
            else:wrongrefs+=1
        classifications['slower'if'slower'in relations else'equal'if'equal'in relations else'strict'if relations else'no_correct_reference']+=1
assert sum(calls.values())==552960
result=dict(status='PASS_NEW_ISOLATED_ROUTER_FAMILY_FRESH_ARM_QFPLIB_AND_MPFR',
    source_FROZEN_sha256=sha(S/'FROZEN.json'),candidate_ELF_sha256=sha(S/'candidate.elf'),parent_FROZEN_sha256=sha(P/'FROZEN.json'),
    input_cases=len(jobs),state_rows=2*len(jobs),completed_ARM_calls=dict(calls),actual_qualified_math_ARM_calls=sum(calls.values()),
    fresh_directed_MPFR_input_evaluations=len(jobs),exact_sNaN_shortcuts=0,MPFR_version=oracle.version,
    all10_new_admitted_exponents=exponents,all1024_log_cells=True,boundary_shapes=8,random_full_mantissa_per_exponent_cell=1,
    candidate_wrong=0,parent_wrong=0,correct_reference_comparisons=dict(comparisons),case_classification=dict(classifications),
    wrong_Qfplib_state_rows_retained=wrongrefs,all_wrong_reference_outputs_and_costs_in_raw_records=True,
    remaining_losing_inputs=len(current_loss_pairs),remaining_reference_state_rows=remaining,
    newly_losing_inputs_vs_R15=len({r['x']for r in new}),newly_losing_reference_state_rows=new,
    old_R15_losing_inputs=len(old_loss_pairs),fixed_R15_losing_input_candidates=len(fixed),
    parent_instruction_delta_histogram=dict(delta),parent_instruction_increase_state_rows=increases,
    all_parent_increase_rows_retained_in_complete_raw_records=True,
    source_loader_and_ROM_initializations_excluded=True,no_nominal_Qfplib_domain_filter=True,
    observed_stacks={n:SP-m.stack_lowest for n,m in machines.items()},
    input_sha256=sha(W/'admission-inputs.jsonl.gz'),records_sha256=sha(W/'admission-records.jsonl.gz'),
    overlapping_campaign_inputs_not_deduplicated_in_execution_totals=True,instructions_are_not_physical_cycles=True,
    hardware_accessed=False,integration_GO=False,goal_complete=False,elapsed_seconds=time.monotonic()-started)
(W/'admission-result.json').write_text(json.dumps(result,indent=2)+'\n')
print('admission PASS ARM',sum(calls.values()),'wrong0','losses',len(current_loss_pairs),'new',len({r['x']for r in new}),flush=True)

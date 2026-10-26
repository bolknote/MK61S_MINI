"""Fresh R29 full ARM; oracle/Qfplib baselines inherited explicitly from R28."""
from pathlib import Path
from collections import Counter
import gzip,hashlib,importlib.util,json,struct,sys,time
sys.dont_write_bytecode=True
W=Path(__file__).resolve().parent;ROOT=W.parents[1]
S=ROOT/'.build/m0-math-unified-exp-bit62-r29-20261026'
P=ROOT/'.build/m0-math-unified-exp-directed-distance-r28-qualification-20261026'
sha=lambda p:hashlib.sha256(p.read_bytes()).hexdigest()
assert sha(S/'FROZEN.json')=='c176067a6ba6afda1ff3f158be5c8e148c6bdc8f98dfc0f63dfa86f03f262018'
assert sha(P/'FROZEN.json')=='0ba57f4e189ef444dc849d8dc42836f2a56ab8780282c36854d320317b42a70b'
assert not(W/'exp-result.json').exists()and not(W/'exp-records.jsonl.gz').exists()
manifest=json.loads((P/'FROZEN.json').read_bytes());parent_result=json.loads((P/'exp-result.json').read_bytes())
assert sha(P/'exp-records.jsonl.gz')==manifest['files']['exp-records.jsonl.gz']['sha256']
spec=importlib.util.spec_from_file_location('r29_full_candidate_machine',S/'harness.py');h=importlib.util.module_from_spec(spec);spec.loader.exec_module(h)
from unicorn import UC_HOOK_CODE
from unicorn.arm_const import UC_ARM_REG_R6,UC_ARM_REG_R7
from native_eabi_m0_arm_self_test import SP
m=h.machine();assert not m.rom_models
proof=json.loads((S/'source-binding-proof.json').read_bytes())
rangeproof=json.loads((ROOT/'.build/m0-exp-bit62-normalization-study-20261026/result.json').read_bytes())
entry=proof['new_block'][0]['address'];visits=0;captured=[]
def point(uc,address,size,arg):
    global visits
    q=uc.reg_read(UC_ARM_REG_R6)|(uc.reg_read(UC_ARM_REG_R7)<<32)
    assert rangeproof['qmin']<=q<=rangeproof['qmax'],('q outside exact global range',q)
    visits+=1
hook=m.uc.hook_add(UC_HOOK_CODE,point,begin=entry,end=entry)
states={'READY':struct.pack('<7I',0,0,0,0,0,0,1),'DIRTY':struct.pack('<7I',17,3,17,3,5,2,3)}
calls=0;remaining=set();parent_losses=set();new=[];increases=[];wrong=0;deltas=Counter();byvisit=Counter();relations=Counter();current=None;start=time.monotonic()
try:
    with gzip.open(P/'exp-records.jsonl.gz','rt')as source,gzip.GzipFile(filename=str(W/'exp-records.jsonl.gz'),mode='wb',mtime=0)as out:
        for line in source:
            r=json.loads(line);current={k:r[k]for k in ['operation','index','x','group','SIO']}
            if calls%8192==0:print('R29 full candidate',calls,'/989922','elapsed',round(time.monotonic()-start,1),'loss',len(remaining),flush=True)
            state=states[r['SIO']];m.uc.mem_write(0xd0000060,state);before=visits
            got,_,cost=m.call('_ZN12compact_math3expEd',int(r['x'],16),count=True);calls+=1
            n=visits-before;assert n in [0,1]
            assert f'{got:016X}'==r['outputs']['candidate'],('R29 output differs',current,got,r['outputs']['candidate'])
            change=cost-r['instructions']['candidate'];assert change==-2*n,('code mapping cost differs',current,change,n)
            deltas[change]+=1;byvisit[n]+=1
            if r['SIO']=='DIRTY':assert bytes(m.uc.mem_read(0xd0000060,28))==state
            else:assert not struct.unpack('<7I',m.uc.mem_read(0xd0000060,28))[6]&2
            if r['correct']['Qfplib']:
                ref=r['instructions']['Qfplib'];relation='strict'if cost<ref else'equal'if cost==ref else'slower';relations[relation]+=1
                if r['instructions']['candidate']>ref:parent_losses.add(r['x'])
                if cost>ref:
                    remaining.add(r['x'])
                    if r['instructions']['candidate']<=ref:new.append(current)
            else:wrong+=1
            record=dict(**current,expected_inherited_directed_MPFR=r['expected'],candidate_output=f'{got:016X}',candidate_instructions=cost,normalization_visits=n,
              inherited_R28_output=r['outputs']['candidate'],inherited_R28_instructions=r['instructions']['candidate'],
              inherited_Qfplib_output=r['outputs']['Qfplib'],inherited_Qfplib_instructions=r['instructions']['Qfplib'],inherited_Qfplib_correct=r['correct']['Qfplib'])
            out.write((json.dumps(record,separators=(',',':'))+'\n').encode())
except Exception as error:
    (W/'FAILURE.json').write_text(json.dumps(dict(status='FAILED_R29_CANDIDATE_FULL_REPLAY',error=repr(error),current=current,completed_fresh_R29_ARM_calls=calls,normalization_visits=visits),indent=2)+'\n');raise
finally:m.uc.hook_del(hook)
assert calls==989922 and len(parent_losses)==428 and not new and not increases
result=dict(status='PASS_FRESH_R29_FULL_ARM_WITH_EXPLICIT_INHERITED_R28_ORACLES_AND_REFERENCES',source_FROZEN_sha256=sha(S/'FROZEN.json'),parent_qualification_FROZEN_sha256=sha(P/'FROZEN.json'),
 candidate_ELF_sha256=sha(S/'candidate.elf'),parent_records_sha256=sha(P/'exp-records.jsonl.gz'),records_sha256=sha(W/'exp-records.jsonl.gz'),
 unique_inputs=494961,state_rows=calls,actual_fresh_public_R29_ARM_calls=calls,actual_fresh_parent_ARM_calls=0,actual_fresh_Qfplib_ARM_calls=0,actual_fresh_MPFR_inputs=0,
 inherited_R28_candidate_state_measurements=calls,inherited_Qfplib_state_measurements=calls,inherited_oracle_input_rows=494961,
 inherited_actual_directed_MPFR_inputs=parent_result['actual_directed_MPFR_inputs'],inherited_exact_sNaN_shortcuts=parent_result['exact_sNaN_policy_shortcuts'],
 all_outputs_exact_saved_correctly_rounded_R28=True,candidate_wrong=0,parent_losing_inputs=428,candidate_losing_inputs=len(remaining),fixed_inputs=len(parent_losses-remaining),
 new_losing_inputs=len(remaining-parent_losses),remaining_losing_arguments=sorted(remaining),new_correct_Qfplib_loss_rows=new,all_parent_increases=increases,
 instruction_delta_histogram=dict(deltas),normalization_visit_histogram=dict(byvisit),all_actual_main_q_within_proved_global_interval=True,
 all_actual_costs_exact_proved_0_or_minus2_mapping=True,correct_inherited_Qfplib_relations=dict(relations),wrong_inherited_Qfplib_rows_retained=wrong,
 observed_stack=SP-m.stack_lowest,primitive_and_diagnostic_and_inherited_R28_full_calls_not_pooled=True,physical_cycles_measured=False,
 hardware_accessed=False,integration_GO=False,goal_complete=False,elapsed_seconds=time.monotonic()-start)
(W/'exp-result.json').write_text(json.dumps(result,indent=2)+'\n')
print(json.dumps({k:v for k,v in result.items()if k!='remaining_losing_arguments'},indent=2),flush=True)

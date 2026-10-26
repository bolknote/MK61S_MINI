"""Fresh full R45 exp corpus, pinned R38 gold/references as inherited by R43."""
from pathlib import Path
from collections import Counter
import gzip,hashlib,importlib.util,json,struct,sys,time
sys.dont_write_bytecode=True
W=Path(__file__).resolve().parent;ROOT=W.parents[1]
S=ROOT/'.build/m0-math-unified-ddiv-cold-overflow-r45-20261026'
P=ROOT/'.build/m0-math-unified-exp-row0-midpoint-r38-qualification-20261026'
sha=lambda p:hashlib.sha256(p.read_bytes()).hexdigest()
assert sha(S/'FROZEN.json')=='dbc455078837507acaeb750df1e3fb6800b923e2a9a880c9c6bcc2150ba3527a'
assert sha(P/'FROZEN.json')=='aff1d6e8bdedba0bb05cf65d5f3a6f3964da1def390bfed69d28078577797f7a'
assert not(W/'exp-result.json').exists()
manifest=json.loads((P/'FROZEN.json').read_bytes());phases=['full','boundary','power','edge','admission','fresh-edge']
for phase in phases:
    f=P/(phase+'-records.jsonl.gz');r=manifest['files'][f.name];assert f.stat().st_size==r['bytes']and sha(f)==r['sha256']
sys.path[:0]=[str(ROOT/'.build/m0-float-fma-qualification-20261023/support'),str(ROOT/'.build/m0-float-fma-qualification-20261023')]
from native_eabi_m0_arm_self_test import SP
from oracles import equal
from unicorn import UC_HOOK_CODE
spec=importlib.util.spec_from_file_location('r45_full_exp',S/'harness.py');h=importlib.util.module_from_spec(spec);spec.loader.exec_module(h);m=h.machine();assert not m.rom_models
states={'READY':struct.pack('<7I',0,0,0,0,0,0,1),'DIRTY':struct.pack('<7I',17,3,17,3,5,2,3),'PENDING':struct.pack('<7I',0x80000001,7,0x80000001,7,0x11223344,0x55667788,2)};stateid={s:i for i,s in enumerate(states)}
visits=Counter();hooks=[]
for sym in ['__aeabi_ddiv','mk61_m0_ddiv_slow','_ZN7m0_eabi6BinaryILj52ELj11EE3divEyy','mk61_m0_ddiv_denominator_guard_begin']:
    a=m.elf.symbols[sym]&~1;hooks.append(m.uc.hook_add(UC_HOOK_CODE,lambda uc,a,s,n:visits.update([n]),user_data=sym,begin=a,end=a))
seen={};inputs=set();parentloss=set();childloss=set();hist=Counter();inc=[];new=[];wrong=0;calls=0;duplicates=0;source_rows=Counter();fresh_rows=Counter();start=time.monotonic();current={}
try:
    with gzip.GzipFile(filename=str(W/'exp-records.jsonl.gz'),mode='wb',mtime=0)as out:
        for phase in phases:
            with gzip.open(P/(phase+'-records.jsonl.gz'),'rt')as f:
                for line in f:
                    r=json.loads(line);hx=r['x'];x=int(hx,16);state=r['SIO'];source_rows[phase]+=1
                    if 'candidate_output'in r:
                        gold=r['expected_inherited_directed_MPFR'];parent=r['candidate_output'];pc=r['candidate_instructions'];qout=r['inherited_Qfplib_output'];qc=r['inherited_Qfplib_instructions'];qcorrect=r['inherited_Qfplib_correct']
                    else:gold=r['expected'];parent=r['outputs']['candidate'];pc=r['instructions']['candidate'];qout=r['outputs']['Qfplib'];qc=r['instructions']['Qfplib'];qcorrect=r['correct']['Qfplib']
                    assert equal(int(parent,16),int(gold,16),64)and equal(int(qout,16),int(gold,16),64)==qcorrect
                    key=(x<<2)|stateid[state];signature=struct.pack('<QQIQIB',int(gold,16),int(parent,16),pc,int(qout,16),qc,qcorrect)
                    if key in seen:assert seen[key]==signature;duplicates+=1;continue
                    seen[key]=signature;inputs.add(x)
                    if calls%16384==0:print('R45 full exp',calls,'phase',phase,'elapsed',round(time.monotonic()-start,1),'loss',len(childloss),'division visits',sum(visits.values()),flush=True)
                    current=dict(phase=phase,x=hx,SIO=state,index=calls);sb=states[state];m.uc.mem_write(0xd0000060,sb);got,_,cost=m.call('_ZN12compact_math3expEd',x,count=True);calls+=1;fresh_rows[phase]+=1
                    assert f'{got:016X}'==parent,current
                    if state=='READY':assert not struct.unpack('<7I',m.uc.mem_read(0xd0000060,28))[6]&2
                    else:assert bytes(m.uc.mem_read(0xd0000060,28))==sb
                    delta=cost-pc;hist[delta]+=1
                    record=dict(operation='exp',x=hx,SIO=state,source_phase=phase,expected=gold,outputs=dict(candidate=f'{got:016X}',inherited_R38=parent,Qfplib=qout),instructions=dict(candidate=cost,inherited_R38=pc,Qfplib=qc),correct=dict(candidate=True,inherited_R38=True,Qfplib=qcorrect),parent_instruction_delta=delta)
                    if delta>0:inc.append(record)
                    if not qcorrect:wrong+=1
                    else:
                        if pc>qc:parentloss.add(x)
                        if cost>qc:
                            childloss.add(x)
                            if pc<=qc:new.append(record)
                    out.write((json.dumps(record,separators=(',',':'))+'\n').encode())
except Exception as error:
    (W/'exp-FAILURE.json').write_text(json.dumps(dict(error=repr(error),current=current,completed_fresh_R45_ARM_calls=calls),indent=2)+'\n');raise
finally:
    for hook in hooks:m.uc.hook_del(hook)
assert len(inputs)==568856 and len(parentloss)==512
result=dict(status='PASS_R45_FULL_EXP_FRESH_CANDIDATE_CACHED_R38_GOLD_QFP',source_FROZEN_sha256=sha(S/'FROZEN.json'),inherited_R38_qualification_FROZEN_sha256=sha(P/'FROZEN.json'),source_rows_by_phase=dict(source_rows),fresh_R45_rows_by_phase=dict(fresh_rows),duplicate_state_rows_checked=duplicates,unique_inputs=len(inputs),state_rows=calls,actual_qualified_public_ARM_calls=calls,actual_fresh_parent_Qfp_MPFR_calls=0,parent_R38_gold_Qfp_cached_as_inherited_R43_not_fresh=True,candidate_wrong=0,parent_losing_inputs=len(parentloss),candidate_losing_inputs=len(childloss),remaining_losing_arguments=[f'{v:016X}'for v in sorted(childloss)],new_correct_reference_loss_rows=new,all_parent_instruction_increase_rows=inc,parent_instruction_delta_histogram=dict(hist),all4_shared_division_entry_visits=dict(visits),wrong_reference_state_rows_retained=wrong,all_correct_reference_results_compared_no_nominalfilter=True,records_sha256=sha(W/'exp-records.jsonl.gz'),observed_stack=SP-m.stack_lowest,not_universal_stack_bound=True,physical_cycles_measured=False,hardware_accessed=False,integration_GO=False,goal_complete=False,elapsed_seconds=time.monotonic()-start)
(W/'exp-result.json').write_text(json.dumps(result,indent=2)+'\n');print(json.dumps({k:v for k,v in result.items()if not isinstance(v,list)},indent=2),flush=True)

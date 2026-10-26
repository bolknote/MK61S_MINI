"""Full current single-ELF candidate and fresh Qfplib plus directed MPFR."""
from pathlib import Path
from collections import Counter
import gzip,hashlib,importlib.util,json,struct,sys,time
sys.dont_write_bytecode=True
W=Path(__file__).resolve().parent;ROOT=W.parents[1]
assert len(sys.argv)==2 and sys.argv[1]in ['ln','exp'];op=sys.argv[1]
S=ROOT/'.build/m0-math-unified-ln-small-partials-r18-20261025';REF=ROOT/'.build/m0-v138-execution-20261023/reference/reference.elf'
sha=lambda p:hashlib.sha256(p.read_bytes()).hexdigest()
assert not(W/(op+'-result.json')).exists()and not(W/(op+'-records.jsonl.gz')).exists()
meta=json.loads((W/'corpus.json').read_bytes());inputfile=W/(op+'-inputs.jsonl.gz');assert sha(inputfile)==meta['prepared_files'][inputfile.name]['sha256']
source_frozen_pin=sha(S/'FROZEN.json');assert source_frozen_pin=='eb8d9ec8d61ad1eded286d52046d7b1d54053712d4fca4c88b288d7ddf7c5479'
source_pin=sha(S/'link-result.json');source_code_pin=sha(S/'source/code/native_eabi_m0_log70.inc')
assert (S/'loader-layout-proof.json').exists() and (S/'private-return-proof.json').exists()
assert sha(REF)=='b66da3a6805ecd110580e6dd281e17c37bc4399bee0ba1fae86f8c8cf78bfc26'
sys.path[:0]=[str(ROOT/'.build/m0-float-fma-qualification-20261023'),str(ROOT/'.build/m0-float-fma-qualification-20261023/support')]
from m0_mpfr_oracle import Oracle
from oracles import equal
from native_eabi_m0_arm_self_test import Machine,SP
spec=importlib.util.spec_from_file_location('expanded_current_r9_'+op,S/'harness.py');u=importlib.util.module_from_spec(spec);spec.loader.exec_module(u)
machines={'candidate':u.machine(),'Qfplib':Machine(REF,True)};assert all(not m.rom_models for m in machines.values())
own=f'_ZN12compact_math{len(op)}{op}Ed';native='mk61_m0_'+op;ref='qfp_d'+op
assert machines['candidate'].elf.symbols[own]==machines['candidate'].elf.symbols[native]
states={'READY':struct.pack('<7I',0,0,0,0,0,0,1),'DIRTY':struct.pack('<7I',17,3,17,3,5,2,3)}
oracle=Oracle();attempted=Counter();completed=Counter();comparisons=Counter();delta=Counter();wrongref=0;snan=0;oraclecalls=0
remaining=[];new_losses=[];increases=[];reference_changes=[];old_gold_changes=[];old_candidate_changes=[];groups={};relation_cases=Counter();started=time.monotonic();current=None;state_rows=0
try:
    with gzip.open(inputfile,'rt')as source,gzip.GzipFile(filename=str(W/(op+'-records.jsonl.gz')),mode='wb',mtime=0)as stream:
        for line in source:
            job=json.loads(line);i=job['index'];x=int(job['x'],16);current=dict(operation=op,index=i,x=job['x'],group=job['group'])
            if i%4096==0:print(op,i,'/',meta['counts'][op],'elapsed',round(time.monotonic()-started,1),'losses',len({r['index']for r in remaining}),flush=True)
            expected=oracle.reference(op,x);oraclecalls+=1;mag=x&0x7fffffffffffffff;snan+=mag>0x7ff0000000000000 and not(x&(1<<51))
            if not equal(expected,int(job['old_expected'],16),64):old_gold_changes.append(dict(**current,old=job['old_expected'],fresh=f'{expected:016X}'))
            relations=[];group=groups.setdefault(job['group'],dict(inputs=0,state_rows=0,relations=Counter()));group['inputs']+=1
            for state_name,state in states.items():
                out={};costs={};correct={};old=job['old_states'][state_name]
                for label,m in machines.items():
                    m.uc.mem_write(0xd0000060,state);attempted[label]+=1
                    got,_,cost=m.call(own if label=='candidate'else ref,x,count=True);completed[label]+=1
                    out[label]=f'{got:016X}';costs[label]=cost;correct[label]=equal(got,expected,64)
                    if state_name=='DIRTY':assert bytes(m.uc.mem_read(0xd0000060,28))==state,(label,'DIRTY context',current)
                    else:assert not struct.unpack('<7I',m.uc.mem_read(0xd0000060,28))[6]&2,(label,'READY context',current)
                    if label=='candidate':assert correct[label],('current source wrong',current,state_name,out[label],f'{expected:016X}')
                if out['candidate']!=old['candidate']:old_candidate_changes.append(dict(**current,SIO=state_name,old=old['candidate'],fresh=out['candidate']))
                if out['Qfplib']!=old['Qfplib']or costs['Qfplib']!=old['Qfplib_instructions']or correct['Qfplib']!=old['Qfplib_correct']:
                    reference_changes.append(dict(**current,SIO=state_name,old=old,fresh_output=out['Qfplib'],fresh_instructions=costs['Qfplib'],fresh_correct=correct['Qfplib']))
                change=costs['candidate']-old['candidate_instructions'];delta[change]+=1
                if change>0:increases.append(dict(**current,SIO=state_name,old_candidate=old['candidate_instructions'],candidate=costs['candidate'],delta=change))
                if correct['Qfplib']:
                    relation='strict'if costs['candidate']<costs['Qfplib']else'equal'if costs['candidate']==costs['Qfplib']else'slower'
                    comparisons[relation]+=1;relations.append(relation);group['relations'][relation]+=1
                    if relation=='slower':
                        loss=dict(**current,SIO=state_name,candidate=costs['candidate'],Qfplib=costs['Qfplib'],expected=f'{expected:016X}',old_candidate=old['candidate_instructions'])
                        remaining.append(loss)
                        if old['Qfplib_correct']and old['candidate_instructions']<=old['Qfplib_instructions']:new_losses.append(loss)
                else:wrongref+=1;group['relations']['wrong_reference_retained']+=1
                stream.write((json.dumps(dict(**current,SIO=state_name,expected=f'{expected:016X}',outputs=out,instructions=costs,correct=correct,old_component=old),separators=(',',':'))+'\n').encode());state_rows+=1;group['state_rows']+=1
            classification='slower'if'slower'in relations else'equal'if'equal'in relations else'strict'if relations else'no_correct_reference';relation_cases[classification]+=1
except Exception as error:
    (W/(op+'-FAILURE.json')).write_text(json.dumps(dict(status='FAILED_CURRENT_SOURCE_FULL_CORPUS_REPLAY',error=repr(error),current=current,completed_ARM_calls=dict(completed),attempted_ARM_calls=dict(attempted),oracle_input_evaluations=oraclecalls,state_rows_written=state_rows),indent=2)+'\n');raise
assert state_rows==2*meta['counts'][op]and oraclecalls==meta['counts'][op]
assert sha(S/'link-result.json')==source_pin and sha(S/'source/code/native_eabi_m0_log70.inc')==source_code_pin
result=dict(status='PASS_CURRENT_R18_UNION_'+op.upper()+'_CORPUS_FRESH_QFPLIB_AND_DIRECTED_MPFR',operation=op,
    source_FROZEN_sha256=source_frozen_pin,source_link_manifest_sha256=source_pin,source_code_sha256=source_code_pin,candidate_ELF_sha256=sha(S/'candidate.elf'),reference_ELF_sha256=sha(REF),
    corpus_metadata_sha256=sha(W/'corpus.json'),input_sha256=sha(inputfile),records_sha256=sha(W/(op+'-records.jsonl.gz')),
    unique_input_cases=meta['counts'][op],state_rows=state_rows,completed_ARM_calls=dict(completed),actual_qualified_ARM_calls=sum(completed.values()),
    fresh_Qfplib_calls=completed['Qfplib'],inherited_Qfplib_calls_counted_as_fresh=0,
    Oracle_input_evaluations=oraclecalls,actual_directed_MPFR_input_evaluations=oraclecalls-snan,exact_sNaN_policy_shortcuts=snan,MPFR_version=oracle.version,
    candidate_wrong=0,correct_reference_state_comparisons=dict(comparisons),wrong_Qfplib_state_rows_retained=wrongref,
    case_classification=dict(relation_cases),remaining_losing_input_cases=len({r['index']for r in remaining}),remaining_reference_state_rows=remaining,
    newly_losing_cases_vs_historical_component=len({r['index']for r in new_losses}),new_losing_reference_state_rows_vs_component=new_losses,
    historical_candidate_instruction_delta_histogram=dict(delta),all_historical_candidate_increase_rows=increases,
    fresh_reference_disagreements_with_old_records=reference_changes,old_expected_disagreements_with_fresh_gold=old_gold_changes,
    old_candidate_bits_different_from_current=old_candidate_changes,groups=groups,
    observed_stacks={n:SP-m.stack_lowest for n,m in machines.items()},
    automatic_candidate_ROM_initializer_calls_excluded=1,explicit_source_loader_calls_excluded=1,
    actual_one_source_linked_ELF_real_ROM_no_old_code_overlay=True,all_correct_Qfplib_outputs_compared_without_nominal_domain_filter=True,
    wrong_references_and_all_costs_retained=True,all_calls_PCS_SP_bounded_writes_and_SIO_checked=True,
    instructions_are_not_physical_cycles=True,hardware_accessed=False,integration_GO=False,goal_complete=False,elapsed_seconds=time.monotonic()-started)
(W/(op+'-result.json')).write_text(json.dumps(result,indent=2)+'\n')
print(json.dumps({k:v for k,v in result.items()if k not in ['remaining_reference_state_rows','new_losing_reference_state_rows_vs_component','all_historical_candidate_increase_rows','fresh_reference_disagreements_with_old_records','old_expected_disagreements_with_fresh_gold','old_candidate_bits_different_from_current','groups','historical_candidate_instruction_delta_histogram']},indent=2),flush=True)

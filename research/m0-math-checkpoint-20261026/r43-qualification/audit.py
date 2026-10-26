"""Join all R43 qualification rows, preserve every cost delta and prior scope."""
from pathlib import Path
from collections import Counter
from itertools import zip_longest
import gzip,hashlib,json,sys
sys.dont_write_bytecode=True
W=Path(__file__).resolve().parent;ROOT=W.parents[1]
S=ROOT/'.build/m0-math-unified-pow-rsqrt-nativeq8-r43-20261026'
P=ROOT/'.build/m0-math-unified-pow-rsqrt-seedreuse-r42-qualification-20261026'
PS=ROOT/'.build/m0-math-unified-pow-rsqrt-seedreuse-r42-20261026'
R29=ROOT/'.build/m0-math-unified-exp-bit62-r29-qualification-20261026'
read=lambda p:json.loads(p.read_bytes())
def sha(p):
    h=hashlib.sha256()
    with p.open('rb')as f:
        for b in iter(lambda:f.read(1048576),b''):h.update(b)
    return h.hexdigest()
assert not(W/'joined-audit.json').exists()
manifestcounts={}
for d,pin in [(S,'170cd77a62244459c526ea2817f964652f4355c31e7824defc7b0195a6a5b22b'),(P,'c9e7ebb1dcd34a4536e12fcb77af95ecbfc51f44176fe5b7e57e85b7cbe39515')]:
    assert sha(d/'FROZEN.json')==pin
    files=read(d/'FROZEN.json')['files']
    for name,r in files.items():assert(d/name).stat().st_size==r['bytes']and sha(d/name)==r['sha256'],(d,name)
    manifestcounts[str(d.relative_to(ROOT))]=len(files)
proof=read(S/'source-binding-proof.json');unit=read(S/'helper-unit-result.json');diagnostic=read(S/'probe-result.json')
assert proof['all_native_branch_paths_save1instruction']and proof['ordinary_entry_keeps_arbitrary_incoming_NZCV']and unit['candidate_wrong']==unit['all_native_fixture_parent_instruction_increase_rows']==0
assert unit['actual_qualified_control_ARM_calls']==573536 and unit['generic_instruction_delta_histogram']=={'2':143384}and unit['native_fixture_instruction_delta_histogram']=={'-1':143384}
matrix=read(W/'matrix-comparison.json')
for r in matrix['matrices'].values():assert not r['parent_increase_rows']and not r['new_correct_Qfplib_loss_rows']
refs=('qfp_composed_pow','qfp_composed_pow_exact','qfp_composed_pow_integer')
target={(r['x'],r['y'])for r in read(S/'probe-inputs.json')['groups']};cache={};inputs=set();pl=set();cl=set();details={}
for phase in ['full','admission']:
    report=read(W/(phase+'-result.json'));assert report['candidate_wrong']==report['actual_fresh_R42_Qfp_MPFR_calls']==0 and not report['new_correct_reference_loss_rows']and not report['all_parent_instruction_increase_rows']
    unique=set();parent=set();child=set();rows=0;overlap=0;wrong=0;hist=Counter()
    with gzip.open(W/(phase+'-records.jsonl.gz'),'rt')as f:
        for line in f:
            r=json.loads(line);key=r['x'],r['y'];sk=(*key,r['SIO']);unique.add(key);inputs.add(key);rows+=1
            assert r['correct']['candidate']and r['correct']['parent']and r['outputs']['candidate']==r['outputs']['parent']
            if sk in cache:
                z=cache[sk];overlap+=1
                for n in ['candidate','parent',*refs]:assert r['outputs'][n]==z['outputs'][n]and r['instructions'][n]==z['instructions'][n]and r['correct'][n]==z['correct'][n],(sk,n)
            if key in target:cache[sk]=r
            cc,pc=r['instructions']['candidate'],r['instructions']['parent'];assert cc-pc in (-1,0);hist[cc-pc]+=1
            for ref in refs:
                if not r['correct'][ref]:wrong+=1;continue
                if pc>r['instructions'][ref]:parent.add(key);pl.add(key)
                if cc>r['instructions'][ref]:child.add(key);cl.add(key)
    assert rows==report['state_rows']and len(unique)==report['unique_input_pairs']and len(parent)==report['parent_losing_pairs']
    assert child=={tuple(k)for k in report['remaining_losing_argument_pairs']}and not child-parent
    assert dict(hist)=={int(k):v for k,v in report['parent_instruction_delta_histogram'].items()}and wrong==report['wrong_reference_state_variants_retained']
    details[phase]=dict(unique_inputs=len(unique),state_rows=rows,parent_losing_pairs=len(parent),candidate_losing_pairs=len(child),fixed_pairs=len(parent-child),public_parent_increase_rows=0,wrong_reference_variants_retained=wrong,instruction_delta_histogram=dict(hist),overlap_state_rows_checked=overlap,net_instruction_delta=sum(k*v for k,v in hist.items()))
    if phase=='full':fullinputs=set(inputs);fullparent=set(pl);fullchild=set(cl)
assert len(fullinputs)==140715 and len(fullparent)==2303 and len(pl-cl)==10 and not cl-pl
prioraudit=read(P/'joined-audit.json');priorloss={tuple(k)for k in prioraudit['remaining_losing_argument_pairs']};assert len(priorloss)==2353 and priorloss<=pl
priorinputs=set()
with gzip.open(P/'full-records.jsonl.gz','rt')as f:
    for line in f:
        r=json.loads(line);priorinputs.add((r['x'],r['y']))
priorinputs.update((r['x'],r['y'])for r in read(PS/'probe-inputs.json')['groups']);assert len(priorinputs)==151409 and priorinputs<=inputs
assert len(priorloss-cl)==10 and len(pl-priorloss)==0 and len(cl-priorloss)==0
assert len(pl)==diagnostic['parent_losing_pairs']==2353 and len(cl)==diagnostic['candidate_losing_pairs']==2343
baseinputs=set(inputs);baseparent=set(pl);basechild=set(cl);primarynew=set();primarypow=0
for name in ['original507','broad']:
    with gzip.open(P/(name+'-records.jsonl.gz'),'rt')as a,gzip.open(W/(name+'-records.jsonl.gz'),'rt')as b:
        for aa,bb in zip_longest(a,b):
            assert aa is not None and bb is not None;a0,b0=json.loads(aa),json.loads(bb)
            assert a0['outputs']==b0['outputs']and a0['correct']==b0['correct']
            if b0['operation']!='pow':assert a0['instructions']==b0['instructions'];continue
            primarypow+=1;key=b0['x'],b0['y'];inputs.add(key)
            if key not in baseinputs:primarynew.add(key)
            cc,pc=b0['instructions']['candidate'],a0['instructions']['candidate'];assert cc-pc in(-1,0)
            sk=(*key,b0['SIO'])
            if sk in cache:
                z=cache[sk]
                for n in ['candidate',*refs]:assert b0['outputs'][n]==z['outputs'][n]and b0['instructions'][n]==z['instructions'][n]and b0['correct'][n]==z['correct'][n]
                assert a0['instructions']['candidate']==z['instructions']['parent']
            for ref in refs:
                assert ref in b0['instructions']
                if not b0['correct'][ref]:continue
                if pc>b0['instructions'][ref]:pl.add(key)
                if cc>b0['instructions'][ref]:cl.add(key)
assert pl==baseparent and cl==basechild
primary=sum(read(W/(n+'.json'))['actual_qualified_math_ARM_calls']for n in ['original507','broad']);assert primary==196714
public=sum(v['state_rows']for v in details.values())+primary;control=unit['actual_qualified_control_ARM_calls']
assert public==528364 and public+control==1101900
assert sha(R29/'FROZEN.json')=='c1629034ff342e7f7da22d246d360e4548506500a99450d42772107bea4012c5'
cumulative={}
for name in ['original507','broad']:
    original=R29/(name+'-records.jsonl.gz');pin=read(R29/'FROZEN.json')['files'][original.name];assert sha(original)==pin['sha256']
    filename='cumulative-R29-'+name+'-records.jsonl.gz';hist=Counter();rows=0
    with gzip.open(original,'rt')as a,gzip.open(W/(name+'-records.jsonl.gz'),'rt')as b,gzip.GzipFile(filename=str(W/filename),mode='wb',mtime=0)as out:
        for aa,bb in zip_longest(a,b):
            assert aa is not None and bb is not None;a0,b0=json.loads(aa),json.loads(bb)
            for key in ['operation','x','y','SIO']:assert a0.get(key)==b0.get(key)
            assert a0['outputs']==b0['outputs']and a0['correct']==b0['correct']
            old,new=a0['instructions']['candidate'],b0['instructions']['candidate'];delta=new-old;hist[delta]+=1;rows+=1
            refdata={n:dict(output=b0['outputs'][n],instructions=v,correct=b0['correct'][n])for n,v in b0['instructions'].items()if n not in ['candidate','zero-control']}
            out.write((json.dumps(dict(operation=b0['operation'],x=b0['x'],y=b0.get('y'),SIO=b0['SIO'],R29=old,R43=new,delta=delta,references=refdata),separators=(',',':'))+'\n').encode())
    cumulative[name]=dict(state_rows=rows,instruction_delta_histogram=dict(hist),net_instruction_delta=sum(k*v for k,v in hist.items()),increased_rows=sum(v for k,v in hist.items()if k>0),decreased_rows=sum(v for k,v in hist.items()if k<0),unchanged_rows=hist[0],all_rows_retained_file=filename,records_sha256=sha(W/filename))
exp_pin=prioraudit['inherited_full_exp_R29_cost_pin'];ep=ROOT/exp_pin['path'];assert ep.stat().st_size==exp_pin['bytes']and sha(ep)==exp_pin['sha256']
result=dict(status='PASS_R43_ALL_REPLAYS_PRIMARY_INTEGER_PROOF_AND_COST_AUDIT',source_FROZEN_sha256=sha(S/'FROZEN.json'),parent_R42_qualification_FROZEN_sha256=sha(P/'FROZEN.json'),verified_manifest_files=manifestcounts,
    same_old_full_pow_inputs=len(fullinputs),same_old_full_parent_losses=len(fullparent),same_old_full_candidate_losses=len(fullchild),same_old_full_fixed=len(fullparent-fullchild),previous_qualified_union_inputs=len(priorinputs),previous_qualified_parent_losses=len(priorloss),previous_qualified_candidate_losses=len(priorloss&cl),previous_qualified_fixed=len(priorloss-cl),
    union_pow_inputs_before_primary=len(baseinputs),union_pow_inputs_with_primary=len(inputs),primary_additional_nonlosing_inputs=len(primarynew),primary_pow_state_rows=primarypow,union_parent_losing_pairs=len(pl),union_candidate_losing_pairs=len(cl),union_fixed_pairs=len(pl-cl),union_new_correct_reference_losses=0,candidate_wrong=0,
    diagnostic_new_inputs_vs_previous_qualified_union=len(baseinputs-priorinputs),diagnostic_new_parent_preexisting_losses=len(pl-priorloss),diagnostic_new_fixed=len((pl-priorloss)-cl),diagnostic_new_remaining=len(cl-priorloss),remaining_losing_argument_pairs=[list(k)for k in sorted(cl)],fixed_losing_argument_pairs=[list(k)for k in sorted(pl-cl)],per_campaign=details,
    all3_Qfplib_references_retained_no_nominal_filter=True,all_wrong_reference_outputs_costs_retained=True,all_public_parent_instruction_increase_rows=0,all_current_generic_helper_control_parent_increase_rows=143384,all_current_native_fixture_control_parent_increase_rows=0,all_generic_control_increases_retained=True,all13_native_helper_CFG_paths_save1instruction=True,all13_generic_helper_CFG_paths_add2_retained=True,all_actual_diagnostic_native_metadata_equal_R42=True,other17_M4default_objects_exact=True,RPASM_allocatedbytes_exact_unique_relocation_changed=True,bank_changed13bytes_symbolically_mapped=True,
    fresh_full_R43_public_ARM_calls=281430,fresh_admission_R43_public_ARM_calls=50220,full_and_admission_R42_Qfp_MPFR_actual_fresh_calls=0,full_gold_R42_Qfp_inherited_frozen_R42_qualification=True,admission_gold_R42_Qfp_inherited_frozen_R43_diagnostic=True,fresh_primary_public_ARM_calls=primary,actual_qualified_public_ARM_calls=public,actual_qualified_primitive_ARM_calls=control,actual_qualified_ARM_calls=public+control,primitive_frames_not_publicaccuracygold=True,
    source_diagnostic_ARM251100_MPFR16726_sNaN14_separate_not_fresh_qualified_pool=True,all_prior_ARM_MPFR_and_source_loader_initializers_excluded_pool=True,primary_comparison=matrix['matrices'],cumulative_R29_primary=cumulative,inherited_full_exp_R29_cost_pin=exp_pin,inherited_full_exp_R29_R38_audit=prioraudit['inherited_full_exp_R29_R38_audit'],
    inherited_R41_synthetic_helper_increase_rows3591_retained=True,inherited_R41_helper_increases_not_R43_parent_increases_or_public_input_cases=True,cumulative_scope='Fresh R43 primary against R29; all rows retained. Full-exp/R29 and exp512/ln0 remain inherited R38/R42. Earlier3591synthetic helper increases retained in R41 packet, not pooled as fresh R43; new143384generic helper increases retained separately, not public numeric-gold. Not workload weighted or physical cycles.',
    current_exp_losing_inputs_inherited=512,current_ln_losing_inputs_inherited=0,known_finite_losing_operation_argument_tuples=512+len(cl),whole_remaining_library_count=False,observed_pow_stack=max(read(W/(n+'-result.json'))['observed_stack']for n in ['full','admission']),not_universal_stack_bound=True,selected=False,independent_acceptance=False,performance_or_adoption_GO=False,hardware_accessed=False,physical_cycles_measured=False,integration_GO=False,goal_complete=False)
(W/'joined-audit.json').write_text(json.dumps(result,indent=2)+'\n');print(json.dumps({k:v for k,v in result.items()if k not in ['remaining_losing_argument_pairs','fixed_losing_argument_pairs']},indent=2),flush=True)

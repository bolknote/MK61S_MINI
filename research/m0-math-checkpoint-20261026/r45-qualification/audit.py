"""Join R45 pow/div/exp/ln/primary evidence without filtering adverse cases."""
from pathlib import Path
from collections import Counter
from itertools import zip_longest
import gzip,hashlib,json,sys
sys.dont_write_bytecode=True
W=Path(__file__).resolve().parent;ROOT=W.parents[1]
S=ROOT/'.build/m0-math-unified-ddiv-cold-overflow-r45-20261026'
P=ROOT/'.build/m0-math-unified-pow-rsqrt-nativeq8-r43-qualification-20261026'
R29=ROOT/'.build/m0-math-unified-exp-bit62-r29-qualification-20261026'
read=lambda p:json.loads(p.read_bytes())
def sha(p):
    h=hashlib.sha256()
    with p.open('rb')as f:
        for b in iter(lambda:f.read(1048576),b''):h.update(b)
    return h.hexdigest()
assert not(W/'joined-audit.json').exists()
manifestcounts={}
for base,pin in [(S,'dbc455078837507acaeb750df1e3fb6800b923e2a9a880c9c6bcc2150ba3527a'),(P,'ebef878da8240173c273bb9e31b02c0a55c48e75286a7fe0dcc800c3c2130786')]:
    assert sha(base/'FROZEN.json')==pin
    for n,r in read(base/'FROZEN.json')['files'].items():assert(base/n).stat().st_size==r['bytes']and sha(base/n)==r['sha256'],(base,n)
    manifestcounts[str(base.relative_to(ROOT))]=len(read(base/'FROZEN.json')['files'])
proof=read(S/'source-binding-proof.json');assert proof['both_source_edits_reversed_exactly_to_R43']and proof['other17_objects_including_M4default_exact']
matrix=read(W/'matrix-comparison.json')
for d in matrix['matrices'].values():assert not d['new_correct_Qfplib_loss_rows']and not d['parent_increase_rows']and d['candidate_instruction_delta_histogram']=={'0':d['state_rows']}
refs=('qfp_composed_pow','qfp_composed_pow_exact','qfp_composed_pow_integer')
target={(r['x'],r['y'])for r in read(S/'probe-inputs.json')['groups']};cache={};inputs=set();pl=set();cl=set();details={}
for phase in ['full','admission']:
    report=read(W/(phase+'-result.json'));assert report['candidate_wrong']==report['actual_fresh_R43_Qfp_MPFR_calls']==0 and not report['new_correct_reference_loss_rows']
    unique=set();parent=set();child=set();rows=0;overlap=0;wrong=0;inc=0;hist=Counter()
    with gzip.open(W/(phase+'-records.jsonl.gz'),'rt')as f:
        for line in f:
            r=json.loads(line);key=r['x'],r['y'];sk=(*key,r['SIO']);unique.add(key);inputs.add(key);rows+=1
            assert r['correct']['candidate']and r['correct']['parent']and r['outputs']['candidate']==r['outputs']['parent']
            if sk in cache:
                old=cache[sk];overlap+=1
                for name in ['candidate','parent',*refs]:assert r['outputs'][name]==old['outputs'][name]and r['instructions'][name]==old['instructions'][name]and r['correct'][name]==old['correct'][name]
            if key in target:cache[sk]=r
            cc,pc=r['instructions']['candidate'],r['instructions']['parent'];hist[cc-pc]+=1;inc+=cc>pc
            for ref in refs:
                if not r['correct'][ref]:wrong+=1;continue
                if pc>r['instructions'][ref]:parent.add(key);pl.add(key)
                if cc>r['instructions'][ref]:child.add(key);cl.add(key)
    assert rows==report['state_rows']and len(unique)==report['unique_input_pairs']and len(parent)==report['parent_losing_pairs']
    assert child=={tuple(k)for k in report['remaining_losing_argument_pairs']}and not child-parent
    assert wrong==report['wrong_reference_state_variants_retained']and inc==len(report['all_parent_instruction_increase_rows'])
    assert dict(hist)=={int(k):v for k,v in report['parent_instruction_delta_histogram'].items()}
    details[phase]=dict(inputs=len(unique),state_rows=rows,parent_losses=len(parent),candidate_losses=len(child),fixed=len(parent-child),all_parent_increase_rows=inc,wrong_reference_variants_retained=wrong,instruction_delta_histogram=dict(hist),overlap_rows_checked=overlap,net_instruction_delta=sum(k*v for k,v in hist.items()))
    if phase=='full':fullinputs=set(inputs);fullparent=set(pl);fullchild=set(cl)
assert(len(fullinputs),len(fullparent),len(fullchild))==(140715,2293,1997)
assert(len(inputs),len(pl),len(cl),len(pl-cl))==(151409,2343,2047,296)
assert pl=={tuple(k)for k in read(P/'joined-audit.json')['remaining_losing_argument_pairs']}
assert details['full']['all_parent_increase_rows']==84 and details['admission']['all_parent_increase_rows']==30
baseinputs=set(inputs);primarypow=0
for name in ['original507','broad']:
    with gzip.open(P/(name+'-records.jsonl.gz'),'rt')as a,gzip.open(W/(name+'-records.jsonl.gz'),'rt')as b:
        for aa,bb in zip_longest(a,b):
            assert aa is not None and bb is not None;a0,b0=json.loads(aa),json.loads(bb);assert a0['outputs']==b0['outputs']and a0['correct']==b0['correct']and a0['instructions']==b0['instructions']
            if b0['operation']=='pow':primarypow+=1;assert(b0['x'],b0['y'])in baseinputs
primary=sum(read(W/(n+'.json'))['actual_qualified_math_ARM_calls']for n in ['original507','broad']);assert primary==196714

# Public IEEE division source tests are included once after source sealing;
# they are not re-executed or described as fresh qualification-stage calls.
dcache={};dinputs=set();dparent=set();dchild=set();divdetails={};divcalls=0;divmpfr=0;divsnan=0
for tag,reportname,rawname in [('direct','div-probe-result.json','div-probe-records.jsonl.gz'),('grid','guard-grid-result.json','guard-grid-records.jsonl.gz')]:
    report=read(S/reportname);assert report['candidate_wrong']==0 and not report['new_correct_Qfp_loss_rows']
    parent=set();child=set();unique=set();hist=Counter();rows=0;inc=0;wrong=0;overlap=0
    with gzip.open(S/rawname,'rt')as f:
        for line in f:
            r=json.loads(line);key=r['a'],r['b'];sk=(*key,r['SIO']);unique.add(key);dinputs.add(key);rows+=1
            assert r['correct']['candidate']and r['correct']['parent']and r['outputs']['candidate']==r['outputs']['parent']
            sig=(r['outputs'],r['instructions'],r['correct'])
            if sk in dcache:assert dcache[sk]==sig;overlap+=1
            else:dcache[sk]=sig
            cc,pc,qc=r['instructions']['candidate'],r['instructions']['parent'],r['instructions']['Qfplib'];hist[cc-pc]+=1;inc+=cc>pc
            if not r['correct']['Qfplib']:wrong+=1;continue
            if pc>qc:parent.add(key);dparent.add(key)
            if cc>qc:child.add(key);dchild.add(key)
    assert rows==report['state_rows']and len(unique)==report['input_pairs']and len(parent)==report['parent_losing_pairs']and len(child)==report['candidate_losing_pairs']and not child-parent
    assert inc==len(report['all_parent_instruction_increase_rows'])and wrong==report['wrong_reference_state_variants_retained']
    assert dict(hist)=={int(k):v for k,v in report['parent_instruction_delta_histogram'].items()}
    divdetails[tag]=dict(inputs=len(unique),state_rows=rows,parent_losses=len(parent),candidate_losses=len(child),fixed=len(parent-child),all_parent_increase_rows=inc,wrong_reference_rows_retained=wrong,overlap_rows_checked=overlap,instruction_delta_histogram=dict(hist))
    divcalls+=report['actual_diagnostic_ARM_calls'];divmpfr+=report['actual_directed_MPFR_inputs'];divsnan+=report['sNaN_policy_shortcuts']
assert(len(dparent),len(dchild),divcalls,divmpfr,divsnan)==(9061,148,182736,20270,34)

trans={};transcalls=0
for op,expected_inputs,expected_loss in [('exp',568856,512),('ln',180295,0)]:
    r=read(W/(op+'-result.json'));assert r['candidate_wrong']==r['actual_fresh_parent_Qfp_MPFR_calls']==0 and not r['new_correct_reference_loss_rows']and not r['all_parent_instruction_increase_rows']
    assert r['unique_inputs']==expected_inputs and r['candidate_losing_inputs']==r['parent_losing_inputs']==expected_loss and not r['all4_shared_division_entry_visits']
    count=0;wrong=0;parent=set();child=set();unique=set();hist=Counter()
    with gzip.open(W/(op+'-records.jsonl.gz'),'rt')as f:
        for line in f:
            z=json.loads(line);count+=1;key=z['x'];unique.add(key);parentkey='inherited_R38'if op=='exp'else'inherited_R18'
            assert z['correct']['candidate']and z['correct'][parentkey]and z['outputs']['candidate']==z['outputs'][parentkey]
            cc,pc,qc=z['instructions']['candidate'],z['instructions'][parentkey],z['instructions']['Qfplib'];hist[cc-pc]+=1;assert cc==pc
            if not z['correct']['Qfplib']:wrong+=1;continue
            if pc>qc:parent.add(key)
            if cc>qc:child.add(key)
    assert count==r['state_rows']and len(unique)==expected_inputs and len(parent)==len(child)==expected_loss and wrong==r['wrong_reference_state_rows_retained']
    assert dict(hist)=={0:count};transcalls+=count
    trans[op]=dict(unique_inputs=len(unique),state_rows=count,parent_losses=len(parent),candidate_losses=len(child),all_parent_increase_rows=0,new_correct_reference_losses=0,instruction_delta_histogram=dict(hist),wrong_reference_rows_retained=wrong,shared_division_entry_visits=r['all4_shared_division_entry_visits'],duplicate_source_rows_checked=r['duplicate_state_rows_checked'],reference_gold_parent_explicitly_cached=True)
assert transcalls==1585497

# Preserve every matching primary row against historical R29, including all
# old slower cases. The full-exp/R29 rows remain pinned and are now also
# validated by the fresh current-exp counts being exactly the inherited R38.
assert sha(R29/'FROZEN.json')=='c1629034ff342e7f7da22d246d360e4548506500a99450d42772107bea4012c5'
cumulative={}
for name in ['original507','broad']:
    old=R29/(name+'-records.jsonl.gz');pin=read(R29/'FROZEN.json')['files'][old.name];assert sha(old)==pin['sha256'];filename='cumulative-R29-'+name+'-records.jsonl.gz';hist=Counter();rows=0
    with gzip.open(old,'rt')as a,gzip.open(W/(name+'-records.jsonl.gz'),'rt')as b,gzip.GzipFile(filename=str(W/filename),mode='wb',mtime=0)as out:
        for aa,bb in zip_longest(a,b):
            assert aa is not None and bb is not None;x,y=json.loads(aa),json.loads(bb)
            for key in ['operation','x','y','SIO']:assert x.get(key)==y.get(key)
            assert x['outputs']==y['outputs']and x['correct']==y['correct']
            oldcost,newcost=x['instructions']['candidate'],y['instructions']['candidate'];d=newcost-oldcost;hist[d]+=1;rows+=1
            refs0={n:dict(output=y['outputs'][n],instructions=v,correct=y['correct'][n])for n,v in y['instructions'].items()if n not in ['candidate','zero-control']}
            out.write((json.dumps(dict(operation=y['operation'],x=y['x'],y=y.get('y'),SIO=y['SIO'],R29=oldcost,R45=newcost,delta=d,references=refs0),separators=(',',':'))+'\n').encode())
    cumulative[name]=dict(state_rows=rows,instruction_delta_histogram=dict(hist),net_instruction_delta=sum(k*v for k,v in hist.items()),increased_rows=sum(v for k,v in hist.items()if k>0),decreased_rows=sum(v for k,v in hist.items()if k<0),unchanged_rows=hist[0],all_rows_retained_file=filename,records_sha256=sha(W/filename))
pa=read(P/'joined-audit.json');epin=pa['inherited_full_exp_R29_cost_pin'];ep=ROOT/epin['path'];assert ep.stat().st_size==epin['bytes']and sha(ep)==epin['sha256']
stage=281430+50220+primary+transcalls;public=stage+divcalls;assert stage==2113861 and public==2296597
increases={**{'pow_'+k:v['all_parent_increase_rows']for k,v in details.items()},**{'ddiv_'+k:v['all_parent_increase_rows']for k,v in divdetails.items()},'exp':0,'ln':0,'primary':0}
result=dict(status='PASS_R45_COMPLETE_SHARED_ARITHMETIC_FINITE_QUALIFICATION_AND_ALL_COST_AUDIT',source_FROZEN_sha256=sha(S/'FROZEN.json'),parent_R43_qualification_FROZEN_sha256=sha(P/'FROZEN.json'),verified_manifest_files=manifestcounts,
    same_full_pow_inputs=140715,same_full_pow_parent_losses=2293,same_full_pow_candidate_losses=1997,same_full_pow_fixed=296,union_pow_inputs=len(inputs),union_pow_parent_losses=len(pl),union_pow_candidate_losses=len(cl),union_pow_fixed=len(pl-cl),pow_primary_state_rows=primarypow,pow_campaigns=details,pow_remaining_losing_argument_pairs=[list(k)for k in sorted(cl)],
    source_div_unique_inputs=len(dinputs),source_div_unique_state_rows=len(dcache),source_div_parent_losing_pairs=len(dparent),source_div_candidate_losing_pairs=len(dchild),source_div_fixed_pairs=len(dparent-dchild),source_div_campaigns=divdetails,div_remaining_losing_argument_pairs=[list(k)for k in sorted(dchild)],source_division_public_validation_ARM_included_once=divcalls,source_division_validation_MPFR_inputs20270_sNaN34_included_once=True,
    exp_ln_campaigns=trans,current_exp_losing_inputs=512,current_ln_losing_inputs=0,current_pow_losing_pairs=2047,current_ddiv_losing_pairs=148,known_finite_losing_operation_argument_tuples=2707,whole_remaining_library_count=False,candidate_wrong=0,new_correct_reference_loss_rows=0,
    every_parent_cost_increase_retained_by_campaign=increases,no_nominal_reference_filter=True,all_wrong_reference_outputs_costs_retained=True,all_primary_bits_refs_and_costs_exact_R43=True,primary_comparison=matrix['matrices'],
    actual_fresh_qualification_stage_public_ARM_calls=stage,actual_source_division_public_ARM_calls_included_once=divcalls,actual_qualified_public_ARM_calls=public,actual_qualified_primitive_ARM_calls=0,actual_qualified_ARM_calls=public,
    pow_full_admission_parent_Qfp_MPFR_cached_not_fresh=True,pow_full_admission_fresh_parent_Qfp_MPFR_calls=0,full_exp_parent_R38_gold_Qfp_cached_not_fresh=True,full_ln_parent_R18_gold_Qfp_cached_not_fresh=True,fresh_primary_MPFR_Qfp_separate=True,source_div_MPFR_Qfp_parent_fresh_in_frozen_source_included_once_not_rerun=True,
    source_pow_diagnostic251100_ARM16726_MPFR14sNaN_excluded_execution_pool=True,R44_unselected25758_ARM_R43baseline10440_ARM_allprior_diagnostics_and_ROMinitializers_excluded_pool=True,inherited_R43_Q8_controls573536_not_fresh=True,inherited_R43_generic_helper143384_adverse_controls_retained=True,
    cumulative_R29_primary=cumulative,inherited_full_exp_R29_cost_pin=epin,inherited_full_exp_R29_R38_audit=pa['inherited_full_exp_R29_R38_audit'],inherited_full_exp_R29_adverse166132rows_retained=True,fresh_full_exp_R45_counts_exact_R38_revalidate_inherited_full_exp_R29_rows=True,inherited_R41_synthetic_helper3591_adverse_controls_retained=True,
    source_17_other_M4default_objects_exact=True,new_lookup_RAM_libgcc_bytes=0,code_Flash_delta_bytes104=True,mandatory_new_div_guard6negative_native_Q8_guard12negative_exp_R12_17negative_normalized_ROMloader9disabled_PASS=True,
    observed_pow_stack=max(read(W/(p+'-result.json'))['observed_stack']for p in ['full','admission']),observed_exp_stack=read(W/'exp-result.json')['observed_stack'],observed_ln_stack=read(W/'ln-result.json')['observed_stack'],not_universal_stack_bounds=True,
    all_actual_exp_ln_changed_division_visits_zero=True,no_workload_or_physical_cycle_speed_claim=True,selected=False,independent_acceptance=False,performance_or_adoption_GO=False,physical_cycles_measured=False,hardware_accessed=False,integration_GO=False,goal_complete=False)
(W/'joined-audit.json').write_text(json.dumps(result,indent=2)+'\n');print(json.dumps({k:v for k,v in result.items()if k not in ['pow_remaining_losing_argument_pairs','div_remaining_losing_argument_pairs']},indent=2),flush=True)
